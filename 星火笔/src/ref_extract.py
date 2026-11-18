# -*- coding: utf-8 -*-
"""v1.133 事件范例库·AI 智能划分。

整本小说按「完整事件」切分：把段落编号后交给主AI判界，返回段落区间，
再用原文精确切片（不重写、不丢字）。按 ~5000 字分块，块内可跨章；
块首/块尾不完整的事件由提示词要求跳过，避免切出半截。
"""
import re

import llm

_EVENT_TYPES = ["兵刃对决", "突破渡劫", "谈判对峙", "追逐逃杀", "群战围攻",
                "宴席试探", "情感爆发", "其他"]

_SYS = (
    "你在为小说写作整理「事件范例库」。你的任务：把给到的段落按**完整事件**切开。\n"
    "什么叫完整事件：一件事从起因/动机落地开始，到这件事有了结果为止——"
    "打斗从双方动手/被拦写到分胜负或收手；突破从准备与风险写到成败与代价；"
    "谈判从落座试探写到底牌交锋与成交/谈崩；追逐从追逃开始写到脱身或被截住。\n"
    "切分铁律：\n"
    "1. 不要按章节/自然段机械切；不要只截高潮中段；不要把两个事件并成一条；\n"
    "2. 一条事件至少覆盖 3 个编号段落（或 200 字以上），否则不要单独成条；\n"
    "3. 只输出在给定段落范围内**完整闭合**的事件；开头或结尾还差一截的不要输出；\n"
    "4. 事件区间不得重叠，按顺序排列。\n"
    "事件类型只能从这些里选：%s。\n"
    "只输出 JSON：{\"events\":[{\"start\":起始段号,\"end\":结束段号,"
    "\"event\":\"事件类型\",\"title\":\"一句话概括这起事件(≤18字)\"}]}"
    % "/".join(_EVENT_TYPES)
)


def _paragraphs(text):
    raw = (text or "").replace("\r\n", "\n").strip()
    parts = [p.strip() for p in re.split(r"\n+", raw) if p.strip()]
    return parts


def _chunks(paras, max_chars=5000):
    """按段落累计切块（不切断段落），返回 [ [段落...], ... ]。"""
    out, cur, size = [], [], 0
    for p in paras:
        if cur and size + len(p) > max_chars:
            out.append(cur)
            cur, size = [], 0
        cur.append(p)
        size += len(p)
    if cur:
        out.append(cur)
    return out


def _slice_events(paras, events):
    """把模型给的区间切片；收拢重叠/越界，返回 [{text,event,note}]。"""
    out = []
    items = []
    for e in events or []:
        if not isinstance(e, dict):
            continue
        try:
            s = int(e.get("start"))
            t = int(e.get("end"))
        except (TypeError, ValueError):
            continue
        if s < 1 or t < s or s > len(paras):
            continue
        t = min(t, len(paras))
        items.append((s, t, str(e.get("event") or "其他").strip(),
                      str(e.get("title") or "").strip()))
    items.sort(key=lambda x: (x[0], x[1]))
    prev_end = 0
    for s, t, ev, title in items:
        s = max(s, prev_end + 1)
        if t - s + 1 < 2:
            continue
        text = "\n".join(paras[s - 1:t]).strip()
        if len(text) < 150:
            continue
        if ev not in _EVENT_TYPES:
            ev = "其他"
        out.append({"text": text, "event": ev, "note": title})
        prev_end = t
    return out


def extract_events(text, progress=None, should_stop=None, profile=None):
    """按完整事件切分整本/多章小说。

    progress(done, total, msg)：进度回调；should_stop() 返回 True 时中止；
    profile：指定 API 配置名（None=按用途跟随设置）。
    返回 [{text, event, note, chars}]；失败抛 llm.LLMError / RuntimeError。
    """
    paras = _paragraphs(text)
    if len(paras) < 2:
        return []
    blocks = _chunks(paras)
    total = len(blocks)
    results = []
    for bi, block in enumerate(blocks, 1):
        if should_stop and should_stop():
            break
        if progress:
            progress(bi - 1, total, "第 %d/%d 块（%d 段）…" % (bi, total, len(block)))
        numbered = "\n".join("[%d] %s" % (i + 1, p) for i, p in enumerate(block))
        user = ("【小说段落（已编号，共 %d 段）】\n%s\n\n"
                "请按完整事件切分，输出 JSON（只要在这个范围内完整闭合的事件）。"
                % (len(block), numbered))
        data = llm.chat_json(_SYS, user, tag="ref_extract", role="review",
                             profile=profile, max_tokens=3000)
        events = (data or {}).get("events") if isinstance(data, dict) else None
        got = _slice_events(block, events or [])
        for g in got:
            g["chars"] = len(g["text"])
        results.extend(got)
    if progress:
        progress(total, total, "完成")
    return results
