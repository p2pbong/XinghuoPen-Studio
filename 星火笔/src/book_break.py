# -*- coding: utf-8 -*-
"""拆书引擎（v0.55 双端：PC/安卓复用）：对超长小说 txt 进行拆书分析，产出小说设计细纲。

核心思路（应对 3000 章级长文 + 维系整体性）：
  L1 骨架先行：全本书只读「卷结构 + 每卷开头样本 + 全部章节标题分批复用」，
     由主AI归纳整体主线 / 核心人物 / 全局伏笔线索池 / 世界观关键词——先立骨架，后续每卷细纲都基于骨架展开；
  L2 逐卷细纲：每卷「章节标题 + 每章开头样本（约400字）」→ 该卷事件拆分（起止章/章数/推动方式/冲突/伏笔埋收/日常式伏笔/高潮点）；
  L3 汇总压缩：骨架 + 各卷细纲 → 拼装成 ≤5 万字的拆书文档（含卷事件细纲、人物设计、伏笔总表、剧情推动技法总结），
     并单独产出「设计技法学习文本」（供主AI学习怎么推动剧情/埋设伏笔，不照抄情节）。

适用范围：txt 长文（支持“第X卷/第X章/序章/楔子/尾声/番外”等常见标题与纯数字编号）；
无卷标的长文自动按固定章数分卷（默认 120 章/卷），保证单次 LLM 调用体量可控、可中途停止。
"""
import json
import os
import re
import threading
import time

import config
import llm

# ---------- 自动重试（v0.70：LLM 环节失败自动重跑，不再停下等用户手动重试） ----------
RETRY_TIMES = 3     # 每个环节最多尝试次数（1 次初始 + 2 次自动重试）
RETRY_DELAY = 2.0   # 重试间隔（秒）：给瞬时错误/网关限流喘息时间


def _retry_llm(fn, log=None, label="LLM 调用"):
    """调用 LLM 环节函数；LLMError 自动重试（最多 RETRY_TIMES 次），仍失败抛最后一次异常。

    StopRequested 立即传播（用户主动停止不重试）。测试可临时把 RETRY_DELAY 置 0 加速。
    """
    last = None
    for attempt in range(RETRY_TIMES):
        try:
            return fn()
        except llm.StopRequested:
            raise
        except llm.LLMError as e:
            last = e
            if log and attempt < RETRY_TIMES - 1:
                log("warn", "%s 第 %d/%d 次调用失败：%s，自动重试…"
                    % (label, attempt + 1, RETRY_TIMES, str(e)[:120]))
            if attempt < RETRY_TIMES - 1:
                time.sleep(RETRY_DELAY)
    raise last

# ---------- 风格库 ----------------
CHARS_PER_HEAD = 400     # 每章开头采样字数（喂给卷细纲）
CHARS_PER_TAIL = 200     # 每章结尾采样字数（帮主AI感知章末钩子）
TITLE_BATCH = 400        # 章节标题流分批（每批标题数，由 token 预算推导）
AUTO_VOLUME = 120        # 无卷标时自动分卷章数（由 token 预算推导）
FALLBACK_BLOCK_LINES = 800   # v1.49 无任何章节标题时的兜底分块行数（拆书/导入至少按块分析）
DOC_MAX_CHARS = 80000    # 拆书文档上限（v0.58 加厚：给足冗余，尽量保留细节）
LEARN_MAX_CHARS = 6000   # 注入主AI的学习文本上限
# v0.58 高级模式上限：现代大上下文（262144 / 1M）下不再卡小预算
TOKEN_PER_PART_MAX = 2000000    # 每部分 token 上限（高级模式）
OVERLAP_TOKEN_MAX = 1000000     # 每部分重叠 token 上限（高级模式，0=不重叠）
L3_BATCH_MAX = 60               # L3 分批汇总：每批最多卷/单元数（0=一次合并全部）
# v0.63 智能模式三档：按模型上下文长度自动定每部分大小（占上下文的百分比）
# 用户 2026-10-03 调整：激进 40%→70%、正常 25%→50%、保守 12%→30%（更激进，长文拆更快）
SMART_SUBS = {"conservative": 0.30, "balanced": 0.50, "aggressive": 0.70}
DEFAULT_CONTEXT = 262144        # 探测不到上下文时的兜底（现代主流大上下文）
MIN_SMART_TOKEN = 8000          # 智能模式每部分 token 下限（再稳也有基本体量）
GENERIC_TITLE_RATIO = 0.5       # 章节标题「无意义」比例超过它 → L1 改用每章开头采样
HEAD_FOR_TITLE = 80             # L1 无意义标题时每章带的开头采样字数
# v0.56 预算换算：中文约 1.6 字/token（保守估算，含标题与结构开销）
TOKENS_PER_CHAR = 1.6
BUDGET_SAFETY = 0.75     # 预算安全系数：只按 75% 预算切分，给输出留空间


def break_settings():
    """拆书专用设置（来自 config.json，v0.56 / v0.56+ 导入设置；v0.58 加三档模式；v0.59 智能模式三档子模式）：
    返回 {"mode","smart_sub","model_context","profile","token_per_part","overlap_token",
          "l3_batch","parallel","parallel_n","prompt","import_profile","import_intro"}。
    全部有默认值，未配置时行为与旧版一致（智能/正常、串行）。
    """
    cfg = config.load_config()
    mode = str(cfg.get("break_mode") or "smart").strip()
    if mode not in ("simple", "smart", "advanced"):
        mode = "smart"
    sub = str(cfg.get("break_smart_sub") or "balanced").strip()
    if sub not in SMART_SUBS:
        sub = "balanced"
    return {
        "mode": mode,
        "smart_sub": sub,
        "model_context": max(0, int(cfg.get("model_context_window") or 0)),
        "profile": str(cfg.get("break_profile") or "").strip(),
        "token_per_part": max(1000, int(cfg.get("break_token_per_part") or 8000)),
        "overlap_token": max(0, int(cfg.get("break_overlap_token") or 0)),
        "l3_batch": max(0, min(L3_BATCH_MAX, int(cfg.get("break_l3_batch") or 0))),
        "parallel": bool(cfg.get("break_parallel")),
        "parallel_n": max(1, min(8, int(cfg.get("break_parallel_n") or 2))),
        "prompt": str(cfg.get("break_prompt") or "").strip(),
        # v0.56 小说导入成项目：单独 API（默认跟随拆书）+ 小说整体规划（剧情设计/方向/未完成部分）
        "import_profile": str(cfg.get("import_profile") or "").strip(),
        "import_intro": str(cfg.get("import_intro") or "").strip(),
    }


# v0.59 智能模式：按模型上下文长度自动定每部分 token（保守/正常/激进三档）
def context_with_source(settings):
    """智能模式生效的模型上下文长度 + 来源说明：
    ① 手填 model_context > 0 → ("手动", ctx)；
    ② 拆书专用配置/当前配置「拉取模型」记下的 context_window → ("拉取模型记录", ctx)；
    ③ 兜底 DEFAULT_CONTEXT（262144）。
    """
    ctx = int(settings.get("model_context") or 0)
    if ctx > 0:
        return ctx, "手动"
    name = str(settings.get("profile") or "").strip() or None
    prof = llm.profile_by_name(name) if name else None
    if prof is None:
        try:
            prof = config.pick_profile("all")
        except Exception:
            prof = None
    if prof:
        try:
            pw = int(prof.get("context_window") or 0)
        except (TypeError, ValueError):
            pw = 0
        if pw > 0:
            return pw, "拉取模型记录"
    return DEFAULT_CONTEXT, "默认 262144（未探测到上下文，可在智能模式手填）"


def known_context(settings):
    """智能模式生效的模型上下文长度（仅数值）。"""
    return context_with_source(settings)[0]


def smart_token_per_part(settings, ctx=None):
    """智能模式每部分 token = 上下文 × 档位比例（保守30% / 正常50% / 激进70%），
    再夹紧 [8000, 200 万]。1M 上下文激进档 ≈ 73 万 token（×0.75 安全系数后输入约占
    上下文 52%，留给输出充足余量）；262144 三档 ≈ 7.9 万 / 13.1 万 / 18.4 万
    （稳/均衡/快速）。
    """
    ctx = ctx or known_context(settings)
    frac = SMART_SUBS.get(settings.get("smart_sub") or "balanced", 0.50)
    return max(MIN_SMART_TOKEN, min(TOKEN_PER_PART_MAX, int(ctx * frac)))


def effective_token(settings):
    """实际生效的每部分 token：简单/高级用手填 token；智能模式按上下文自动定。"""
    mode = settings.get("mode") or "smart"
    if mode == "smart":
        return smart_token_per_part(settings)
    return max(1000, int(settings.get("token_per_part") or 8000))


def effective_l3_batch(settings, ctx=None, per_c=5, n_units=0):
    """L3 汇总每批单元数：高级模式用手填 l3_batch（0=一次合并）；
    智能模式自动判断——按「每单元 L2 输出约占该单元输入的 12%」估算，
    让每批输入 ≤ 上下文 40%（保守起见再乘 0.8），单元数不多时一次合并即可。
    """
    mode = settings.get("mode") or "smart"
    if mode != "smart":
        return max(0, min(L3_BATCH_MAX, int(settings.get("l3_batch") or 0)))
    if n_units <= 0:
        return 0
    ctx = ctx or known_context(settings)
    per_ch = int((CHARS_PER_HEAD + CHARS_PER_TAIL + 40) * TOKENS_PER_CHAR)
    est_unit_out = max(2000, int(per_c * per_ch * 0.12))   # L2 输出约占输入 12%
    batch = max(1, int(ctx * 0.40 * 0.8 / est_unit_out))
    return min(L3_BATCH_MAX, batch) if n_units > batch else 0


def chapters_per_part(settings):
    """按「每部分 token 预算」推导每部分应包含多少章（含标题+头尾采样）。

    每章 ≈ 标题40字 + 头400字 + 尾200字 ≈ 640 字 × 1.6 token/字 ≈ 1024 token；
    预算×安全系数后整除即可。至少 1 章。
    v0.58 高级模式不设引擎上限（UI 已放开到 200 万 token），由用户自行把握上下文。
    """
    budget = int(settings.get("token_per_part") or 8000) * BUDGET_SAFETY
    per_ch = int((CHARS_PER_HEAD + CHARS_PER_TAIL + 40) * TOKENS_PER_CHAR)
    return max(1, int(budget / per_ch)) if per_ch else AUTO_VOLUME


def overlap_chapters(settings):
    """高级模式「每部分重叠 token」→ 每部分与下一部分重叠的章数（保证相邻批次衔接连贯）。

    重叠章数 = 重叠预算×安全系数 ÷ 每章采样 token；至少 0 章。
    """
    budget = int(settings.get("overlap_token") or 0) * BUDGET_SAFETY
    per_ch = int((CHARS_PER_HEAD + CHARS_PER_TAIL + 40) * TOKENS_PER_CHAR)
    return max(0, int(budget / per_ch)) if per_ch else 0


def titles_per_part(settings, generic_titles=False):
    """按预算推导每批标题数。

    正常：每条标题≈30字×1.6≈48 token；
    v0.59 无意义章节名：每条带「开头采样 ≈80 字」→ ≈(30+80)×1.6≈176 token，批数相应变小。
    """
    budget = int(settings.get("token_per_part") or 8000) * BUDGET_SAFETY
    per_t = int((30 + (HEAD_FOR_TITLE if generic_titles else 0)) * TOKENS_PER_CHAR)
    return max(20, int(budget / per_t)) if per_t else TITLE_BATCH


def _user_break_prompt(settings):
    """可选的拆书总体提示词（用户大方向：关注日常/人物/脑洞/哲思等）。空串=不影响。"""
    return str((settings or {}).get("prompt") or "").strip()


def breaks_dir():
    """风格库目录（延迟求值：安卓 bootstrap 会重定位 config.DATA_DIR）。"""
    return os.path.join(config.DATA_DIR, "breaks")


# ---------- 断点续传（v0.55：拆书/小说导入成项目可续传） ----------
def jobs_base_dir():
    """任务断点续传目录（data/jobs/，与风格库同基目录，安卓 bootstrap 重定位生效）。"""
    return os.path.join(config.DATA_DIR, "jobs")


def job_dir_for(text, settings=None, title="", label="job"):
    """为一次可续传任务生成 job 目录。

    同一文本 + 同一关键设置（token 预算/并行/提示词）→ 同一目录（下次启动自动续传）；
    设置或文本变了 → 新目录（旧的不再命中，由 cleanup_jobs 兜底清理）。
    """
    import hashlib
    s = settings or {}
    key = "%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s" % (
        text or "", label, title or "",
        s.get("mode"), s.get("smart_sub"), s.get("model_context"),
        s.get("token_per_part"), s.get("overlap_token"),
        s.get("l3_batch"), s.get("parallel"), s.get("parallel_n"),
        s.get("import_intro") or "")
    h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    d = os.path.join(jobs_base_dir(), label, h)
    os.makedirs(d, exist_ok=True)
    return d


def cleanup_jobs(keep=20):
    """清理最旧的 job 目录（按修改时间，保留最近 keep 个），防止无限堆积。"""
    try:
        base = jobs_base_dir()
        if not os.path.isdir(base):
            return 0
        dirs = []
        for label in os.listdir(base):
            lp = os.path.join(base, label)
            if os.path.isdir(lp):
                for d in os.listdir(lp):
                    dp = os.path.join(lp, d)
                    if os.path.isdir(dp):
                        dirs.append((os.path.getmtime(dp), dp))
        dirs.sort(key=lambda x: x[0], reverse=True)
        removed = 0
        for _, dp in dirs[keep:]:
            try:
                import shutil
                shutil.rmtree(dp, ignore_errors=True)
                removed += 1
            except OSError:
                pass
        return removed
    except Exception:
        return 0


def rm_job(job_dir):
    """删除一个 job 目录（正常完成/用户放弃时调用）。"""
    if not job_dir:
        return
    try:
        import shutil
        shutil.rmtree(job_dir, ignore_errors=True)
    except OSError:
        pass

_VOL_RE = re.compile(r"^\s*(?:第\s*([0-9一二三四五六七八九十百千万零]+)\s*[卷部篇集]|"
                     r"([一二三四五六七八九十百千万零]+)\s*[卷部篇集])\s*[:：]?\s*(.*)$")
# v1.48 章节识别放宽（用户：整本书几十万字只识别出一章、其他章节全被吞）：
# 支持【第X章】/（第X章）/ [第X话] 等括号包裹、前导装饰符、第X话、数字/中文数字标题
# （如「1.标题」「一、标题」）；裸「第一章」（无副标题）不再被 _SKIP_RE 当装饰线吞掉。
# v1.49 再放宽：行首允许常见装饰符号（☆★※◎●◆◇§№¤ 等网站导出格式，如「☆、第一章 假钞」）
_CH_RE = re.compile(r"^\s*[☆★※◎●◆◇§№¤▽△▲◦·•＊*、，,;；—\-～~ ]*[【\[（(—\-]?\s*(?:"
                    r"第\s*([0-9一二三四五六七八九十百千万零]+)\s*[章节回话]"
                    r"|(序章|楔子|尾声|番外|引子|终章|后记|序言|前传|后传)"
                    r"|([Cc]hapter\s*[0-9]+)"
                    r"|([0-9一二三四五六七八九十百千万零]{1,6})[、.．:：]\s*"
                    r")\s*[】\]）)—\-]?\s*[:：]?\s*(.*)$")
_SKIP_RE = re.compile(r"^\s*(?:目录|简介|内容简介|作品简介|版权|本章[完终]|未完\s*[待稿]?|"
                      r"[——\-—～~·.。]{3,}\s*$)")


def _num(s):
    """中文数字 → int（支持到万）。"""
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    m = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
         "七": 7, "八": 8, "九": 9, "十": 10, "百": 100, "千": 1000, "万": 10000}
    total = 0
    cur = 0
    for ch in s:
        if ch in ("十", "百", "千", "万"):
            cur = cur if cur else 1
            total += cur * m[ch]
            cur = 0
        else:
            cur = m.get(ch, 0)
    return total + cur


def parse_novel(text):
    """解析小说文本 → 卷/章结构（每章只保留 head/tail 采样，供拆书分析）。

    返回 {"volumes": [{"no":1, "title":"", "chapters":[
        {"no":1, "title":"", "head":str(400字), "tail":str(200字), "full_len":int}]}]}
    无法识别任何章节标题时（正文连续无标题），把全文作为一卷一章处理。
    """
    return _parse_structure(text, full=False)


def parse_novel_full(text):
    """解析小说文本 → 卷/章结构，每章保留**完整正文**（供「小说导入成项目」原样入库）。

    返回 {"volumes": [{"no":1, "title":"", "chapters":[
        {"no":1, "title":"", "content":str(完整正文)}]}],
        "total_chars", "total_chapters"}；无标题时同样单卷单章兜底。
    """
    return _parse_structure(text, full=True)


def _parse_structure(text, full=False):
    """分卷分章的公共解析器（full=True 时保留每章完整正文）。"""
    lines = text.split("\n")
    vols = []          # {"no","title","chapters"}
    cur_vol = {"no": 1, "title": "", "chapters": []}
    vols.append(cur_vol)
    cur_title = "第1章"
    ch_no = 0
    buf = []
    seen_title = False   # v1.48 是否已识别到章节/卷标题（区分「开头简介」与「正式章节正文」）

    def flush_chapter():
        nonlocal buf
        if buf:
            body = "\n".join(buf).strip()
            # v1.48 只在已识别到标题后落章：文件开头未遇标题的简介/前言内容不当作章节；
            # _SKIP_RE 只拦「目录/简介/版权/本章完」等真实垃圾行，不再吞裸章节标题
            if seen_title and cur_title and not _SKIP_RE.match(cur_title):
                ch_no_tmp = ch_no
                if full:
                    return {"no": ch_no_tmp, "title": cur_title,
                            "content": body}
                return {"no": ch_no_tmp, "title": cur_title,
                        "head": body[:CHARS_PER_HEAD],
                        "tail": body[-CHARS_PER_TAIL:] if len(body) > CHARS_PER_HEAD else "",
                        "full_len": len(body)}
        return None

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        m_ch = _CH_RE.match(s)
        if m_ch:
            # 先落前章（此时若从未见过标题，则跳过开头简介——cur_title 是默认"第1章"）
            c = flush_chapter()
            if c and cur_vol is not None:
                cur_vol["chapters"].append(c)
            buf = []
            seen_title = True   # v1.48 从这一行起才是正式章节，后续 flush 才落章
            g1, g2, g3, g4 = (m_ch.group(1), m_ch.group(2),
                              m_ch.group(3), m_ch.group(4))
            rest = (m_ch.group(5) or "").strip()
            if g1 is not None:          # 第X章/节/回/话
                real_no = _num(g1)
                if real_no and real_no != ch_no + 1:
                    ch_no = real_no - 1   # 章号异常时以标题为准
                cur_title = rest or ("第%d章" % (ch_no + 1))
            elif g4:                    # 数字/中文数字标题（1.xxx / 一、xxx）
                if not rest:
                    # 形如「1.」单独一行：正文里的编号行，不当章节标题
                    buf.append(s)
                    continue
                real_no = _num(g4)
                if real_no and real_no != ch_no + 1:
                    ch_no = real_no - 1
                cur_title = rest
            elif g3:                    # Chapter N
                cur_title = rest or s
            else:                       # 序章/楔子/尾声…
                if g2 in ("序章", "楔子", "引子"):
                    ch_no = 0
                cur_title = g2
            ch_no += 1
            continue
        m_vol = _VOL_RE.match(s)
        if m_vol:
            # 先落前章（此时若从未见过标题，则跳过开头简介/前言内容）
            c = flush_chapter()
            if c and cur_vol is not None:
                cur_vol["chapters"].append(c)
            buf = []
            seen_title = True   # v1.48 卷标题也是正式标题，后续 flush 才落章
            vol_title = (m_vol.group(3) or "").strip()
            # 若当前卷仍是 v0 那个隐含空卷（无章节无标题），把它升格为真正的第一卷
            if (len(vols) == 1 and not cur_vol["chapters"]
                    and not cur_vol["title"] and cur_vol["no"] == 1):
                cur_vol["title"] = vol_title
            else:
                cur_vol = {"no": len(vols) + 1, "title": vol_title,
                           "chapters": []}
                vols.append(cur_vol)
            cur_title = "第1章"
            ch_no = 0
            continue
        # 普通正文行
        buf.append(s)
    # 收尾
    c = flush_chapter()
    if c and cur_vol is not None:
        cur_vol["chapters"].append(c)

    # 剔除空卷，无卷标的自动分卷
    vols = [v for v in vols if v["chapters"]]
    has_vol_title = any(v["title"] for v in vols) or len(vols) > 1
    if has_vol_title:
        # 保留卷结构（含"第1卷"默认卷）——若全书只有一卷且无卷题，则按自动分卷
        single_no_title = (len(vols) == 1 and not vols[0]["title"])
        if single_no_title:
            chapters = vols[0]["chapters"]
            vols = [{"no": i + 1, "title": "", "chapters": chapters[i:i + AUTO_VOLUME]}
                    for i in range(0, len(chapters), AUTO_VOLUME)]
    else:
        chapters = vols[0]["chapters"] if vols else []
        vols = [{"no": i + 1, "title": "", "chapters": chapters[i:i + AUTO_VOLUME]}
                for i in range(0, len(chapters), AUTO_VOLUME)]
    # v1.49 兜底：识别结果 ≤2 章但文本很大 → 标题格式没被识别（作者乱取名/无标题），
    # 扫描「装饰符短行标题」重新切分；仍无标题则按固定行数分块，避免整本一锅端。
    total_n = sum(len(v["chapters"]) for v in vols)
    if total_n <= 2 and len(text) >= 20000:
        fb_chapters = _fallback_chapters(text, full)
        if fb_chapters:
            vols = [{"no": 1, "title": "", "chapters": fb_chapters}]
    # 直接无标题 → 单卷单章兜底
    if not vols:
        if full:
            vols = [{"no": 1, "title": "", "chapters": [
                {"no": 1, "title": "第1章", "content": text.strip()}]}]
        else:
            vols = [{"no": 1, "title": "", "chapters": [
                {"no": 1, "title": "第1章", "head": text[:CHARS_PER_HEAD],
                 "tail": text[-CHARS_PER_TAIL:], "full_len": len(text)}]}]
    return {"volumes": vols, "total_chars": len(text),
            "total_chapters": sum(len(v["chapters"]) for v in vols)}


def _fallback_chapters(text, full=False):
    """v1.49 章节识别兜底（作者乱取名 / 完全没有章节标题的书）：

    ①扫描「装饰符短行标题」——行首有装饰符号（☆★※◎●◆◇§ 等）、整行 ≤40 字、
    行尾无句末标点、非对话（不以引号开头）→ 视为章节标题重新切分；
    ②若连这样的标题都找不到，按固定行数（FALLBACK_BLOCK_LINES）自动分块，
    让拆书/导入至少按块分析而不是整本一锅端。

    返回章节列表（[{no,title,head,tail,full_len}] 或 full=True 时带 content）；找不到返回 []。
    """
    lines = text.split("\n")
    title_idx = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or len(s) > 40:
            continue
        if s.endswith(("。", "！", "？", "，", "；", "…", ".", "!", "?", "~", "～")):
            continue
        if s.startswith(("“", "「", "『", '"', "'")):
            continue
        if re.match(r"^[☆★※◎●◆◇§№¤▽△▲◦·•＊*、，,;；—\-～~ ]+", s):
            title_idx.append(i)
    chapters = []
    if len(title_idx) >= 2:
        for k, idx in enumerate(title_idx):
            start = idx + 1
            end = title_idx[k + 1] if k + 1 < len(title_idx) else len(lines)
            body = "\n".join(lines[start:end]).strip()
            title = lines[idx].strip()
            if full:
                chapters.append({"no": k + 1, "title": title, "content": body})
            else:
                chapters.append({"no": k + 1, "title": title,
                                 "head": body[:CHARS_PER_HEAD],
                                 "tail": body[-CHARS_PER_TAIL:] if len(body) > CHARS_PER_HEAD else "",
                                 "full_len": len(body)})
        return chapters
    # 无任何标题：按固定行数分块
    block = FALLBACK_BLOCK_LINES
    for b in range(0, len(lines), block):
        body = "\n".join(lines[b:b + block]).strip()
        if not body:
            continue
        if full:
            chapters.append({"no": len(chapters) + 1,
                             "title": "第%d部分" % (len(chapters) + 1),
                             "content": body})
        else:
            chapters.append({"no": len(chapters) + 1,
                             "title": "第%d部分" % (len(chapters) + 1),
                             "head": body[:CHARS_PER_HEAD],
                             "tail": body[-CHARS_PER_TAIL:] if len(body) > CHARS_PER_HEAD else "",
                             "full_len": len(body)})
    return chapters if len(chapters) >= 2 else []


# ---------- LLM 环节（拆书各阶段，mock 友好：测试只替换这四个函数） ----------
def summarize_title_batch(titles, profile=None, user_prompt=""):
    """L1-a：一批章节标题（可能带每章开头采样）→ 摘要 {people:[],events:[],place:[],hints:[]}。

    v0.59：章节标题可能是自动编号（无意义），此时每条带「开头：xxx…」采样——
    提示词明确告知 AI 结合采样推断，不再只看无意义编号。
    """
    sys = ("你是一位资深网文编辑，根据给出的章节标题（或每章开头采样）判断这几章大致讲了什么。"
           "注意：标题可能是自动编号（如「第123章」）没有信息量，此时**以「开头：」后的采样文字为准**"
           "推断这章内容。请归纳出：涉及的主要人物名、发生的核心事件（一句话）、"
           "出现的场景/势力/地点、疑似被反复提及的关键词（可能是伏笔）。"
           "输出 JSON：{\"people\":[...],\"events\":[...],\"place\":[...],\"hints\":[...]}。"
           "不要编造信息。")
    user = "\n".join(titles)
    if user_prompt:
        user += "\n\n【拆书重点（用户指定的大方向，拆书时优先关注）】\n%s" % user_prompt
    data = llm.chat_json(sys, user, tag="break_title", role="decide", profile=profile,
                         think_role="break")
    if isinstance(data, dict):
        return data
    return {}


# v0.59 L1 无意义章节名处理：自动编号（如「第3章」/「Chapter 5」/「1.xxx」/「一、xxx」）
# 或空标题算无意义；v1.48 同步放宽——支持括号/装饰包裹（【第1章】、（第1章）、—第1章—）
_GENERIC_RE = re.compile(r"^(?:[【\[（(—\-]*\s*(?:"
                         r"第\s*[0-9一二三四五六七八九十百千万零]+\s*[章节回话]"
                         r"|chapter\s*[0-9]+"
                         r"|[0-9一二三四五六七八九十百千万零]{1,6}[、.．:：]?"
                         r")\s*[】\]）)—\-]*)$", re.IGNORECASE)


def generic_title_mode(parsed):
    """判断全书章节标题是否多为「自动编号/无意义」：
    （无意义标题章数 / 总章数）≥ GENERIC_TITLE_RATIO → 返回 True（L1 改用开头采样）。
    """
    vols = parsed.get("volumes") or []
    total = 0
    generic = 0
    for v in vols:
        for c in (v.get("chapters") or []):
            t = (c.get("title") or "").strip()
            total += 1
            if not t or _GENERIC_RE.match(t):
                generic += 1
    if total <= 0:
        return False
    return generic / total >= GENERIC_TITLE_RATIO


def build_skeleton(payload, profile=None, user_prompt=""):
    """L1-b：全书骨架（卷列表 + 每卷开头样本 + 标题流摘要）→ 整体主线/人物/伏笔池。"""
    sys = ("你是一位专职拆书的小说设计分析师。请基于给定的超长篇小说「抽样」（卷结构 + "
           "每卷开头章节的片段 + 全书章节标题的分批概览），在**不臆造**的前提下提炼：\n"
           "1) story：全书主线（开局钩子、核心冲突、大致走向，100-200字）；\n"
           "2) arcs：全书的卷/篇章结构——**原书有明确卷就用卷；没有明确卷概念（章节连排/"
           "每卷只是若干章的物理切分）时，由你按剧情阶段自行判卷**（开局→发展→转折→高潮→"
           "收束，每段标注起止章号与卷题）。每段：{start(起止卷号或起止章号), end, "
           "title(卷题,5-15字), task(这阶段的剧情任务/要完成的事,30-80字), "
           "basis(判卷依据：按原书卷标 或 按剧情阶段划分,5-15字)}；\n"
           "3) characters：核心角色 [{name, role(定位,5-15字), arc(人设弧光/成长方向,15-30字), "
           "key_relations(全书级关键关系线：与谁什么关系、矛盾或羁绊焦点是什么,20-50字)}]"
           "——男女主/重要配角/反派都列，这是给后面逐卷拆的全局关系锚点；\n"
           "4) foreshadow_pool：疑似全局伏笔/反复出现的意象清单（是什么、大约最早出现在哪，各15-30字）；\n"
           "5) tech：这本书值得学习的**剧情设计技法**（怎么埋钩子、怎么推节奏、怎么塑人物、"
           "怎么设计日常与大事的穿插），3-6 条，每条15-40字，**只讲技法本身，不要复述情节**。\n"
           "输出 JSON。题目过大时优先保证主线与人物准确。")
    user = json.dumps(payload, ensure_ascii=False)
    if user_prompt:
        user += "\n\n【拆书重点（用户指定的大方向，骨架分析时优先关注）】\n%s" % user_prompt
    data = llm.chat_json(sys, user, tag="break_skeleton", role="decide", profile=profile,
                         think_role="break")
    if isinstance(data, dict):
        return data
    return {}


def analyze_volume(payload, profile=None, user_prompt=""):
    """L2：单卷细纲 → 事件拆分（起止章/章数/推动方式/冲突/高潮/推进要点/**逐章节拍**）
    + 人物变化（成长/关系推进/性格刻画/**当前状态**）+ 伏笔（含**埋设载体/回收方式**）。

    v0.58 输出加厚：事件带「推进要点」，人物带「关系进展」与「性格刻画」。
    v0.62 人物刻画升级为**事件级证据**：性格用「发生了什么事件→什么转折/抉择→体现什么性格」
    写（禁止只列静态细节如外貌/小动作）；关系按「事件如何一步步推进」写事件概述序列
    （相识→升温→转折→定型），覆盖男女主/配角/反派之间的核心关系。
    v1.09 再细化（用户：拆书结果指导 AI 还是太潦草）：
    - 事件带 **beats 逐章节拍**——每个事件里每一章用一句话写明「推进了什么 / 结尾落什么钩子」，
      让主AI续写时知道下一章具体往哪儿推（这是此前最缺的粒度）；
    - 人物带 **state 当前状态**——本部分结束时该人物的处境/目标/心结，续写可直接接上；
    - 伏笔带 **carrier 埋设载体**（借谁的口/什么物件/哪个场景）与回收的 **by 回收方式**
      （无意呼应/刻意回收/反转揭示），主AI知道要在哪一句、哪种语气上回应。
    """
    sys = ("你是一位网文拆书师。下面是某部小说**一部分**的章节标题与每章开头/结尾节选"
           "（以及全书骨架摘要）。请把这部分拆成若干「事件」（每个事件是连续若干章完成的一个"
           "剧情单元，通常 3~15 章），并标出：\n"
           "1) events：每个事件按**四段式**拆解——**起因→经过→高潮→结尾，每段都标出占用的"
           "章数范围**（四段的章数范围拼接起来应覆盖 start_ch~end_ch）："
           "[{title(事件名,5-15字), start_ch, end_ch, chapters(章数), "
           "cause(起因：因为什么引起——什么局面/谁的举动/什么矛盾点燃了这个事件,10-30字), "
           "cause_ch(起因占用的章数范围，如「1-3章」), "
           "process(经过：怎么一步步发展——中间**受到哪些因素误导/干扰/假象**、人物做了什么选择,"
           "30-60字), process_ch(经过占用的章数范围), "
           "climax(高潮：冲突/高潮是怎么产生的——矛盾如何引爆、关键抉择在哪,15-40字), "
           "climax_ch(高潮占用的章数范围), "
           "ending(结尾：以什么方式结束——被迫战斗/交易妥协/反转/逃亡/死亡等收场方式,10-30字), "
           "ending_ch(结尾占用的章数范围), "
           "drive(靠什么推动剧情:冲突/悬念/新角色/新地点/升级/反转…,10-30字), "
           "conflict(核心冲突,10-30字), advance(本事件如何一步步推进/关键转折点,20-50字，"
           "把读者视角下「转折怎么发生」写清楚), "
           "beats(**逐章节拍**：按本事件覆盖的每一章给一条「第X章：一句话」，写明这一章推进了什么、"
           "结尾落在什么钩子/情绪上，每条约10-20字，数组形式，条数与 end_ch-start_ch+1 一致)}]；\n"
           "2) overview：本部分情节概述（30-60字，涵盖这几十章大致发生了什么、氛围走向）；\n"
           "3) foreshadow_seed：本部分**新埋设**的伏笔（含日常式伏笔——比如人物一句貌似平常的话、"
           "一个不起眼的物件举动），[{text(15-30字), chapter, type(日常/物件/对话/事件/设定), "
           "carrier(埋设载体：这句话是谁说的/借哪个物件/在哪个场景下埋的,5-15字)}]；\n"
           "4) foreshadow_payoff：本部分**回收/呼应**的旧伏笔 "
           "[{text, chapter, by(回收方式：无意呼应/刻意回收/反转揭示,5-15字)}]；\n"
           "5) chars：本部分主要人物（**NPC/龙套不写**）的成长与刻画，每名人物三项都写扎实：\n"
           "   [{name,\n"
           "     change(本部分内成长/变化,15-30字),\n"
           "     relation(关系推进的事件概述：本部分内与哪些人的关系、靠什么事件一步步推进"
           "——相识/升温/裂痕/反目的转折点都写出来,40-90字), \n"
           "     portrayal(性格刻画的事件证据：**用事件说话**——写清「发生了什么事件→"
           "他怎么抉择/反应→体现什么性格」，30-60字；禁止只列静态细节(外貌/小动作/说话方式)，"
           "要的是行动与抉择),\n"
           "     state(本部分结束时该人物的当前状态：处境/目标/心结,15-30字——主AI续写"
           "直接从这接)}]；\n"
           "6) tech：本部分体现的剧情/节奏技法（2-4条，每条10-30字，只讲技法不抄情节）。\n"
           "注意：伏笔是拆书命脉——特别留意日常对话与毫不起眼的描写里藏的东西；"
           "beats 是续写命脉——宁可每条短也要逐章写到，别跳章。"
           "输出 JSON，事件与人物描述要保留足够还原原小说的细节，不要压缩成只剩标题。")
    user = json.dumps(payload, ensure_ascii=False)
    if user_prompt:
        user += "\n\n【拆书重点（用户指定的大方向，本部分拆解时优先关注）】\n%s" % user_prompt
    data = llm.chat_json(sys, user, tag="break_volume", role="decide", profile=profile,
                         think_role="break")
    if isinstance(data, dict):
        return data
    return {}


def merge_doc(payload, profile=None, user_prompt="", stage="final"):
    """L3：骨架 + 各卷细纲 → 最终拆书文档（markdown，≤80000 字）+ learning（技法文本）。

    v0.58：
    - 输出加厚：事件带推进要点、人物带关系进展/性格刻画、每卷故事概述——保证细纲能还原
      原小说七八成，不再只剩骨架；上限 50000 → 80000 字、learning 4000 → 6000 字。
    - 高级模式「L3 分批汇总」后手：stage="partial" 时只汇总给定单元组的细纲为一份分卷文档；
      stage="final" 时把多份分卷文档合并成最终文档（防止一次调用上下文不够）。
    """
    if stage == "partial":
        sys = ("你是一位资深小说编辑，负责把一部长篇拆书分析的**其中一部分单元**汇总为"
               "一份分卷拆书文档（后续还会与其他部分合并，本步只写这些单元的内容）。\n"
               "请按以下结构输出 markdown（**人物与事件穿插**，按剧情段组织，不搞人物表/事件表分离）：\n"
               "## 本部分剧情线\n"
               "按时间顺序列本部分的事件段；**每个事件段按四段式展开——起因→经过→高潮→结尾，"
               "每段都标注占用的章数范围**（如「起因（1-3章）：……」）：起因写清因为什么引起"
               "（什么局面/谁的举动/什么矛盾点燃）；经过写清怎么一步步发展、中间**受到哪些因素"
               "误导/干扰/假象**；高潮写清冲突是怎么产生的、矛盾如何引爆；结尾写清以什么方式收场"
               "（被迫战斗/交易妥协/反转/逃亡/死亡等）。事件段里直接把卷入的主要人物写进去："
               "在此事中主要人物的抉择/反应/关系怎么变（性格证据嵌在事件里）——事件是骨架、"
               "人物是血肉，两者合写，随后附逐章节拍；\n"
               "## 本部分锚点与伏笔\n"
               "新埋设：文本/章/类型/**载体（借谁的口/哪个物件/什么场景埋的）**；回收：文本/章/"
               "**方式（无意呼应/刻意回收/反转揭示）**；关键信息锚点（重要地点/物件/对话，标章节）；\n"
               "## 本部分人物当前状态（这部分结束时主要人物处境/目标/心结，续写直接接）\n"
               "要求：①只写分析结论，不照抄原文情节（事件名/章号/人物名可保留）；"
               "②**篇幅与剧情量匹配**——本部分覆盖几十上百章时写到 1~2 万字，把四段式与人物"
               "推进写透写足，**严禁压缩成只剩标题的提纲**；"
               "③开头加一行 `> 分部：<本次覆盖的卷/单元范围>` 便于最后合并。\n"
               "输出 JSON：{\"doc\":\"...markdown全文...\"}。")
    else:
        # v1.50 分批合并防压缩：输入是若干份分卷文档（partials）时明确「合并≠删减」，
        # 内容量不得低于各分卷之和——此前模型把多份 partial 再压缩一遍，最终文档
        # 比一次合并短很多（用户实测 5w → 1.5w）。
        _merged = bool(payload.get("partials"))
        sys = ("你是一位资深小说编辑，负责把一部长篇小说的拆书分析汇总为**可供作者/主AI参考的"
               "设计细纲文档——读完能还原原小说的剧情、人物与结构**。")
        if _merged:
            sys += ("\n输入是**若干份分卷拆书文档**（partials）：必须把每一份分卷的剧情线/事件段/人物/伏笔"
                    "**完整合并进最终文档，合并≠删减**——最终文档的内容量不得低于各分卷之和，"
                    "不得把分卷内容压缩成提纲。然后按以下结构输出 markdown：\n")
        else:
            sys += "请按以下结构输出 markdown：\n"
        sys += ("# 拆书 · 《书名》\n"
               "## 一、全书总览（主线/结构 + **卷划分说明**：原书有明确卷按卷；无明确卷概念时"
               "按剧情阶段（开局→发展→转折→高潮→收束）自行判卷，标起止章号 + 各卷一句话概述）\n"
               "## 二、核心人物设计（全书级人物总图，每节：定位/人设弧光 + 与男女主、重要配角的"
               "关键关系线（相识→升温→转折→定型的事件序列）——**只给跨卷的人物全局画像**，"
               "卷内具体发展放「卷内细纲」穿插写，不在此重复）\n"
               "## 三、卷内细纲（**主体：人物与事件穿插**，按卷逐卷展开）\n"
               "### 第N卷《卷题》（第x~y章 · 划分依据：按原书卷标/按剧情阶段）\n"
               "- **本卷剧情线**：按时间顺序，事件与人物合写——**每个事件段按四段式展开："
               "起因→经过→高潮→结尾，每段标注占用的章数范围**（如「起因（1-3章）：……」）。"
               "起因写清**因为什么引起**（什么局面/谁的举动/什么矛盾点燃了这个事件）；经过写清"
               "**怎么一步步发展、中间受到哪些因素误导/干扰/假象**（人物在误导下做了什么选择）；"
               "高潮写清**冲突是怎么产生的**（矛盾如何引爆、关键抉择在哪）；结尾写清**以什么方式"
               "收场**（被迫战斗/交易妥协/反转/逃亡/死亡等）。事件段里直接写卷入的主要人物在此事中"
               "的抉择/反应/关系推进（性格证据=事件证据），**不做人物表与事件表分离**，事件推进"
               "即人物成长，随后附逐章节拍；\n"
               "- **本卷锚点与伏笔**：本卷新埋设（文本/章/类型/**载体**）与已回收（文本/章/**方式**）"
               "的伏笔 + 关键信息锚点（重要地点/物件/对话，标章节）；\n"
               "- **本卷卷末人物状态**（卷末主要人物处境/目标/心结，续写直接接）。\n"
               "## 四、全书伏笔总表（埋设章→回收章，注明类型/载体/方式，含日常式伏笔）\n"
               "## 五、剧情推动技法总结（分条列：悬念/节奏/人物塑造/日常穿插等）\n"
               "## 六、代表性章节细纲与逐章提示词（v1.43 新增，学习和参考用）：从卷内细纲中挑一段"
               "**约 20 章左右、最经典/最有代表性**的故事段（短篇可整段；一章几万字本身就是完整故事的，"
               "取其中最具代表性的一段），标出起止章（第 n~n+m 章），然后**一章一章**给一条「章节提示词」"
               "——就是这一章要喂给正文AI的写作提示词：写什么场景/推进什么剧情/本章的情绪与节奏/结尾落在"
               "什么钩子上，要具体到 AI 能照它直接写出这一章正文；这一节只讲这一段的写法设计，用于学习"
               "参考（不照抄情节，事件名/章号可保留，人物名可保留）。\n"
               "**第六节是附录级的辅助参考，篇幅要克制：整节约 1500~3000 字即够，每章提示词"
               "80~150 字（写场景/推进/节奏/钩子，点到为止）——严禁为写第六节而压缩第一~五节的"
               "篇幅。第一节~第五节（尤其第三节卷内细纲）才是拆书文档的主体，必须按②的篇幅要求"
               "写满写透、严格遵守；第六节只是挑一段代表性故事做示范，只占总篇幅的一小部分。**\n"
               "要求：①只写分析结论，**不得照抄原文情节**（事件名与章号可保留，人物名可保留）；"
               "②**篇幅与剧情量匹配，充分利用篇幅上限**——短篇（≤20 章）几千字即可；"
               "中长篇（上百章）写到 1~3 万字；超长篇（上千章，如 2000+ 章）写到 5~8 万字（接近"
               "上限），每个事件段四段式写透、人物推进写足，**严禁压缩成只剩标题的提纲**；"
               "③**人物与事件务必穿插成卷内叙事流**（禁止退回「人物表+事件表」分离写法），"
               "逐章节拍让主AI能直接照着续写；④同时输出 `learning` 字段："
               "一段 1000-6000 字的**设计技法学习文本**——把这本书可迁移的剧情设计方法"
               "（怎么开篇钩人、怎么埋长线伏笔、怎么设计人物弧光、怎么穿插日常与事件、怎么推高潮、"
               "怎么设计关系张力、怎么设计每章的钩子与情绪节拍）写成让作者/主AI照做的指导，"
               "**技法必须覆盖两个关键维度**：\n"
               "（a）**事件长度与节奏**：一个事件用多少章铺垫（起因）/推进（经过）/引爆（高潮）/收尾"
               "（结尾），长短事件怎么交替、避免篇幅雷同——给出可照做的章数配比思路；\n"
               "（b）**事件影响层级**：怎么区分单章小事件/跨章中事件/改变整卷格局的大事件，事件"
               "影响哪些人物与关系、在主线支线留什么后果、结束要点出对后续剧情的连锁影响；\n"
               "（c）**冲突与误导**：高潮冲突怎么一步步产生、中途埋哪些误导/假象/干扰、关键抉择"
               "落在哪一章；\n"
               "（d）**伏笔与回收**：怎么埋设（借载体/日常）、隔多少章回收、用什么方式回收"
               "（无意呼应/刻意回收/反转揭示）。\n"
               "**只讲技法与思路，绝不出现具体情节/对话/人名照搬**。\n"
               "输出 JSON：{\"doc\":\"...markdown全文...\", \"learning\":\"...技法文本...\"}。")
    user = json.dumps(payload, ensure_ascii=False)
    if user_prompt:
        user += "\n\n【拆书重点（用户指定的大方向，汇总文档时优先关注并体现）】\n%s" % user_prompt
    data = llm.chat_json(sys, user, tag="break_merge", role="decide", profile=profile,
                         think_role="break")
    if not isinstance(data, dict):
        data = {}
    doc = str(data.get("doc") or "").strip()
    learning = str(data.get("learning") or "").strip()
    if len(doc) > DOC_MAX_CHARS:
        doc = doc[:DOC_MAX_CHARS] + "\n\n（已达 8 万字上限，详细卷细纲请查看过程阶段）"
    if stage == "partial":
        return {"doc": doc}
    return {"doc": doc, "learning": learning[:LEARN_MAX_CHARS]}


# ---------- 拆书主流程（可停止/进度回调） ----------
_STAGES = ["title", "skeleton", "volume", "merge"]


class NovelBreaker:
    """拆书执行器：串起 标题流分批 → 骨架 → 逐卷细纲 → 汇总。

    v0.56：支持拆书专用设置（break_settings）——
      profile      拆书单独用哪个 API 配置（空=跟随全局用途分工）
      token_per_part 每部分 token 预算（决定每批标题数/每部分章数）
      parallel/parallel_n  并行执行（L1-a 各批、L2 各卷可并行；骨架/汇总仍串行）
      prompt       用户拆书总体提示词（大方向：关注日常/人物/脑洞/哲思…；空=照常）
    """

    def __init__(self, log=None, stop_check=None, settings=None, pause_check=None):
        self.log = log or (lambda kind, msg: None)
        self.stop_check = stop_check or (lambda: False)
        # v0.82 暂停：拆书进行中可临时挂起（点「暂停」后环节之间停下），点「继续」恢复
        self.pause_check = pause_check or (lambda: False)
        self.settings = settings or break_settings()

    def _wait_pause(self):
        """暂停点：暂停期间在环节之间挂起（不中断当前内容），直到继续或停止。"""
        while self.pause_check() and not self.stop_check():
            time.sleep(0.2)

    def _profile(self):
        return self.settings.get("profile") or None

    def _user_prompt(self):
        return _user_break_prompt(self.settings)

    def run(self, text, title="拆书分析", progress_cb=None, job_dir=None):
        """完整拆书。返回 {"ok", "doc", "learning", "stats"}。

        v0.55 断点续传：传入 job_dir（目录）时，各阶段结果即时落盘——
        L1-a 标题摘要 / L1-b 骨架 / L2 单元细纲 / L3 汇总，每完成一块写一块；
        API 出错或用户停止/软件退出后，对同一输入再启动会自动跳过已完成部分
        （只补跑缺失环节），不需要整本重拆。完成/放弃时由调用方决定删不删 job。
        不传 job_dir 时行为与旧版完全一致。
        """
        import concurrent.futures
        import glob
        import json as _json
        import os as _os

        def _jload(*rel):
            if not job_dir:
                return None
            p = _os.path.join(job_dir, *rel)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return _json.load(f)
            except Exception:
                return None

        def _jsave(data, *rel):
            if not job_dir:
                return
            p = _os.path.join(job_dir, *rel)
            _os.makedirs(_os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False)

        stats = {}
        parsed = parse_novel(text)
        vols = parsed["volumes"]
        stats = {"volumes": len(vols),
                 "chapters": parsed["total_chapters"],
                 "chars": parsed["total_chars"]}
        # v0.69 失败环节清单：LLM 出错/返回空的环节不落盘、不视为完成，
        # 结束时若有失败环节直接返回错误（done.json 不写）；重试只补跑失败环节，
        # 不再「出错跳过、之后步骤继续」。
        # v0.70 升级：每个环节失败先自动重试（RETRY_TIMES 次），仍失败才记入清单。
        _failed = []

        def _fail_err():
            return ("%d 个环节未完成（失败）：%s。每个环节已自动重试 %d 次仍失败，"
                    "中间结果已保留——再次「开始拆书」只补跑失败环节；"
                    "「重新开始拆书」清空进度全部重来。"
                    % (len(_failed), "；".join(_failed[:8]) + ("…" if len(_failed) > 8 else ""),
                       RETRY_TIMES))

        self.log("info", "文本解析完成：%d 卷 / %d 章 / %.1f 万字。"
                 % (len(vols), parsed["total_chapters"], parsed["total_chars"] / 10000))
        # v0.59 实际生效的每部分 token：智能模式按模型上下文×档位自动定（简单/高级用手填）
        mode = self.settings.get("mode") or "smart"
        token = effective_token(self.settings)
        ctx, ctx_src = (context_with_source(self.settings) if mode == "smart"
                        else (0, ""))
        per_c = chapters_per_part(dict(self.settings, token_per_part=token))
        ovl_c = overlap_chapters(self.settings)
        step = max(1, per_c - ovl_c)   # 重叠：每部分与下一部分重叠 ovl_c 章
        # 无意义章节名（自动编号/空标题）占比高 → L1 改用每章开头采样概览
        gen_titles = generic_title_mode(parsed)
        per_t = titles_per_part(dict(self.settings, token_per_part=token),
                                generic_titles=gen_titles)
        n_units = sum((len(v["chapters"]) - 1) // step + 1 for v in vols)
        l3b = effective_l3_batch(self.settings, ctx, per_c, n_units)
        n_par = self.settings.get("parallel_n") or 2
        mode_name = {"simple": "简单", "smart": "智能", "advanced": "高级"}.get(mode, "智能")
        sub_name = {"conservative": "（保守）", "balanced": "（正常）", "aggressive": "（激进）"}.get(
            self.settings.get("smart_sub") or "", "")
        if gen_titles:
            self.log("info", "章节标题多为自动编号/无意义，L1 改用每章开头采样概览。")
        self.log("info", "拆书模式：%s%s%s（每部分 %d token → %d 章%s；每批标题 %d 条；"
                 "L3 汇总%s）。"
                 % (mode_name, sub_name,
                    ("；上下文 %d token（%s）" % (ctx, ctx_src)) if mode == "smart" else "",
                    token, per_c,
                    ("，与下一部分重叠 %d 章" % ovl_c) if ovl_c else "",
                    per_t,
                    ("分批 %d 单元/批" % l3b) if l3b else "一次合并"))
        if self.settings.get("parallel"):
            self.log("info", "并行拆书已开启（并发 %d）。" % n_par)
        if gen_titles:
            all_titles = []
            for v in vols:
                for c in v["chapters"]:
                    head = (c.get("head") or "").replace("\n", " ")[:HEAD_FOR_TITLE]
                    all_titles.append("%d.%d %s｜开头：%s"
                                      % (v["no"], c["no"], (c["title"] or ""), head))
        else:
            all_titles = []
            for v in vols:
                all_titles.extend("%d.%d %s" % (v["no"], c["no"], (c["title"] or ""))
                                  for c in v["chapters"])

        # L1-a 标题流分批（可并行；job_dir 已完成的批直接跳过）
        n_batch = (len(all_titles) - 1) // per_t + 1
        title_summ = [None] * n_batch
        _cached_ts = _jload("title_summ.json") or []
        for i, r in enumerate(_cached_ts):
            if i < n_batch and isinstance(r, dict):
                title_summ[i] = r
        _ts_lock = threading.Lock()

        def _save_ts(idx, r):
            with _ts_lock:
                c2 = _jload("title_summ.json") or []
                while len(c2) <= idx:
                    c2.append(None)
                c2[idx] = r
                _jsave(c2, "title_summ.json")

        batch_index = [i for i in range(n_batch) if title_summ[i] is None]

        def _do_title(idx):
            s = idx * per_t
            batch = all_titles[s:s + per_t]
            self.log("info", "L1 章节标题概览（%d/%d 批）…" % (idx + 1, n_batch))

            def _call():
                r = summarize_title_batch(batch, profile=self._profile(),
                                          user_prompt=self._user_prompt())
                if not isinstance(r, dict) or not r:
                    raise llm.LLMError("返回空结果")
                return r

            try:
                r = _retry_llm(_call, log=self.log, label="L1 标题批 %d" % (idx + 1))
            except llm.StopRequested:
                raise   # 用户停止：立即终止，不当作普通失败跳过
            except llm.LLMError as e:
                # v0.70 已自动重试 RETRY_TIMES 次仍失败/仍空：不落盘、不视为完成
                self.log("warn", "标题批概览失败（已自动重试 %d 次仍失败）：%s"
                         % (RETRY_TIMES, e))
                _failed.append("L1 标题批 %d" % (idx + 1))
                r = {}
            if r:
                _save_ts(idx, r)
            return idx, r

        if batch_index:
            self._wait_pause()
            if self.settings.get("parallel") and n_par > 1 and len(batch_index) > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=n_par) as ex:
                    # v0.79.1 并行子线程继承主线程停止事件：拆书 worker 在调用线程
                    # set_abort 绑定了 stop_ev，子线程线程局部未继承——不绑定的子线程
                    # LLM 调用不响应点停止（429 重试风暴里停不下来）
                    def _bound_title(i):
                        _cur = llm.current_abort()
                        if _cur is not None:
                            llm.set_abort(_cur)
                        try:
                            return _do_title(i)
                        finally:
                            llm.set_abort(None)
                    futs = {ex.submit(_bound_title, i): i for i in batch_index}
                    done_n = sum(1 for r in _cached_ts if isinstance(r, dict))
                    for fut in concurrent.futures.as_completed(futs):
                        idx, r = fut.result()
                        title_summ[idx] = r
                        done_n += 1
                        if progress_cb:
                            progress_cb("title", done_n, n_batch)
            else:
                for idx in batch_index:
                    if self.stop_check():
                        return {"ok": False, "error": "已停止", "stats": stats}
                    _, r = _do_title(idx)
                    title_summ[idx] = r
                    if progress_cb:
                        progress_cb("title", idx + 1, n_batch)
        elif progress_cb:
            progress_cb("title", n_batch, n_batch)
        title_summ = [x for x in title_summ if x]
        if _failed:
            return {"ok": False, "error": _fail_err(), "stats": stats}

        # L1-b 骨架（job_dir 已存在则直接复用）
        self._wait_pause()
        if self.stop_check():
            return {"ok": False, "error": "已停止", "stats": stats}
        skeleton = _jload("skeleton.json")
        if skeleton is None:
            self.log("info", "L1 全书骨架分析（主线/人物/伏笔池）…")
            skel_payload = {
                "title": title,
                "volumes": [{"no": v["no"], "title": v["title"],
                             "chapter_count": len(v["chapters"]),
                             "first_heads": [c["head"][:300] for c in v["chapters"][:2]]}
                            for v in vols],
                "title_summaries": title_summ,
            }
            def _call():
                r = build_skeleton(skel_payload, profile=self._profile(),
                                   user_prompt=self._user_prompt())
                if not isinstance(r, dict) or not r:
                    raise llm.LLMError("返回空结果")
                return r

            try:
                skeleton = _retry_llm(_call, log=self.log, label="骨架分析") \
                    if skel_payload.get("volumes") else {}
            except llm.StopRequested:
                raise
            except llm.LLMError as e:
                # v0.70 已自动重试仍失败/仍空：骨架是后续所有环节的地基，中断
                self.log("warn", "骨架分析失败（已自动重试 %d 次仍失败）：%s"
                         % (RETRY_TIMES, str(e)[:120]))
                return {"ok": False,
                        "error": "骨架分析失败（已自动重试 %d 次仍失败）：%s。"
                                 "中间结果已保留，可重试。"
                                 % (RETRY_TIMES, str(e)[:120]),
                        "stats": stats}
            if not skeleton:
                self.log("warn", "骨架分析返回空，中断拆书（未落盘，可重试）。")
                return {"ok": False,
                        "error": "骨架分析返回空，可重试（已完成环节保留）。", "stats": stats}
            _jsave(skeleton, "skeleton.json")
        if progress_cb:
            progress_cb("skeleton", 1, 1)

        # L2 逐卷细纲：无卷标时卷=每部分（按 token 预算分出的章组）；有卷标时若卷超过
        # 预算也按每部分章数再细分（保证单次调用体量可控）。高级模式可开重叠（step < per_c）
        # 让相邻部分首尾衔接连贯。job_dir 已完成的单元跳过。
        total_parts = 0
        chunks = []
        for v in vols:
            chs = v["chapters"]
            for s in range(0, len(chs), step):
                chunks.append({"vol_no": v["no"], "vol_title": v["title"],
                               "chapters": chs[s:s + per_c],
                               "part": len(chunks)})
        total_parts = len(chunks)

        def _do_vol(chunk):
            idx = chunk["part"]
            self.log("info", "L2 拆第 %d/%d 单元（%s，%d 章）…"
                     % (idx + 1, total_parts,
                        ("《%s》" % chunk["vol_title"]) if chunk["vol_title"] else "无卷题",
                        len(chunk["chapters"])))
            payload = {
                "vol_no": chunk["vol_no"], "vol_title": chunk["vol_title"],
                "skeleton": skeleton,
                "chapters": [{"no": c["no"], "title": c["title"],
                              "head": c["head"], "tail": c["tail"]}
                             for c in chunk["chapters"]],
            }
            def _call():
                r = analyze_volume(payload, profile=self._profile(),
                                   user_prompt=self._user_prompt())
                if not isinstance(r, dict) or not r:
                    raise llm.LLMError("返回空结果")
                return r

            try:
                r = _retry_llm(_call, log=self.log, label="L2 第 %d 单元" % (idx + 1))
            except llm.StopRequested:
                raise   # 用户停止：立即终止，不当作普通失败跳过
            except llm.LLMError as e:
                # v0.70 已自动重试 RETRY_TIMES 次仍失败/仍空：不落盘、不视为完成
                self.log("warn", "第 %d 单元拆解失败（已自动重试 %d 次仍失败）：%s"
                         % (idx + 1, RETRY_TIMES, e))
                _failed.append("L2 第 %d 单元（%s）"
                               % (idx + 1, chunk["vol_title"] or ("卷%d" % chunk["vol_no"])))
                r = {}
            if r:
                _jsave({"vol": chunk["vol_no"], "title": chunk["vol_title"], **r},
                       "vol_notes", "vol_%d.json" % idx)
            return idx, r

        vol_notes = [None] * total_parts
        _cached_vn = {}
        if job_dir:
            for p in glob.glob(_os.path.join(job_dir, "vol_notes", "vol_*.json")):
                d = _jload("vol_notes", _os.path.basename(p))
                if isinstance(d, dict):
                    try:
                        _cached_vn[int(_os.path.basename(p)[4:-5])] = d
                    except ValueError:
                        pass
        for i, d in _cached_vn.items():
            if 0 <= i < total_parts:
                vol_notes[i] = d
        vol_todo = [i for i in range(total_parts) if vol_notes[i] is None]
        if vol_todo:
            self._wait_pause()
            if self.settings.get("parallel") and n_par > 1 and len(vol_todo) > 1:
                with concurrent.futures.ThreadPoolExecutor(max_workers=n_par) as ex:
                    # v0.79.1 并行子线程继承停止事件（同 _bound_title 说明）
                    def _bound_vol(ch):
                        _cur = llm.current_abort()
                        if _cur is not None:
                            llm.set_abort(_cur)
                        try:
                            return _do_vol(ch)
                        finally:
                            llm.set_abort(None)
                    futs = {ex.submit(_bound_vol, chunks[i]): i for i in vol_todo}
                    done_n = total_parts - len(vol_todo)
                    for fut in concurrent.futures.as_completed(futs):
                        idx, r = fut.result()
                        if r:
                            vol_notes[idx] = {"vol": chunks[idx]["vol_no"],
                                              "title": chunks[idx]["vol_title"], **r}
                        done_n += 1
                        if progress_cb:
                            progress_cb("volume", done_n, total_parts)
            else:
                for idx in vol_todo:
                    if self.stop_check():
                        return {"ok": False, "error": "已停止", "stats": stats}
                    _, r = _do_vol(chunks[idx])
                    if r:
                        vol_notes[idx] = {"vol": chunks[idx]["vol_no"],
                                          "title": chunks[idx]["vol_title"], **r}
                    if progress_cb:
                        progress_cb("volume", idx + 1, total_parts)
        elif progress_cb:
            progress_cb("volume", total_parts, total_parts)
        vol_notes = [x for x in vol_notes if x]
        if _failed:
            return {"ok": False, "error": _fail_err(), "stats": stats}

        # L3 汇总（job_dir 已有 doc 则直接复用；高级模式可开「分批汇总」后手）
        self._wait_pause()
        if self.stop_check():
            return {"ok": False, "error": "已停止", "stats": stats}
        cached_doc = _jload("doc.json")
        if cached_doc and cached_doc.get("doc"):
            doc = cached_doc.get("doc", "")
            learning = cached_doc.get("learning", "") or ""
        else:
            # v0.59 实测修复：L3 汇总调用失败（商汤类网关对超长生成可能返回空/异常）时
            # 不能中断整个拆书——包一层 try/except，失败自动退化为阶段过程文档
            # v0.70：merge_doc 失败先自动重试 RETRY_TIMES 次，仍失败才退化
            def _try_merge(payload, stage="final"):
                try:
                    return _retry_llm(
                        lambda: merge_doc(payload, profile=self._profile(),
                                          user_prompt=self._user_prompt(), stage=stage),
                        log=self.log, label="L3 汇总（%s）" % stage)
                except llm.StopRequested:
                    raise
                except llm.LLMError as e:
                    self.log("warn", "L3 汇总调用失败（已自动重试 %d 次仍失败）：%s"
                             % (RETRY_TIMES, str(e)[:120]))
                    return {}
                except Exception as e:
                    self.log("warn", "L3 汇总异常：%s" % (str(e)[:120]))
                    return {}

            # 高级模式：手填 l3_batch（0=一次合并）；智能模式：按上下文自动判断（l3b）
            if l3b > 0 and len(vol_notes) > l3b:
                # 分批汇总：每批 l3b 个单元 → 分卷文档，最后合并成最终文档
                self.log("info", "L3 分批汇总（每批 %d 单元，共 %d 批 → 最后合并）…"
                         % (l3b, (len(vol_notes) + l3b - 1) // l3b))
                partial_docs = []
                n_parts = (len(vol_notes) + l3b - 1) // l3b
                for pi in range(n_parts):
                    group = vol_notes[pi * l3b:(pi + 1) * l3b]
                    cached_p = _jload("doc_part_%d.json" % pi)
                    pdoc = (cached_p or {}).get("doc") or ""
                    if not pdoc:
                        merged = _try_merge(
                            {"title": title, "skeleton": skeleton,
                             "volumes": group, "stats": stats, "partial_no": pi + 1},
                            stage="partial")
                        merged = merged if isinstance(merged, dict) else {}
                        pdoc = (merged or {}).get("doc") or ""
                        if not pdoc:
                            self.log("warn", "第 %d 批分卷汇总返回空，改用阶段过程拼装。"
                                     % (pi + 1))
                            pdoc = _fallback_doc(title, skeleton, group)
                        _jsave({"doc": pdoc}, "doc_part_%d.json" % pi)
                    partial_docs.append(pdoc)
                merged = _try_merge(
                    {"title": title, "skeleton": skeleton,
                     "partials": partial_docs, "stats": stats},
                    stage="final")
                merged = merged if isinstance(merged, dict) else {}
                doc = (merged or {}).get("doc") or ""
                learning = (merged or {}).get("learning") or ""
                if not doc:
                    self.log("warn", "最终合并返回空，改用分卷文档拼接。")
                    doc = "\n\n".join(partial_docs)
                    learning = _fallback_learning(skeleton, vol_notes)
            else:
                self.log("info", "L3 汇总拆书文档（总览/人物/卷细纲/伏笔总表/技法）…")
                merged = _try_merge({"title": title, "skeleton": skeleton,
                                     "volumes": vol_notes, "stats": stats})
                merged = merged if isinstance(merged, dict) else {}
                doc = (merged or {}).get("doc") or ""
                learning = (merged or {}).get("learning") or ""
                if not doc:
                    self.log("warn", "汇总返回空，改用阶段过程拼装最小文档。")
                    doc = _fallback_doc(title, skeleton, vol_notes)
                    learning = _fallback_learning(skeleton, vol_notes)
            _jsave({"doc": doc, "learning": learning}, "doc.json")
        if progress_cb:
            progress_cb("merge", 1, 1)
        self.log("info", "拆书完成：文档 %d 字，学习文本 %d 字。"
                 % (len(doc), len(learning)))
        stats["doc_chars"] = len(doc)
        if job_dir:
            _jsave({"ok": True}, "done.json")
        return {"ok": True, "doc": doc, "learning": learning, "stats": stats,
                # v0.54 小说导入成项目：回传中间结果（骨架/卷细纲/标题流摘要），
                # 供「还原项目」直接复用（设定合成/人物抽取/伏笔台账），无需二次拆书
                "intermediate": {"skeleton": skeleton,
                                 "vol_notes": vol_notes,
                                 "title_summaries": title_summ}}


def _fallback_doc(title, skeleton, vol_notes):
    lines = ["# 拆书 · %s" % title, ""]
    sk = skeleton if isinstance(skeleton, dict) else {}
    if sk.get("story"):
        lines += ["## 一、全书总览", str(sk["story"]), ""]
    lines += ["## 二、卷事件细纲（过程阶段）", ""]
    for v in vol_notes:
        lines.append("### 第%s卷 %s" % (v.get("vol"), v.get("title") or ""))
        if v.get("overview"):
            lines.append("概述：%s" % str(v["overview"]))
        for e in (v.get("events") or []):
            lines.append("- %s（第%s~%s章 · %s章 · %s）%s" % (
                e.get("title", "?"), e.get("start_ch"), e.get("end_ch"),
                e.get("chapters", "?"), e.get("drive", ""),
                ("　推进：%s" % str(e.get("advance", ""))) if e.get("advance") else ""))
            # v1.11 四段式：起因/经过/高潮/结尾，每段标注占用章数范围
            for _key, _lab in (("cause", "起因"), ("process", "经过"),
                               ("climax", "高潮"), ("ending", "结尾")):
                _txt = str(e.get(_key) or "").strip()
                if not _txt:
                    continue
                _ch = str(e.get(_key + "_ch") or "").strip()
                lines.append("  · %s（%s）：%s" % (_lab, _ch or "?", _txt))
            # v1.09 逐章节拍：每章一行，主AI续写知道下一章往哪儿推
            for b in (e.get("beats") or []):
                lines.append("  · %s" % str(b))
        if v.get("foreshadow_seed"):
            lines.append("埋设：%s" % "；".join(
                ("%s%s" % (str(x.get("text", "")),
                           (("（借：%s）" % str(x.get("carrier", ""))) if x.get("carrier") else "")))
                for x in v["foreshadow_seed"]))
        for c in (v.get("chars") or []):
            if not isinstance(c, dict):
                continue
            nm = str(c.get("name") or "").strip()
            if not nm:
                continue
            parts = [str(c.get("change") or "")]
            if c.get("relation"):
                parts.append("关系：%s" % str(c["relation"]))
            if c.get("portrayal"):
                parts.append("刻画：%s" % str(c["portrayal"]))
            if c.get("state"):
                parts.append("状态：%s" % str(c["state"]))
            lines.append("人物：%s — %s" % (nm, "；".join(x for x in parts if x)))
    return "\n".join(lines)


def _fallback_learning(skeleton, vol_notes):
    parts = []
    sk = skeleton if isinstance(skeleton, dict) else {}
    if sk.get("tech"):
        parts.append("\n".join("- %s" % str(x) for x in sk["tech"]))
    for v in vol_notes[:3]:
        if v.get("tech"):
            parts.append("\n".join("- %s" % str(x) for x in v["tech"]))
    txt = "\n".join(parts).strip()
    return txt[:LEARN_MAX_CHARS]


# ---------- 风格库（保存/列表/读取/删除） ----------
def ensure_breaks_dir():
    os.makedirs(breaks_dir(), exist_ok=True)


def _slug(name):
    return re.sub(r"[\\/:*?\"<>|\s]+", "_", str(name or "").strip()) or "untitled"


def save_break(name, doc, learning=""):
    """保存一个拆书风格。返回 {"ok", "name", "path"}。"""
    ensure_breaks_dir()
    key = _slug(name)
    meta = {
        "name": str(name).strip(), "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "doc_chars": len(doc or ""), "learning_chars": len(learning or ""),
    }
    with open(os.path.join(breaks_dir(), key + ".json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "doc": doc or "", "learning": learning or ""},
                  f, ensure_ascii=False, indent=1)
    return {"ok": True, "name": key, "path": os.path.join(breaks_dir(), key + ".json")}


def list_breaks():
    """风格库列表：[{name, saved_at, doc_chars, learning_chars}]（按保存时间倒序）。"""
    ensure_breaks_dir()
    out = []
    for fn in os.listdir(breaks_dir()):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(breaks_dir(), fn), "r", encoding="utf-8") as f:
                d = json.load(f)
            meta = d.get("meta") or {}
            out.append({"name": meta.get("name", fn[:-5]),
                        "saved_at": meta.get("saved_at", ""),
                        "doc_chars": int(meta.get("doc_chars", 0) or 0),
                        "learning_chars": int(meta.get("learning_chars", 0) or 0)})
        except Exception:
            continue
    out.sort(key=lambda x: x["saved_at"], reverse=True)
    return out


def load_break(name):
    """读取一个拆书风格：{"name","doc","learning"}；不存在返回 None。"""
    key = _slug(name)
    path = os.path.join(breaks_dir(), key + ".json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return {"name": (d.get("meta") or {}).get("name", key),
                "doc": d.get("doc") or "", "learning": d.get("learning") or ""}
    except Exception:
        return None


def delete_break(name):
    key = _slug(name)
    path = os.path.join(breaks_dir(), key + ".json")
    if os.path.exists(path):
        os.remove(path)
        return {"ok": True}
    return {"error": "风格不存在"}


def import_break_from_text(name, content, learning=""):
    """导入一份拆书文档（txt/md 全文）为一个拆书风格。

    若内容本身是风格库导出的 JSON（含 meta/doc/learning）则识别 JSON 结构；
    否则把全文当作拆书文档 doc，learning 留空（主AI注入时退化为取 doc 前缀）。
    返回 {"ok", "name"}。
    """
    import json as _json
    content = (content or "").strip()
    if not content:
        return {"error": "内容为空"}
    doc = content
    learn = (learning or "").strip()
    try:
        parsed = _json.loads(content)
        if isinstance(parsed, dict) and parsed.get("doc"):
            doc = str(parsed["doc"])
            learn = str((parsed.get("learning") or parsed.get("meta", {}).get("learning") or "")).strip()
            if not parsed.get("name"):
                pass
    except Exception:
        pass
    return save_break(name or "导入拆书", doc, learn)


def export_break(name, out_txt):
    """导出拆书文档为 txt。返回 {"ok", "path"}。"""
    data = load_break(name)
    if data is None:
        return {"error": "风格不存在"}
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("# 拆书风格：%s\n\n%s\n" % (data["name"], data["doc"]))
    return {"ok": True, "path": out_txt}


def learning_text(name):
    """取一个拆书风格的「设计技法学习文本」（供主AI提示词注入）。

    若风格没有单独保存 learning（外部导入的文档），退化为取 doc 前缀，
    保证导入的拆书文档也能直接供主AI学习设计技法。
    """
    data = load_break(name)
    if data is None:
        return ""
    learn = (data.get("learning") or "").strip()
    if not learn:
        learn = (data.get("doc") or "")[:LEARN_MAX_CHARS]
    return learn[:LEARN_MAX_CHARS]