# -*- coding: utf-8 -*-
"""LLM 客户端：OpenAI 兼容接口，无状态单次调用（每次请求携带完整上下文，不保留任何历史），
支持 JSON 结构化输出与容错解析。"""
import json
import re
import threading
import time

import requests

import config

MAX_JSON_CHARS = 200000

# 429（限流）最小等待（秒）默认值：实际等待取 max(rate_limit_min_wait, retry_interval)，
# 且次数计入 retry_times（用户设置的「重试次数/间隔」对限流同样生效）。可在设置页调整。
RATE_LIMIT_MIN_WAIT = 5


class LLMError(Exception):
    pass


class StopRequested(LLMError):
    """用户主动停止任务：LLM 调用被立即中断（v0.55）。

    与普通 LLMError 的区别：不参与自动重试/自动续跑，调用方应清理未完成内容并正常收尾。
    """


def _err_text(em):
    """把网关错误对象转成可读文本（OpenAI 风格 error 为 dict 或字符串）。"""
    if isinstance(em, dict):
        return str(em.get("message") or em.get("error") or em)[:200]
    return str(em)[:200]


# 任务级停止事件（线程局部）：任务线程开始/结束时用 set_abort 绑定/解绑，
# LLM 调用在流式读取过程中检测到事件置位会立即断开连接并抛 StopRequested——
# 「点停止立即生效，不等本次请求写完」（用户指正：停止太墨迹）。
_abort_local = threading.local()

# 当前活跃的 LLM 请求响应集合（v1.59 立即停止用）：点停止时 abort_active_resps()
# close 所有在途连接，阻塞在流式读取等待数据的线程立刻抛异常 → 转 StopRequested，
# 不再等当前节点（请求）自然结束。
_active_resp_lock = threading.Lock()
_active_resps = set()


def _register_resp(resp):
    with _active_resp_lock:
        _active_resps.add(resp)


def _unregister_resp(resp):
    with _active_resp_lock:
        _active_resps.discard(resp)


def abort_active_resps():
    """立即关闭所有活跃 LLM 请求连接（供 UI 点停止调用）：
    阻塞的流式读取马上抛异常，配合停止事件转 StopRequested。"""
    with _active_resp_lock:
        items = list(_active_resps)
    for r in items:
        try:
            r.close()
        except Exception:
            pass


def set_abort(event):
    """绑定当前线程的停止事件（传 None 解绑）。"""
    _abort_local.event = event


def current_abort():
    """返回当前线程绑定的停止事件（无则 None）。

    v0.79.1 供并行子线程继承绑定：ThreadPoolExecutor 的子线程有自己的线程局部，
    主 worker 绑定的停止事件不会自动传给子线程——子线程的 LLM 调用（429 重试风暴等）
    因此不响应点停止。子线程开头用 set_abort(current_abort()) 继承即可。
    """
    return getattr(_abort_local, "event", None)


def _abort_check():
    ev = getattr(_abort_local, "event", None)
    return bool(ev and ev.is_set())


def _abort_sleep(seconds):
    """可被停止打断的等待（重试间隔/限流等待期间用户点停止能立即响应）。

    未绑定停止事件（set_abort 未调用/已解绑）时与普通 time.sleep 完全一致（一次睡完）；
    绑定后才按 0.2s 分段，保证点停止能打断限流/重试等待立即生效。
    """
    seconds = max(0.0, seconds)
    if seconds <= 0:
        return
    if not _abort_check():
        time.sleep(seconds)
        return
    end = time.time() + seconds
    while time.time() < end:
        if _abort_check():
            raise StopRequested("已请求停止")
        time.sleep(0.2)


# 连接复用：每次新建 TCP/TLS 连接（requests.post 直连）在跨网场景下每个请求
# 都要白付一次握手延迟，一章几十个请求累计非常可观（qwen code / dsh 均复用连接池）。
# 用每线程一个 Session 复用连接：线程安全（并发推理各线程独立），连接池自动管理。
_thread_local = threading.local()


def _endpoint(base_url, path):
    """OpenAI 兼容端点智能拼接（v0.56 修复 vibecoding 配置粘过来导致的 404）：

    ① base_url 填「网关根」（如 https://token.sensenova.cn/v1）→ 自动拼 /chat/completions；
    ② base_url 直接填了完整端点（vibecoding/第三方工具的习惯，
       如 https://token.sensenova.cn/v1/chat/completions）→ 不再重复拼——
       否则会拼出 /chat/completions/chat/completions → HTTP 404。
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith(path):
        return base
    return base + path


def _session():
    s = getattr(_thread_local, "sess", None)
    if s is None:
        s = requests.Session()
        s.verify = False
        _thread_local.sess = s
    return s


def profile_by_name(name):
    """按配置名取 API 配置（拆书/导入单独指定 API 用）。不存在返回 None。"""
    if not (name or "").strip():
        return None
    cfg = config.load_config()
    for p in cfg.get("api_profiles", []) or []:
        if p.get("name") == name:
            return p
    return None


def _parse_model_list(data):
    """从 /models 响应里解析模型列表，尽量提取每模型上下文长度。

    兼容 data.data / data.models / 顶层列表 / 嵌套 dict（如 {"data": {"list": [...]}}）等
    多种结构；模型条目可能是字符串或 dict（id/model 键），dict 键即模型 id 也支持，
    单模型对象（{"id": ...} 无外层列表）按单个处理。
    返回 (ids, contexts)：ids=[model_id,...]，contexts={model_id: context_int}。
    """
    if isinstance(data, list):
        raw = data
    elif isinstance(data, dict):
        raw = data.get("data")
        if isinstance(raw, dict):
            for k in ("list", "models", "items", "data", "result"):
                v = raw.get(k)
                if isinstance(v, list):
                    raw = v
                    break
            else:
                if raw.get("id") or raw.get("model"):
                    raw = [raw]             # 单个模型对象
                else:
                    raw = list(raw.keys())  # dict 键即模型 id（部分网关）
        elif raw is None:
            raw = data.get("models")
            if isinstance(raw, dict):
                for k in ("list", "models", "items"):
                    v = raw.get(k)
                    if isinstance(v, list):
                        raw = v
                        break
        if not isinstance(raw, list):
            raw = []
    else:
        raw = []
    ids, contexts = [], {}
    for m in raw:
        if isinstance(m, str):
            mid = m.strip()
            if mid:
                ids.append(mid)
            continue
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or m.get("model") or "").strip()
        if not mid:
            continue
        ids.append(mid)
        for key in ("context_window", "context_length", "max_context_length",
                    "max_model_len", "context_size", "context_tokens"):
            v = m.get(key)
            if v is not None:
                try:
                    contexts[mid] = int(v)
                except (TypeError, ValueError):
                    pass
                break
    return ids, contexts


def fetch_models_detailed(base_url, api_key, timeout=None):
    """拉取模型列表并尝试解析各模型上下文长度。

    返回 {"models": [model_id,...] 排序去重, "contexts": {model_id: context}}。
    网关不提供上下文信息时 contexts 为空；失败抛 LLMError。
    base_url 已含 /v1 时只试 /models，否则依次试 /models 与 /v1/models。
    timeout 默认跟随设置页「请求超时」（v0.76：不再用 15 秒硬编码——慢网关/冷启动
    拉取列表 15 秒内没响应就失败，纯属自缚手脚）。
    """
    if timeout is None:
        timeout = float(config.load_config().get("request_timeout", 300) or 300)
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise LLMError("未填写 API 地址（base_url）。")
    if not (api_key or "").strip():
        raise LLMError("未填写 API Key。")
    # 兼容完整端点填法（vibecoding 习惯）：base_url 已含 /models 则直接用
    if base.endswith("/models"):
        candidates = [base]
    else:
        candidates = [base + "/models"]
        v1 = base + "/v1/models"
        if v1 != candidates[0]:
            candidates.append(v1)
    last_err = "无可用响应"
    for url in candidates:
        try:
            r = _session().get(
                url, headers={"Authorization": "Bearer %s" % api_key.strip()},
                timeout=timeout)
            if r.status_code in (401, 403):
                raise LLMError("拉取模型失败：%s 返回 HTTP %s（Key 无效或无权访问）"
                               % (url, r.status_code))
            if r.status_code != 200:
                last_err = "%s 返回 HTTP %s" % (url, r.status_code)
                continue
            ids, contexts = _parse_model_list(r.json())
            if ids:
                return {"models": sorted(set(ids)), "contexts": contexts}
            last_err = "%s 响应中无模型列表" % url
        except LLMError:
            raise   # 授权失败等已明确的原因直接抛出，不再试后续候选
        except Exception as e:
            last_err = "%s：%s" % (url, e)
    raise LLMError("拉取模型失败：%s" % last_err)


def fetch_models(base_url, api_key, timeout=None):
    """从 OpenAI 兼容网关拉取可用模型列表（GET /models）。

    返回 [model_id, ...] 排序去重；失败抛 LLMError。base_url 已含 /v1 时只试
    /models，否则依次试 /models 与 /v1/models（部分网关两种路径均可）。
    timeout 默认跟随设置页「请求超时」。
    """
    return fetch_models_detailed(base_url, api_key, timeout)["models"]


def chat(messages, temperature=None, max_tokens=None, json_mode=False,
         timeout=None, retries=None, role="all", profile=None, on_chunk=None,
         think_role=None, on_think=None):
    """发起一次完全独立的对话请求。messages 必须由调用方携带完整上下文。

    role: all | decide | reason | write —— 按用途从多 API 配置中挑一个 profile。
    profile: 显式指定要用的 API 配置名（v0.56 拆书可单独选 API，绕过用途分工）。
             None = 按 role 走 pick_profile。
    on_chunk: v0.88 AI 对话页流式回调——每个 SSE content 分片到达时调用 on_chunk(片段)，
             实现「打字机式」实时显示；默认 None（既有调用方完全不受影响）。
    on_think: v1.43 AI 对话页思考气泡回调——模型先输出的推理思考
             （reasoning_content）分片逐段回调（可折叠思考气泡实时展示）；
             模型没有思考时永远不回调；默认 None（既有调用方完全不受影响）。
    think_role: v0.94 思考强度按功能——优先查 config role_thinking[think_role]，
               否则 role_thinking[role]，为空跟随全局 reasoning_effort。
               （拆书/导入/文风/对话/Agent 等用 profile 显式名时 role 恒为 all，
               需传 think_role 指定功能键才能命中各自的思考强度行。）
    """
    cfg = config.load_config()
    if profile is not None:
        prof = None
        for p in cfg.get("api_profiles", []) or []:
            if p.get("name") == profile:
                prof = p
                break
        if prof is None:
            prof = cfg.get("break_profile_obj") if isinstance(cfg.get("break_profile_obj"), dict) else None
        if not prof:
            raise LLMError("拆书指定的 API 配置「%s」不存在，请到设置页检查。" % profile)
    else:
        prof = config.pick_profile(role)
    if not prof or not (prof.get("api_key") or "").strip():
        raise LLMError("未设置 API Key，请先在「设置·API 配置」中填写并启用。")
    base_url = (prof.get("base_url") or "").strip().rstrip("/")
    api_key = (prof.get("api_key") or "").strip()
    if not base_url:
        raise LLMError("配置「%s」未设置 API 地址（base_url）。" % prof.get("name", "?"))

    url = _endpoint(base_url, "/chat/completions")
    if not url:
        raise LLMError("配置「%s」未设置 API 地址（base_url）。" % prof.get("name", "?"))
    # max_tokens 收敛：取「用户设置」与「环节传入值」的较小者——
    # 用户设 102400 这类超大值时，网关按 max_tokens 占用限流配额（tpm），
    # 1 个请求就烧掉整分钟配额 → 必 429（Qwen Code 等工具 max_tokens 合理所以不触发）。
    # 收敛后的环节值（8000/12500/16000）对对应环节足够，不会截断；真被截断还有 length 翻倍兜底。
    if max_tokens is not None and cfg.get("max_tokens"):
        mt = min(int(cfg.get("max_tokens")), int(max_tokens))
    elif max_tokens is not None:
        mt = max_tokens
    else:
        # v0.75 不限制：调用方不传 max_tokens（如 chat_json 默认）时不再收敛到用户设置，
        # payload 不带 max_tokens → 网关/模型自己决定输出长度（本地大上下文模型随便
        # 输出，自己会停；云端网关也有服务端默认上限，不会无限）。
        mt = None
    payload = {
        "model": prof.get("model") or "deepseek-chat",
        "messages": messages,
        "temperature": float(temperature if temperature is not None else cfg.get("temperature", 1.0)),
        # 用流式请求：部分网关（如商汤 token.sensenova.cn）对非流式返回空内容或 429，
        # 流式（SSE）是兼容度最高的调用方式（Qwen Code 等工具均走流式）。
        "stream": True,
    }
    if mt:
        payload["max_tokens"] = int(mt)
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    # 推理思考强度（参考 dsh 的 reasoning_effort）：None/空 = 不传、跟随 API 默认。
    # 推理模型不控制思考时每个请求先想很久（慢 + 消耗配额）；JSON 环节设 low/off 可显著提速。
    # v0.94 按功能覆盖：role_thinking[think_role or role] 非空时优先，否则全局。
    _rt = cfg.get("role_thinking") or {}
    _effort = _rt.get(think_role or role) or ""
    if not _effort:
        _effort = cfg.get("reasoning_effort")
    if _effort:
        payload["reasoning_effort"] = _effort

    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }

    def _do_post():
        """发起请求并读取响应正文。优先解析 SSE 流；非 SSE（完整 JSON）兜底。

        返回 (status, text, finish_reason, saw_reasoning)。
        finish_reason 为 "length" 表示输出被 max_tokens 截断；
        saw_reasoning 表示模型先输出了 thinking（reasoning_content）——推理模型的
        思考会消耗输出预算，正文可能因此为空，调用方按"预算截断"翻倍上限重试。
        """
        resp = _session().post(url, json=payload, headers=headers, timeout=timeout_s,
                               stream=True)
        if resp.status_code != 200:
            # 用 bytes 强制 UTF-8 解码：resp.text 会按 requests 猜的编码（可能
            # 无 charset 头时猜成 latin-1）解码，中文错误信息会乱码。
            return resp.status_code, resp.content.decode("utf-8", errors="replace"), None, False
        # v1.59 立即停止：注册活跃响应；外部 abort_active_resps() close 连接
        # 会让阻塞的流式读取抛 ConnectionError → 下方转 StopRequested。
        _register_resp(resp)
        try:
            parts = []
            finish_reason = None
            current = ""
            saw_sse = False
            saw_reasoning = False
            # decode_unicode=False 拿原始 bytes，再强制 UTF-8 解码：
            # requests 的 iter_lines(decode_unicode=True) 依赖猜编码（无 charset 头时
            # 常误判 latin-1），中文正文会被解成乱码（UTF-8 字节按单字节码页解读）。
            for raw in resp.iter_lines(decode_unicode=False):
                # v0.55 果断停止：用户点停止 → 立即断开当前请求连接，丢弃半成品
                if _abort_check():
                    resp.close()
                    raise StopRequested("已请求停止")
                line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
                if not line:
                    if current:
                        saw_sse = True
                        data = current
                        current = ""
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except Exception:
                            # 单块解析失败：容忍多行 data / 内容含未转义换行等异常，
                            # 将该行原文并入（防止丢块导致 JSON 残缺），由 extract_json 兜底
                            parts.append(data)
                            continue
                        if isinstance(obj, dict) and obj.get("error"):
                            # v0.69 网关在流中返回错误（如 llama.cpp "Model is unloaded."）
                            # 立即报错，不再静默吞掉返回空内容
                            raise LLMError("网关流式返回错误：%s" % _err_text(obj["error"]))
                        choices = obj.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta") or {}
                            # v0.74 推理模型：记录 thinking（reasoning_content）出现；正文在
                            # 思考后由 content 输出。不中断本次请求——llama.cpp 类网关每次请求
                            # 都从思考开始（首个 chunk 毫秒级到达、完整输出却要几十秒），
                            # 见了就中断等于把完整生成掐断、浪费已经在跑的计算。
                            # 预算不足（思考把 max_tokens 吃光）时由调用方在完整响应后翻倍重来。
                            if delta.get("reasoning_content") is not None:
                                saw_reasoning = True
                                if on_think:
                                    on_think(delta["reasoning_content"])
                            piece = delta.get("content")
                            if piece:
                                parts.append(piece)
                                if on_chunk:
                                    on_chunk(piece)
                            fr = choices[0].get("finish_reason")
                            if fr:
                                finish_reason = fr
                    continue
                if line.startswith("data:"):
                    chunk = line[5:].strip()
                    if current:
                        # 一个事件跨多行（异常但容忍）：续接到当前 data
                        current += chunk
                    else:
                        current = chunk
                elif current:
                    # data 事件内的非 data 行（被真实换行拆开）：续接
                    current += line
            if current:
                saw_sse = True
                data = current
                if data != "[DONE]":
                    try:
                        obj = json.loads(data)
                    except Exception:
                        parts.append(data)
                        obj = None
                    if isinstance(obj, dict) and obj.get("error"):
                        raise LLMError("网关流式返回错误：%s" % _err_text(obj["error"]))
                    choices = (obj or {}).get("choices") or []
                    if choices:
                        delta = choices[0].get("delta") or {}
                        if delta.get("reasoning_content") is not None:
                            saw_reasoning = True
                        piece = delta.get("content")
                        if piece:
                            parts.append(piece)
                            if on_chunk:
                                on_chunk(piece)
                        if choices[0].get("finish_reason"):
                            finish_reason = choices[0]["finish_reason"]
            if saw_sse:
                return 200, "".join(parts), finish_reason, saw_reasoning
            # 非 SSE：网关直接返回完整 JSON
            body = resp.content.decode("utf-8", errors="replace")
            try:
                obj = json.loads(body)
            except Exception:
                return 200, body, None, False
            if isinstance(obj, dict) and obj.get("error"):
                raise LLMError("网关返回错误：%s" % _err_text(obj["error"]))
            try:
                msg = obj["choices"][0]["message"]
                content = msg.get("content") or ""
                if msg.get("reasoning_content") is not None:
                    saw_reasoning = True
                    if on_think:
                        on_think(str(msg.get("reasoning_content") or ""))
                if on_chunk and content:
                    on_chunk(content)
                return 200, content, None, saw_reasoning
            except Exception:
                return 200, body, None, False
        except StopRequested:
            raise
        except requests.exceptions.ChunkedEncodingError:
            # 连接被 abort 主动 close（点停止）→ 立即转停止，不当作网络失败重试
            if _abort_check():
                raise StopRequested("已请求停止")
            raise
        except requests.exceptions.ConnectionError:
            if _abort_check():
                raise StopRequested("已请求停止")
            raise
        finally:
            _unregister_resp(resp)

    tries = int(retries if retries is not None else cfg.get("retry_times", 3))
    timeout_s = float(timeout if timeout is not None else cfg.get("request_timeout", 300))
    retry_interval = max(0.5, float(cfg.get("retry_interval", 3) or 3))   # 重试间隔（秒）
    rate_min_wait = max(0.5, float(cfg.get("rate_limit_min_wait", RATE_LIMIT_MIN_WAIT) or RATE_LIMIT_MIN_WAIT))
    # 统一重试：429/5xx/超时/网络错误全部按 tries 次尝试、固定间隔重试——
    # 用户设置的「重试次数」「重试间隔」对限流同样生效（429 额外保证最小等待
    # rate_min_wait，因为限流窗口按分钟计，等太短没意义；可在设置页调整）。
    last_err = None
    max_mt = int(payload.get("max_tokens") or 0)
    # 当服务端通过 400 错误告知 max_tokens 上限时记录，之后翻倍/降档都以它为准
    server_mt_max = None
    max_mt_cap = max_mt * 8 if max_mt else 0
    # v1.38 兼容：reasoning_effort 参数被网关拒绝（400）时去掉该参数重试一次。
    # 本地网关（LM Studio/llama.cpp）大多不认 OpenAI 的 reasoning_effort，
    # 用户一旦在设置页设了思考强度（全局或某功能行），请求就带该参数 → 400 报错。
    _effort_dropped = False
    for attempt in range(max(1, tries)):
        if _abort_check():
            raise StopRequested("已请求停止")
        try:
            # 预算升级内层循环（v0.74）：推理模型 thinking 中断 / 输出被截断 → 翻倍
            # max_tokens 再试。这是"预算升级"不是"失败重试"，不消耗 tries 次数——
            # 设置页重试次数=1 时推理模型也应正常（翻倍后一次成功）。
            while True:
                status, text, finish, saw_reasoning = _do_post()
                if status != 200:
                    break
                # 推理模型适配：思考（reasoning_content）与正文共享 max_tokens 预算，
                # _do_post 一见到 thinking 就中断本次请求（saw_reasoning + 空正文），
                # 这里立即翻倍 max_tokens 重来（不等它吃完预算白等）；正文在思考后输出。
                # 仍空才显式报错，绝不静默返回空正文（避免空章/空 JSON 假完成）。
                budget_eaten = saw_reasoning and not text
                if (budget_eaten or finish == "length") and max_mt:
                    limit = server_mt_max or max_mt_cap
                    if max_mt < limit:
                        # thinking 中断不用等；普通截断稍等一拍再重试
                        max_mt = min(limit, max_mt * 2)
                        payload["max_tokens"] = max_mt
                        if not budget_eaten:
                            _abort_sleep(0.6)
                        continue
                if not text:
                    raise LLMError(
                        "模型未返回有效内容（推理模型思考过程占满输出预算，"
                        "已尝试加大 max_tokens 仍无正文）。可在「设置·API 配置」"
                        "为该配置关闭/调低思考强度，或改用非推理模型。")
                return text
            if status == 400:
                # v1.38 兼容：本地/第三方网关不认 reasoning_effort 参数（LM Studio/llama.cpp
                # 大多报 400 参数不支持）——用户一旦设置思考强度就带该参数，去掉后重试一次，
                # 与 max_tokens 400 降档同款逻辑；商汤等支持该参数的网关不受影响（不会 400）。
                if not _effort_dropped and payload.get("reasoning_effort"):
                    payload.pop("reasoning_effort", None)
                    _effort_dropped = True
                    _abort_sleep(0.5)
                    continue
                # 服务端拒绝 max_tokens（如超出模型合法范围 [1, 393216]）：
                # 从错误消息提取合法上限，降档重试一次，避免用户设置值直接失败
                m = re.search(
                    r"max_tokens.{0,40}?\[\s*(\d+)\s*,\s*(\d+)\s*\]", text)
                if m:
                    try:
                        upper = int(m.group(2))
                    except Exception:
                        upper = None
                    if upper:
                        server_mt_max = upper
                        if payload.get("max_tokens") and int(payload["max_tokens"]) > upper:
                            payload["max_tokens"] = upper
                            _abort_sleep(1)
                            continue
            if status == 429:
                last_err = LLMError(
                    "HTTP 429 限流（服务端 tpm/rpm 超限）：%.120s"
                    "（若此前一直正常，多为同一 API Key 被多个应用/会话共享争抢额度；"
                    "将按设置的重试间隔自动重试，共 %d 次尝试）" % (text, tries))
                if attempt < tries - 1:
                    _abort_sleep(max(rate_min_wait, retry_interval))
                    continue
                raise last_err
            if status in (500, 502, 503, 504):
                last_err = LLMError("HTTP %d: %.120s" % (status, text))
                if attempt < tries - 1:
                    _abort_sleep(retry_interval)
                    continue
            if status in (400, 404):
                # 404/400 最常见原因：base_url 把完整端点（vibecoding 习惯）填进来了，
                # 或模型名/网关路径不对——给明确排查提示而不是一串裸错误
                raise LLMError(
                    "HTTP %d: %.160s\n排查提示：① 若 base_url 填的是完整端点"
                    "（如 .../chat/completions，vibecoding 习惯）已自动兼容，无需改；"
                    "② 检查「设置·API 配置」里该配置的 base_url 与模型名——可在设置页点"
                    "「拉取模型」看可用列表；③ 火山引擎豆包模型名需填端点 ID（ep-xxxx）。"
                    % (status, text))
            raise LLMError("HTTP %d: %.300s" % (status, text))
        except StopRequested:
            raise
        except requests.exceptions.Timeout:
            last_err = LLMError("请求超时（%ds）" % timeout_s)
            if attempt < tries - 1:
                _abort_sleep(retry_interval)
                continue
        except requests.exceptions.ConnectionError as e:
            last_err = LLMError("网络连接失败：%s" % (e or "无法连接到 API 地址"))
            if attempt < tries - 1:
                _abort_sleep(retry_interval)
                continue
        except LLMError:
            raise
        except Exception as e:
            raise LLMError("请求异常：%s" % e)
    raise last_err or LLMError("请求失败")


def extract_json(text):
    """从模型输出中稳健地提取 JSON 对象。"""
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, min(len(text), start + MAX_JSON_CHARS)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except Exception:
                    return None
    return None


def chat_json(system, user, temperature=None, max_tokens=None,
              timeout=None, retries=None, tag="json", role="all", profile=None,
              think_role=None):
    """请求 JSON 输出：默认不带 response_format（部分网关如商汤返回坏内容或报错），
    靠 extract_json 解析（支持 ```json 代码块）。

    v0.71 内容级重试：模型偶发返回**坏 JSON（解析失败）**属于瞬时错误——重新请求一次
    极大概率输出合格——自动重试（次数与设置页「重试次数」一致，默认 3），而非直接报错
    停下等用户手动重试；网络类错误（429/5xx/超时/网关 error chunk）已在 chat 内部按
    retries 重试，此处不重复处理（保持原样抛错）。仍失败才用 response_format 兜底一轮。

    JSON 环节（决断/推理/校验/战后/压缩/建卡等）输出都很小，未显式传 max_tokens 时
    默认**不限制**（v0.75：不设小预算卡推理模型的思考；网关/模型自己决定输出长度，
    提取到 JSON 即成功，云端也有服务端默认上限不会无限）。
    """
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    _cfg = config.load_config()
    attempts = max(1, int(retries if retries is not None
                          else _cfg.get("retry_times", 3) or 3))
    last_text = ""
    # 第一轮起循环：不带 response_format（兼容商汤等网关），extract_json 解析；
    # 解析失败 = 内容不合格（瞬时）→ 重新请求；网络/网关错误保持原样抛错。
    for _ in range(attempts):
        try:
            text = chat(messages, temperature=temperature, max_tokens=max_tokens,
                        json_mode=False, timeout=timeout, retries=retries, role=role,
                        profile=profile, think_role=think_role)
            last_text = text or ""
            data = extract_json(last_text)
            if data is not None:
                return data
        except LLMError as e:
            if "response_format" in str(e) or "BadRequest" in str(e):
                break  # 服务端明确拒绝非 json_mode → 下面走 response_format 兜底
            raise
    # 兜底：带 response_format 再试一轮（有的网关只认 json_mode）
    try:
        text = chat(messages, temperature=temperature, max_tokens=max_tokens,
                    json_mode=True, timeout=timeout, retries=retries, role=role,
                    profile=profile)
        last_text = text or ""
        data = extract_json(last_text)
        if data is not None:
            return data
    except LLMError:
        pass  # 以解析失败提示为准
    raise LLMError("模型未返回有效 JSON（tag=%s）：%.300s" % (tag, (last_text or "")[:300]))


def chat_text(system, user, temperature=None, max_tokens=None,
              timeout=None, retries=None, role="all", tag="text", profile=None,
              on_chunk=None, think_role=None):
    """请求纯文本输出。tag 仅用于日志标识，不影响请求。"""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    return chat(messages, temperature=temperature, max_tokens=max_tokens,
                json_mode=False, timeout=timeout, retries=retries, role=role,
                profile=profile, on_chunk=on_chunk, think_role=think_role).strip()