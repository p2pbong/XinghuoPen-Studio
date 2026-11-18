# -*- coding: utf-8 -*-
"""v1.134 事件范例库·AI 分类整理。

对范例句库做批量体检：判定每条属于哪类事件、是否是一个**完整事件**（开头有起因/
结尾有结果），给一句话标题；碎片只做标记（flag=fragment），不自动删除，
由用户在界面上决定留删。
"""
import llm
import ref_taxonomy as tax

EVENT_TYPES = [ev for _, _, subs in tax.CATEGORIES for _, ev, _ in subs]

_SYS = (
    "你是小说素材库的分类员，按一套**图书分类规则**给范例上架，保证同一类事件永远落在同一个架位。\n"
    "【类目表（必须严格使用，不得自造类目）】\n%s\n"
    "对每一条范例做四件事：\n"
    "1. 归类：选一个二级分类号 code（A1/A2/A3/B1/B2/C1/D1/E9）与其事件名 event；\n"
    "2. 判断完整性：这条范例是不是一个**有始有终的完整事件**——开头能看到起因/由头，"
    "中间有推进或交锋，结尾有明确结果或收束；明显从中间截断、只有打斗中段、事情没讲完、"
    "开头没来由或结尾悬空的判为 fragment；\n"
    "3. 起标题：≤18 字，概括这起事件（如「长街断枪」「茶凉之前」），不要写成主题词；\n"
    "4. 一句话判断依据（≤20 字）。\n"
    "只输出 JSON：{\"items\":[{\"id\":\"给定id\",\"code\":\"A1\",\"event\":\"兵刃对决\","
    "\"title\":\"一句话标题\",\"quality\":\"complete|fragment\",\"reason\":\"≤20字\"}]}\n"
    "每条都要输出，id 原样返回，不得漏条、不得改 id。"
    % tax.catalog_text()
)


def _trim(text, head=700, tail=260):
    t = (text or "").strip()
    if len(t) <= head + tail:
        return t
    return t[:head] + "\n……（中间省略）……\n" + t[-tail:]


def classify_items(items, profile=None, progress=None):
    """批量判定事件类型/标题/完整性，返回 [{id,event,title,quality,reason}]。"""
    items = [x for x in (items or []) if isinstance(x, dict) and (x.get("text") or "").strip()]
    out = []
    batch = 6
    total = (len(items) + batch - 1) // batch
    for bi in range(0, len(items), batch):
        chunk = items[bi:bi + batch]
        if progress:
            progress(min(bi + 1, len(items)), len(items),
                     "第 %d/%d 批（%d 条）…" % (bi // batch + 1, total, len(chunk)))
        lines = []
        for x in chunk:
            lines.append("【id=%s｜现类型=%s｜%d字】\n%s"
                         % (x.get("id") or "", x.get("event") or "未分类",
                            len(x.get("text") or ""), _trim(x.get("text"))))
        user = ("【待整理的范例】\n" + "\n\n".join(lines) +
                "\n\n请逐条输出分类/标题/完整性判断的 JSON。")
        data = llm.chat_json(_SYS, user, tag="ref_classify", role="review",
                             profile=profile, max_tokens=2500)
        rows = (data or {}).get("items") if isinstance(data, dict) else None
        by_id = {str(r.get("id")): r for r in (rows or []) if isinstance(r, dict)}
        for x in chunk:
            r = by_id.get(str(x.get("id"))) or {}
            code = str(r.get("code") or "").strip().upper()
            ev = tax.event_for_code(code)
            if not ev:
                ev = str(r.get("event") or "").strip()
                if ev not in EVENT_TYPES:
                    ev = x.get("event") if x.get("event") in EVENT_TYPES else "其他"
                code = tax.code_for_event(ev)
            q = str(r.get("quality") or "").strip().lower()
            out.append({"id": str(x.get("id") or ""), "event": ev, "code": code,
                        "title": str(r.get("title") or "").strip()[:18],
                        "quality": "fragment" if q == "fragment" else "complete",
                        "reason": str(r.get("reason") or "").strip()[:20]})
    if progress:
        progress(len(items), len(items), "完成")
    return out
