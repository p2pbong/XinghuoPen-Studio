# -*- coding: utf-8 -*-
"""v1.136 事件范例库·图书分类规则（分类号 + 类目树）。

像图书馆一样给每条范例一个分类号：一级类目（A 战斗冲突 / B 言语交锋 / C 成长突破 /
D 情感关系 / E 其他），二级为事件类型（A1 兵刃对决…）。分类号用于分组、检索与 AI 归类，
保证不同批次、不同来源的条目落在同一套架子上，不越分越乱。
"""

CATEGORIES = [
    ("A", "战斗冲突", [
        ("A1", "兵刃对决", "两人或少数人持兵器正面对决：起手—试探—交锋—变招—胜负落地"),
        ("A2", "群战围攻", "多人围杀/突围：站位、分批突入、破口、掩护撤退"),
        ("A3", "追逐逃杀", "追与逃：路线选择、路障、位置变化、脱身或被抓"),
    ]),
    ("B", "言语交锋", [
        ("B1", "谈判对峙", "落座试探—亮底牌—讨价还价—成交或谈崩"),
        ("B2", "宴席试探", "酒席/集会上的试探、敬酒、暗话、底线与散席"),
    ]),
    ("C", "成长突破", [
        ("C1", "突破渡劫", "铺垫与风险—临界—过程—成败—代价与后患"),
    ]),
    ("D", "情感关系", [
        ("D1", "情感爆发", "关系摊牌/决裂/和好：导火索—交锋—转折—结果"),
    ]),
    ("E", "其他", [
        ("E9", "其他", "以上都不贴切时归到这里，备注里写清是什么事件"),
    ]),
]

CODE_TO_EVENT = {}
EVENT_TO_CODE = {}
CODE_TO_CAT = {}
for _c, _cname, _subs in CATEGORIES:
    for _code, _ev, _desc in _subs:
        CODE_TO_EVENT[_code] = _ev
        EVENT_TO_CODE[_ev] = _code
        CODE_TO_CAT[_code] = (_c, _cname)


def code_for_event(event):
    return EVENT_TO_CODE.get((event or "").strip(), "E9")


def event_for_code(code):
    return CODE_TO_EVENT.get((code or "").strip(), "")


def catalog_text():
    """给 AI 的分类规则正文（类目树 + 判定口径）。"""
    lines = []
    for c, cname, subs in CATEGORIES:
        lines.append("%s %s" % (c, cname))
        for code, ev, desc in subs:
            lines.append("  %s %s：%s" % (code, ev, desc))
    return "\n".join(lines)


def groups():
    """[(一级名, [(code, 事件名), ...]), ...]"""
    out = []
    for c, cname, subs in CATEGORIES:
        out.append((cname, [(code, ev) for code, ev, _ in subs]))
    return out
