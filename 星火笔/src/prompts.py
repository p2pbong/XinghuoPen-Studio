# -*- coding: utf-8 -*-
"""提示词模板：主AI决断 / 角色推理 / 综合校验 / 写作 / 审查 / 战后更新 / 卷规划 / 角色生成。
所有提示词均要求无状态调用：上下文在每次调用时完整组装。"""
import json

MAIN_SYSTEM = (
    "你是一位资深小说主笔兼剧情架构师，深谙 RP（角色扮演）式小说自推理方法。"
    "你的一切输出都基于用户提供的既有设定与各角色的实际认知，绝不添加设定之外的信息。"
)

# v1.91 内置默认·章节标题命名规则（取自网文/文学标题命名经验：标题=章节钩子不是内容复述，
# 忌空泛词，具体动作+物件/身份关系/反差/数字优于抽象与修饰；xx与xx 可用但须真并列对照要素；
# 长度随本书气质）。用户可在重命名按钮旁/文风参考③.8 编辑，重置按钮可恢复本默认。
DEFAULT_TITLE_RULES = ("标题要浓缩本章发生的事，写成『章节钩子』而不是内容复述：亮出冲突、悬念或"
                       "情绪缺口，不把结果写进标题（剧透）；忌用『真相/秘密/震惊/意外来袭/惊天/大战』"
                       "这类空泛词；优先用具体动作+物件、身份+关系、反差对撞、具体数字"
                       "（如『保险柜里的照片有七个人，四个已经死了』）；『xx与xx』式可以用，"
                       "但两项须是本章真正并列/对照的要素，不硬凑、不连续多章同一句式；"
                       "长度随本书气质：网文向短句有钩子（约10~18字），文学向含蓄对仗（约2~8字，"
                       "如『梅雨夜的钢琴声』）；相邻章节句式要有变化。")

WRITER_SYSTEM = (
    "你是一位小说正文作者，笔力扎实、节奏沉稳。你严格依照主笔的裁定和各角色的行为指导写作，"
    "绝不让人物做出与其人设、认知不符的举动，不越权引入设定之外的内容。"
    "若用户提供了参考文风样本，你的行文应主动模仿其句式、语感、节奏与描写手法，"
    "让正文读起来与样本一脉相承。"
)


def main_system(project=None):
    """主AI系统提示词：基础 MAIN_SYSTEM + 用户自定义的主AI全局提示词（story_main_prompt）
    + v0.55 拆书风格参考（project.story_break_style 指向的拆书「设计技法学习文本」）。"""
    sys = MAIN_SYSTEM
    extra = ""
    if project is not None:
        extra = (project.story_main_prompt or "").strip()
    if extra:
        sys += "\n【用户对主AI的全局要求（最高优先，必须遵守）】\n%s" % extra
    # v0.55 拆书风格：主AI学习其剧情推动/伏笔设计技法（不抄情节）
    # v1.12 学习维度细化：事件长度（铺垫/发展/引爆/收尾各占多少章）、影响层级、伏笔与冲突安排
    if project is not None and (project.story_break_style or "").strip():
        try:
            import book_break
            learn = book_break.learning_text(project.story_break_style)
            if learn:
                sys += ("\n【拆书风格参考（你正在学习一部高分小说的剧情设计技法）。"
                        "下面的「设计技法学习文本」是拆书提炼的**可迁移方法**——请把它内化成"
                        "你自己的剧情设计能力，**设计剧情时必须主动运用**：\n"
                        "①**事件长度与节奏**：一个事件用多少章铺垫（起因）、多少章推进（经过）、"
                        "多少章引爆（高潮）、多少章收尾（结尾）——长短事件怎么交替，避免每一事件"
                        "篇幅雷同或拖沓；\n"
                        "②**事件影响层级**：这个事件影响多大范围（单章小事件/推动几章的中事件/"
                        "改变整卷格局的大事件）、影响哪些人物与关系、在主线/支线上留下什么后果"
                        "——事件结束后要点出它对后续剧情的连锁影响；\n"
                        "③**冲突与误导**：高潮冲突是怎么一步步产生的、中间埋了哪些误导/假象/"
                        "干扰，关键抉择落在哪一章；\n"
                        "④**伏笔与回收**：怎么埋设（借载体/日常）、隔多少章回收、用什么方式回收"
                        "（无意呼应/刻意回收/反转揭示）；\n"
                        "⑤**钩子与情绪节拍**：每一章结尾落什么钩子、情绪怎么起伏。\n"
                        "**只学这些技法，绝不照抄情节、人名或对话。**】\n%s" % learn)
        except Exception:
            pass
    return sys


def writer_system(project=None):
    """正文AI系统提示词：基础 WRITER_SYSTEM + 用户自定义的正文AI角色提示词（story_writer_prompt）。"""
    sys = WRITER_SYSTEM
    extra = ""
    if project is not None:
        extra = (project.story_writer_prompt or "").strip()
    if extra:
        sys += "\n【用户对正文AI的角色设定/风格要求（最高优先，必须遵守）】\n%s" % extra
    return sys


# ---------- 上下文格式化 ----------
def fmt_card(card):
    """酒馆（SillyTavern）风格角色卡：description 为综合主描述，缺失时回退拼接。"""
    lines = [
        "【角色卡】%s（%s，%s岁，%s）" % (card.name, card.role or "身份未知", card.age or "?", card.gender or "?"),
        "状态：%s" % {"active": "在世", "dead": "已阵亡", "traveling": "外出游历"}.get(card.status, card.status),
    ]
    desc = (card.description or "").strip()
    if desc:
        lines.append("【综合描述】%s" % desc)
    else:
        if card.appearance:
            lines.append("外貌：%s" % card.appearance)
        lines.append("性格：%s" % (card.personality or "（未设定）"))
        if card.backstory:
            lines.append("背景故事：%s" % card.backstory)
    if card.traits:
        lines.append("特质标签：%s" % "、".join(card.traits))
    if card.values:
        lines.append("价值观/底线：%s" % card.values)
    if card.goals:
        lines.append("目标/欲望：%s" % card.goals)
    if card.fears:
        lines.append("恐惧/弱点：%s" % card.fears)
    if card.speech_style:
        lines.append("说话风格：%s" % card.speech_style)
    if card.mes_example:
        lines.append("示例对话（模仿其语气）：\n%s" % card.mes_example)
    if card.relationships:
        lines.append("人际关系：%s" % card.relationships)
    if (card.plot_arc or "").strip():
        # v1.102 人物剧情线：角色卡标准视图统一带出，推理/盘点/审查都能看到未了之事
        lines.append("人物剧情线：%s" % card.plot_arc[:200])
    return "\n".join(lines)


def fmt_library(lib):
    lines = ["【信息库】该角色实际知道/经历的内容："]
    if (lib.scenario or "").strip():
        lines.append("当前场景/处境：%s" % lib.scenario)
    if lib.events:
        lines.append("经历的事件：")
        for e in lib.events:
            lines.append("- 第%s章：%s（影响：%s）" % (e.get("chapter", "?"), e.get("event", ""), e.get("impact", "无")))
    if lib.knowledge:
        lines.append("已知信息：")
        for k in lib.knowledge:
            lines.append("- 第%s章：%s" % (k.get("chapter", "?"), k.get("info", "")))
    if lib.secrets:
        lines.append("掌握的隐秘：%s" % "；".join(lib.secrets))
    if lib.notes:
        lines.append("备注：%s" % lib.notes)
    if not (lib.events or lib.knowledge or lib.secrets or lib.notes):
        lines.append("（暂无记录）")
    return "\n".join(lines)


def fmt_story(project):
    """故事设定（剧情 + 世界观 + 特殊规则，分栏给主AI）+ 本卷进度。

    故事描述只管剧情发展；世界观单独成栏（背景/势力/地理/力量体系）；
    特殊规则是用户的其他硬约束。三者都必须严格遵守。
    """
    lines = ["【故事设定（用户提供给总AI的主线依据，必须严格遵守）】"]
    brief = (project.story_brief or "").strip()
    if brief:
        lines.append("【剧情发展】%s" % brief)
    else:
        # 旧版兼容：opening + 结构化卷规划拼接
        if (project.opening or "").strip():
            lines.append("开局设定：%s" % project.opening)
        for v in project.volumes:
            lines.append("第%d卷（目标%d章）：%s" % (v.index, v.total_chapters, v.title or "无题"))
            for i, ev in enumerate(v.main_events, 1):
                lines.append("  %d. %s" % (i, ev))
            if v.ending:
                lines.append("  本卷结尾目标：%s" % v.ending)
            if v.next_hook:
                lines.append("  承接下一卷：%s" % v.next_hook)
            if v.notes:
                lines.append("  补充约束：%s" % v.notes)
    world = (project.story_world or "").strip()
    if world:
        lines.append("【世界观（世界的背景/势力格局/地理/力量体系/大概念，剧情必须服从）】")
        lines.append(world)
    rules = (project.story_rules or "").strip()
    if rules:
        lines.append("【特殊规则/其他设定（用户的硬性要求，写作时不得违反）】")
        lines.append(rules)
    style = (project.story_style or "").strip()
    if style:
        lines.append("【主AI风格设定（用户指定的文风/基调/视角/节奏等，写作与决断时必须体现）】")
        lines.append(style)
    target = project.chapter_target()
    written = project.written_chapters()
    if target > 0:
        lines.append("【本卷进度】目标 %d 章，已写 %d 章（当前第 %d/%d 章）。"
                     "必须推进剧情并完成目标章数。" % (target, written, min(written + 1, target), target))
    else:
        lines.append("【本卷进度】已写 %d 章，无固定章数上限（由你把控剧情节奏，"
                     "可适当设计分支剧情以丰富人物形象）。" % written)
    return "\n".join(lines)


def _brief_content(content, limit=90):
    content = (content or "").strip().replace("\n", " ")
    return content[:limit] + ("…" if len(content) > limit else "")


def _recent_scan(project, store, n=6):
    """构建「设定锚点」关键词匹配用的近期剧情文本：最近章节标题/梗概/正文片段
    + 开放伏笔 + 主AI管理笔记。中文关键词直接做子串匹配（不按词边界切分）。"""
    parts = []
    try:
        for i in sorted(store.list_chapter_indices())[-n:]:
            ch = store.load_chapter(i)
            if ch:
                parts.append("%s %s %s" % (ch.title or "", ch.brief or "",
                                           (ch.content or "")[:300]))
        for f in store.load_foreshadows():
            parts.append(str(f.text or ""))
    except Exception:
        pass
    parts.append((getattr(project, "story_summary", "") or "")[:600])
    return "\n".join(parts)


def fmt_lore(project, scan_text=""):
    """【项目设定锚点】注入段：常驻条目（always）每章必带，关键词条目仅在剧情文本
    命中其任一关键词时注入（中文子串匹配，不区分大小写）。返回空串表示无锚点。

    与故事设定同级硬约束：写作/决断/校验/审查/战后更新都会注入并遵守，
    避免长篇小说中重要设定被压缩笔记遗忘或模型自由发挥改掉。
    """
    entries = getattr(project, "lore_entries", None) or []
    if not entries:
        return ""
    scan = (scan_text or "").lower()
    active, matched = [], []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if e.get("always"):
            active.append(e)
            continue
        keys = [str(k).strip().lower() for k in (e.get("keys") or []) if str(k).strip()]
        if not keys:
            continue
        if scan and any(k and k in scan for k in keys):
            matched.append(e)
    selected = (active + matched)[:10]
    if not selected:
        return ""
    lines = ["【项目设定锚点（用户维护的硬性设定，与故事设定同级；"
             "写作/决断/审查都必须遵守，正文不得与锚点冲突）】"]
    for e in selected:
        title = str(e.get("title") or "").strip()
        content = str(e.get("content") or "").strip()[:400]
        if not content:
            continue
        if title:
            lines.append("■ %s：%s" % (title, content))
        else:
            lines.append("■ %s" % content)
    return "\n".join(lines)


def story_context(project, store, recent=4):
    """全书宏观上下文：主AI管理笔记（压缩卷）+ 进度 + 最近章节摘要。"""
    out = ["【故事整体进度】"]
    target = project.chapter_target()
    if target > 0:
        out.append("- 本卷目标 %d 章，已写 %d 章" % (target, project.written_chapters()))
    else:
        out.append("- 已写 %d 章（无硬性章数目标，主AI把控节奏）" % project.written_chapters())
    if project.volumes:
        for v in project.volumes:
            out.append("- 第%d卷：%s（目标%d章）" % (v.index, v.title or "无题", v.total_chapters))
    if (project.story_summary or "").strip():
        out.append("【主AI管理笔记（剧情压缩卷，勿与章节正文重复消耗上下文）】")
        out.append(project.story_summary)
    kcs = getattr(project, "story_characters", None) or []
    if kcs:
        out.append("【重要角色动向（主AI笔记；决断出场时优先考虑这些人）】")
        for kc in kcs[:15]:
            nm = str(kc.get("name", "") or "").strip()
            info = str(kc.get("info", "") or "").strip()
            if nm:
                out.append("- %s：%s" % (nm, info or "（无备注）"))
    ideas = getattr(project, "story_ideas", None) or []
    if ideas:
        out.append("【后续剧情灵感（主AI笔记；可择机展开的方向）】")
        for idea in ideas[:10]:
            out.append("- %s" % idea)
    if (project.story_knowledge or "").strip():
        out.append("【主AI知识库（联网搜集的灵感/重要设定/伏笔备忘，仅你（主AI）查阅，正文AI看不到）】")
        out.append(project.story_knowledge)
    if (project.opening or "").strip() and not (project.story_brief or "").strip():
        out.append("【开局设定】%s" % project.opening)
    indices = store.list_chapter_indices()
    done = sorted(indices)
    if done:
        out.append("【全书已写章节】%s" % ("、".join("第%d章" % i for i in done)))
        out.append("【最近章节概要】")
        for i in done[-recent:]:
            ch = store.load_chapter(i)
            if ch:
                brief = (ch.brief or "").strip() or _brief_content(ch.content)
                out.append("- 第%d章：%s — %s" % (ch.index, ch.title or "无题", brief))
    else:
        out.append("（尚无已写章节）")
    return "\n".join(out)


def char_pool(project, store, recent_chapters=10):
    """角色池两级视图（用于出场决断与写作约束）：

    1. 候选角色详单：近期出场 + 主要分类 + 管理笔记点名的角色，带一句话定位（主AI优先从中选）；
    2. 全量名册：所有角色一行（名字+状态），保证主AI永远「知道存在谁」——
       需要名册中但不在详单的角色出场时，在决断的 recall 字段点名，引擎会补充其完整档案再重判
       （长篇小说角色池庞大时，避免把几百张卡全塞进上下文导致注意力稀释/选择质量下降）。
    """
    items = store.list_characters()
    if not items:
        return "（暂无角色，可在「角色」页创建或自动生成）"
    # 近期出场（最近 N 章已归档章节的出场角色）
    recent_ids = set()
    try:
        for i in store.list_chapter_indices()[-recent_chapters:]:
            ch = store.load_chapter(i)
            if ch and ch.status == "approved":
                recent_ids.update(ch.characters or [])
    except Exception:
        pass
    # 管理笔记点名的重要角色（主AI笔记 story_characters 与 story_summary 中提及）
    note_names = set()
    for kc in getattr(project, "story_characters", None) or []:
        if isinstance(kc, dict) and kc.get("name"):
            note_names.add(str(kc["name"]))
    note_text = (getattr(project, "story_summary", "") or "")
    KEY_CAT = ("主要", "主角")
    detail, roster = [], []
    for cid, name, status in items:
        card, _ = store.load_character(cid)
        if not card:
            roster.append("- [%s] %s" % (cid, name))
            continue
        st = {"active": "在世", "dead": "已阵亡", "traveling": "游历中",
              "archived": "已归档(剧情价值已收,非必要不选)",
              "discarded": "已废弃(因删除章节移出,非必要不选)"}.get(status, status)
        line = "- [%s] %s（%s，%s）" % (cid, name, card.role or "?", st)
        roster.append(line)
        is_main = any(k in (card.category or "") for k in KEY_CAT)
        if cid in recent_ids or is_main or name in note_names or (name and name in note_text):
            desc = (card.description or card.personality or "").strip()
            one_liner = desc[:60] + ("…" if len(desc) > 60 else "")
            detail.append("%s\n　↳ %s" % (line, one_liner or "（无描述，可在名册中点名后补充档案）"))
    parts = ["【候选角色详单（优先考虑这些角色出场，每人一行定位）】"]
    parts.append("\n".join(detail) if detail else "（暂无活跃候选；可从下方名册点名或描述新角色）")
    parts.append("【全量名册（全部角色一览。若需名册中但不在详单的角色出场，"
                 "在输出 JSON 的 recall 字段点名其名字，系统会补充档案后请你重新决断）】")
    parts.append("\n".join(roster))
    return "\n".join(parts)


FORESHADOW_OVERDUE_CHAPTERS = 15  # 伏笔埋设后超过该章数未回收 → 标记「逾期」并强提醒主AI（设置页可配）


def _foreshadow_overdue_chapters():
    """伏笔逾期阈值（章）：读取设置页配置（config["foreshadow_overdue_chapters"]），默认 15。"""
    try:
        import config
        return max(1, int(config.load_config().get("foreshadow_overdue_chapters", 15) or 15))
    except Exception:
        return FORESHADOW_OVERDUE_CHAPTERS


def _overdue_mark(f, current_no, overdue_chapters=None):
    """伏笔逾期标记：open 且埋设章存在、距当前章超过阈值 → "⚠逾期N章"。否则空串。"""
    if overdue_chapters is None:
        overdue_chapters = _foreshadow_overdue_chapters()
    if f.status != "open":
        return ""
    planted = int(f.planted_chapter or 0)
    if planted <= 0:
        return ""
    gap = max(0, int(current_no or 0) - planted)
    if gap > overdue_chapters:
        return "⚠逾期%d章" % gap
    return ""


def open_foreshadows_text(fs_list, current_no=0, overdue_chapters=None):
    """开放伏笔清单（v1.100 双账本：事件线分组 + 人物/散笔；含逾期标注）。

    事件性质伏笔按 storyline 分组列出：线名 + 干系人 + 推进轨迹（最近2条）+
    下一步展开目标；人物性质伏笔与未归类伏笔列在散笔区。
    逾期伏笔是长篇写作的"欠账"——主AI决断/校验/压缩时都应优先安排回收。
    """
    if overdue_chapters is None:
        overdue_chapters = _foreshadow_overdue_chapters()
    opens = [f for f in fs_list if f.status == "open"]
    if not opens:
        return "（当前无开放伏笔）"
    lines = ["【开放伏笔清单（事件伏笔=跨章故事线，需持续展开；人物伏笔详情在对应角色卡 plot_arc）】"]
    by_line, singles = {}, []
    for f in opens:
        sl = (f.storyline or "").strip()
        if sl:
            by_line.setdefault(sl, []).append(f)
        else:
            singles.append(f)
    for sl, group in sorted(by_line.items()):
        mark = ""
        for f in group:
            m = _overdue_mark(f, current_no, overdue_chapters)
            if m:
                mark = m
                break
        rel = []
        for f in group:
            for c in (f.related_chars or []):
                if c and c not in rel:
                    rel.append(c)
        head = group[0]
        more = "（本条线共%d笔）" % len(group) if len(group) > 1 else ""
        line = "■ 事件线「%s」%s%s：%s（埋于第%s章%s）" % (
            sl, ("　" + mark) if mark else "", more, head.text,
            head.planted_chapter,
            ("；埋设要点：%s" % (head.planted_note or "").strip()) if (head.planted_note or "").strip() else "")
        if rel:
            line += "\n　↳ 干系人：%s" % "、".join(rel)
        else:
            line += "\n　↳ 干系人：%s" % (head.target_char or "无")
        prog = head.progress or []
        if prog:
            line += "\n　↳ 已推进：%s" % "；".join(prog[-2:])
        if (head.next_target or "").strip():
            line += "\n　↳ 下一步：%s" % head.next_target.strip()
        lines.append(line)
    for f in singles:
        mark = _overdue_mark(f, current_no, overdue_chapters)
        cat = {"character": "人物伏笔", "event": "事件伏笔"}.get(f.f_category or "", "伏笔")
        _note = (f.planted_note or "").strip()
        rel = "、".join(f.related_chars or []) or f.target_char or "无"
        lines.append("- [%s·%s] %s%s（干系人：%s；埋于第%s章%s）" %
                     (cat, f.f_type, f.text, ("　" + mark) if mark else "",
                      rel, f.planted_chapter,
                      ("；埋设要点：%s" % _note) if _note else ""))
    return "\n".join(lines)


def _foreshadow_related_cards(project, store, limit=5):
    """v1.100 与开放伏笔/剧情线相关的角色档案（人物伏笔详录所在地）。

    从开放伏笔的干系人/依托角色 + 主AI笔记点名的角色中匹配名册，
    注入其人物剧情线（plot_arc）/关系/当前处境——供主AI"先看笔记、再看相关角色卡"。
    """
    try:
        fs = store.load_foreshadows()
    except Exception:
        fs = []
    names = []
    for f in fs:
        if f.status != "open":
            continue
        for c in (f.related_chars or []):
            if c and c not in names:
                names.append(c)
        tc = (f.target_char or "").strip()
        if tc and tc not in names:
            names.append(tc)
    for kc in getattr(project, "story_characters", None) or []:
        nm = str(kc.get("name", "") or "").strip()
        if nm and nm not in names:
            names.append(nm)
    if not names:
        return ""
    name_to_id = {}
    for cid, nm, _st in store.list_characters():
        if nm and nm not in name_to_id:
            name_to_id[nm] = cid
    out = []
    for nm in names:
        cid = name_to_id.get(nm)
        if not cid:
            for n2, c2 in name_to_id.items():
                if nm and (nm in n2 or n2 in nm):
                    cid = c2
                    break
        if not cid:
            continue
        card, lib = store.load_character(cid)
        if not card:
            continue
        arc = (card.plot_arc or "").strip()
        rel = (card.relationships or "").strip()
        scen = (lib.scenario if lib else "") or ""
        parts = ["- %s（%s）：" % (card.name, card.role or "?")]
        if scen:
            parts.append("此刻%s。" % scen[:60])
        if rel:
            parts.append("关系：%s。" % rel[:70])
        if arc:
            parts.append("人物线：%s。" % arc[:120])
        if len(parts) == 1:
            parts.append("（档案无特别备注）")
        out.append("".join(parts))
        if len(out) >= limit:
            break
    if not out:
        return ""
    return ("【与开放伏笔/剧情线相关的角色档案（先读完笔记，再看这些角色卡，"
            "然后定本章剧情）】\n" + "\n".join(out))


def _cast_cards_text(store, inferences):
    """v1.100 本章出场角色档案摘要（consolidate 校验人设/人物伏笔的依据）。"""
    out = []
    for cid in list(inferences.keys())[:7]:
        if not cid or cid.startswith("_"):
            continue
        card, lib = store.load_character(cid)
        if not card:
            continue
        desc = (card.description or card.personality or "").strip()
        rel = (card.relationships or "").strip()
        arc = (card.plot_arc or "").strip()
        line = "- %s（%s，%s）：%s" % (
            card.name, card.role or "?", card.status,
            (desc[:90] + "…" if len(desc) > 90 else desc) if desc else "（无人设描述）")
        if rel:
            line += "；关系：%s" % (rel[:60] + "…" if len(rel) > 60 else rel)
        if arc:
            line += "；人物线：%s" % (arc[:100] + "…" if len(arc) > 100 else arc)
        out.append(line)
    if not out:
        return ""
    return ("【本章出场角色档案（主AI校验人设/人物伏笔依据；正文AI写作时不注入此块）】\n"
            + "\n".join(out))


def overdue_foreshadow_lines(fs_list, current_no=0, overdue_chapters=None):
    """逾期伏笔提醒段（仅列出已逾期的开放伏笔；无逾期返回空串）。"""
    if overdue_chapters is None:
        overdue_chapters = _foreshadow_overdue_chapters()
    out = []
    for f in fs_list:
        mark = _overdue_mark(f, current_no, overdue_chapters)
        if mark:
            out.append("- %s（埋于第%s章，依托角色：%s）" %
                       (f.text, f.planted_chapter, f.target_char or "无"))
    if not out:
        return ""
    return ("【逾期伏笔提醒（埋设已久仍未回收，本章应优先考虑回收其中一条；"
            "若确无合适时机，需在 issues 中说明为何延后）】\n" + "\n".join(out))


# ---------- 各环节 ----------
def decide_characters(project, store, chapter_no, vol_no, vol_rank):
    """主AI第一步：判断本章出场角色与场景焦点。"""
    target = project.chapter_target()
    sys = main_system(project) + "\n现在执行第一步：出场角色决断。只做决断，不写作正文。"
    lore = fmt_lore(project, _recent_scan(project, store))
    related = _foreshadow_related_cards(project, store)
    user = "\n\n".join([
        fmt_story(project),
        story_context(project, store),
        related if related else "",
        char_pool(project, store),
        open_foreshadows_text(store.load_foreshadows(), current_no=chapter_no),
        lore,
        (
            "【本章目标】全书第 %d 章，本卷第 %d/%d 章。%s\n"
            "请决断：本章的场景焦点是什么？哪些角色出场、各自在场景中的定位与戏剧功能？\n"
        "**scene_focus 必须写『可执行』的具体内容**：按『地点＋在场关键人物＋本章聚焦推进的事』"
        "写（如『集市暗巷：沈逸与老周核对符纸来路，发现铜钱压过的印痕多了一枚』）；"
        "本章确无单一焦点（纯过渡/铺垫）就写承接上一章结尾的具体推进点；"
        "**禁止『氛围感/张力/升华/细腻刻画』这类不可执行的空洞词**——正文AI要的是动词+对象，"
        "不是形容词气氛，精确大于天。\n"
        "**characters 的 notes（行为要点）同样要『可执行』**：写该角色本章具体要做什么/避免什么"
        "（动词+对象，如『先验物再谈价』），至少 2 条；没有特别要点留空串。\n"
            "注意：出场角色数量控制在 1-5 人，优先与近期剧情和主线相关；"
            "**优先从【候选角色详单】中选择**（那是近期活跃/主线重要角色）；\n"
            "若需要的角色在【全量名册】中但不在详单（如久未出场的旧角色要回归），"
            "就在 recall 字段点名其名字（可多个），系统会补充其完整档案后请你重新决断；\n"
            "若本章需要**名册中不存在**的全新角色（如新场景人物、新势力成员、敌方爪牙等），"
            "就在 new_character_hint 里给出一句话描述（主AI会自动为其建档并让该角色本章登场），"
            "characters 里照常列出原有角色；没有需要则留空。\n"
            "仅输出 JSON："
            '{"scene_focus":"本章场景事件焦点(40字内)：必须具体可执行——地点+在场关键人物+本章聚焦推进的事(动词+对象)；无单一焦点写承接上一章的推进点；禁空洞词(氛围感/张力/升华等)",'
            '"characters":[{"id":"角色ID(人物池中的id)","role_in_scene":"本章定位","notes":"本章行为要点：至少2条该角色具体要做什么/避免什么(动词+对象)，如『压下铜钱不问来路』『先让老周走、再关门验物』；没有特别要点就留空串"}],'
            '"considerations":"判断依据",'
            '"recall":["(可选)需点名召回的名册角色名，如\\"老渔夫张三\\""],'
            '"new_character_hint":"(可选)一句话描述需要的新角色，如\\"城主府的年轻文书，表面恭顺暗藏心机\\""}'
        ) % (chapter_no, vol_rank, target or 0,
             ("严格按本卷设定推进，完成目标章数" if target else "卷内容较空，由你把控节奏，可设计分支剧情丰富人物")),
    ])
    return sys, user


def reason_character(card, lib, chapter_no, scene_focus, project, store, role_in_scene="主角视角"):
    """代入单个角色，依据人设与已知信息推断行为。"""
    sys = (
        "你是一个 RP（角色扮演）推理引擎。你现在完全代入角色「%s」，"
        "一切推理只能基于该角色人设与其信息库中实际掌握的信息，"
        "绝不能使用信息库之外的知识（不知道的事就是不知道）。" % card.name
    )
    extra = (card.system_prompt or "").strip()
    if extra:
        sys += "\n该角色的附加扮演规则：\n%s" % extra
    user = "\n\n".join([
        fmt_card(card),
        fmt_library(lib),
        fmt_story(project),
        "【最新局势】%s" % scene_focus,
        "【该角色在本章场景中的定位】%s" % role_in_scene,
        (
            "请以「%s」的身份推断：ta 此刻在想什么、相信什么、打算做什么、会怎么说。\n"
            "仅输出 JSON："
            '{"intent":"本章想达成的目标(一句话)",'
            '"believes":["对当前局势的判断(基于ta已知信息)"],'
            '"actions":["可能采取的行动(2-4条,按ta的行事逻辑排序)"],'
            '"speech_hints":["可能说出口的话(2-3句,贴合其说话风格)"],'
            '"inner_conflict":"内心的矛盾或顾虑(可空)",'
            '"suspicion_points":["ta会怀疑/留意的点(可空)"],'
            '"possible_personality_shift":"(可选)若本章发生重大变故,性格可能的细微变化"}' % card.name
        ),
    ])
    return sys, user


def consolidate(project, store, chapter_no, scene_focus, inferences, new_char_pool_hint="",
                extra_context="", search_enabled=False, kb_prompt=""):
    """主AI第三步：综合各角色推理，校验主线；必要时加入新人物/新事件修正；同时管理伏笔。

    search_enabled=True 时允许主AI在不确定剧情走向时给出 search_queries（engine 会联网搜索后
    把结果作为 extra_context 重新喂回再判一轮）；kb_prompt 为知识库维护说明（默认走通用文案）。
    """
    sys = main_system(project) + "\n现在执行第三步：综合校验与主线把关。"
    # v1.100 先笔记 → 再看相关角色卡 → 定本章剧情：注入与开放伏笔相关的角色档案 + 本章出场角色档案
    related = _foreshadow_related_cards(project, store)
    cast_arch = _cast_cards_text(store, inferences)
    lines = [
        fmt_story(project),
        story_context(project, store),
        related if related else "",
        open_foreshadows_text(store.load_foreshadows(), current_no=chapter_no),
        fmt_lore(project, _recent_scan(project, store)),
        "【本章场景焦点】%s" % scene_focus,
        cast_arch if cast_arch else "",
        "【各角色推理结果】",
    ]
    for char_id, data in inferences.items():
        name = data.get("_name", char_id)
        lines.append("■ %s：" % name)
        lines.append("  意图：%s" % data.get("intent", "无"))
        lines.append("  判断：%s" % "；".join(data.get("believes", [])))
        lines.append("  行动倾向：%s" % "；".join(data.get("actions", [])))
        lines.append("  言语倾向：%s" % "；".join(data.get("speech_hints", [])))
        conflict = data.get("inner_conflict")
        if conflict:
            lines.append("  内心矛盾：%s" % conflict)
    if new_char_pool_hint:
        lines.append("【新角色候选提示】%s" % new_char_pool_hint)
    # v1.22 正文AI情景规则卡：项目级主AI可用库（project.scene_cards，与全局总库独立）。
    # v1.32 选卡策略改「按需精确匹配」：**不是每章都要选卡**——只有当本章剧情**确实包含**
    # 某类写法明显特殊的情景（激烈对抗/文斗交锋/大婚/绝境/大场面爆发等，按常规叙事写会
    # 寡淡/写不好），且库里有**真正匹配**该情景的卡时才选；平淡铺垫/日常推进/过渡/开篇
    # 引入等常规叙事章节一律不选卡（scene_cards 留空数组），正文AI按正常叙事节奏把铺垫
    # 写足——卡是为了写出特殊时刻的起伏，绝不因硬套卡而压缩铺垫、改变剧情节奏。
    _active_cards121 = []
    try:
        _active_cards121 = list(getattr(project, "scene_cards", None) or [])
    except Exception:
        _active_cards121 = []
    # v1.42 正文AI基础文风注入：主AI选卡/自制卡前先确认用户限定的正文文风（第一优先）
    _base_style_v142 = (getattr(project, "story_writer_prompt", None) or "").strip()
    _base_note_v142 = (getattr(project, "story_style_note", None) or "").strip()
    if _base_style_v142 or _base_note_v142:
        _stylines_v142 = ["【正文AI基础文风（用户对正文AI的全局限定，第一优先——情景卡只在其框架内"
                          "对对应情景片段做写法精修，两者冲突时以本文风为准；"
                          "**自制新卡同样必须契合该基础文风**）】"]
        if _base_style_v142:
            _stylines_v142.append("- 正文AI角色/风格限定：%s" % _base_style_v142)
        if _base_note_v142:
            _stylines_v142.append("- 风格要点：%s" % _base_note_v142)
        lines.append("\n".join(_stylines_v142))
    if _active_cards121:
        _card_lines = [
            "【正文AI情景规则卡（本项目主AI可用库名单，与全局总库独立）：**仅当本章剧情确实包含"
            "与某张卡匹配的特殊情景时才选用**——在输出 JSON 的 scene_cards 字段给出要启用的"
            "卡名（**可多选，各卡对应本章不同的情景片段；一章同时出现几个特殊情景就选几张，"
            "全选不漏，是分工组合而非单选**）。"
            "**选卡原则（v1.33/v1.40 必须遵守）**："
            "① 平淡铺垫/日常推进/过渡/开篇引入等**常规叙事章节不选卡**（scene_cards 留空数组），"
            "让正文AI正常铺垫、引入人物、推进剧情；"
            "② **只要本章确实出现某类特殊情景（激烈对抗/文斗交锋/大婚/绝境/大场面爆发/"
            "对话攻防/氛围酝酿等），且库里有内容匹配度足够高的卡，就应该选用它——宁可选中让"
            "正文AI参考，也绝不因怕选错而漏用**；**本章同时出现多个特殊情景时（如既有暧昧对话"
            "又有氛围酝酿又有景致反衬），必须把每个情景各自匹配的卡全部选上**——正文AI按卡"
            "各自片段分工取用、互不冲突；只当库中卡与本章情景**明显不匹配**（类型对不上、写法"
            "差异大）才不选，**绝不硬套不匹配的卡**；"
            "③ 若确认需要某类特殊情景的写法、但库里所有卡都不真正匹配，才自行**设计一张新卡**"
            "填进 new_scene_cards（**必须参考下方清单里已有卡的实际写法样例来写新卡——"
            "模仿其核心定位、分节结构、详略与表述风格，绝不凭空创造**；每章最多 1 张、"
            "名字不得与已有卡重复，新卡只存入本项目库标记「AI 制作」）；"
            "④ **必须输出 scene_cards_reason（一句话说明本条选卡判断的理由）**："
            "选中=说明命中了哪个情景哪张卡；不选=说明本章为何属于常规叙事/库卡为何不匹配"
            "（供运行记录展示，用于核对你的判断是否合理，漏用匹配卡会被认为失职）。"
            "【v1.30/v1.32 重要：卡只是**特殊情景片段的正文写法建议**，绝不影响你的剧情判断"
            "（人物状态/伏笔回收/剧情走向/chapter_beats 一律严格按上面章节内容与你的任务来），"
            "也绝不要求正文AI为了套卡而压缩铺垫或改变节奏；卡全文由正文AI按名单自行取用。"
            "**自制新卡参考（v1.35）：下方清单前 10 张卡附写法摘录，若需自做新卡必须参考"
            "这些摘录的写法/结构/详略，不凭空创造**】】"]
        for _i121, _c121 in enumerate(_active_cards121[:40]):
            _nm121 = str(_c121.get("name") or "").strip()
            if not _nm121:
                continue
            _src121 = "用户提供" if str(_c121.get("source") or "").strip() != "ai" else "AI 制作"
            _cat121 = str(_c121.get("category") or "").strip()
            _line121 = "■ [%s] %s%s" % (_src121,
                                        "〔%s〕" % _cat121 if _cat121 else "",
                                        _nm121)
            if _i121 < 10:
                _ct121 = str(_c121.get("content") or "").strip().replace("\n", " ")
                if _ct121:
                    _line121 += "：%s%s" % (_ct121[:150], "…" if len(_ct121) > 150 else "")
            _card_lines.append(_line121)
        lines.append("\n".join(_card_lines))
    else:
        lines.append(
            "【正文AI情景规则卡（本项目主AI可用库为空，**没有已有卡可参考**）。"
            "同样遵守 v1.33 原则：平淡/常规章节不选卡；仅当本章确实需要某类特殊情景写法"
            "（武打/文斗/大婚/绝境/大场面爆发等）时才自行**设计一张新卡**填进 new_scene_cards"
            "（按通用范例结构：核心定位+分节+写作执行自检清单；名字自定；每章最多 1 张）"
            "——新卡只存入本项目库（标记「AI 制作」），主AI后续章节也能选用；"
            "必须输出 scene_cards_reason 说明判断理由（为何不选/为何自做）。"
            "**卡只是特殊情景片段的正文写法建议，绝不要求为了套卡压缩铺垫/改变剧情节奏，"
            "也**绝不影响剧情判断**（人物状态/伏笔/剧情走向/chapter_beats 按上面章节内容来）。】")
    lines.append(
        "【你的任务】\n"
        "1. **逐条消化【各角色推理结果】**：先理解每个角色的意图/判断/行动倾向/言语倾向与内心矛盾，"
        "判断这些行为形成的合力是否符合本卷主线与用户约束；"
        "**本章的 chapter_beats、approved_direction 与小事件/细节引导必须以这些推理结果为基础**——"
        "人物在正文中的行为逻辑来自角色推理，主AI负责用事件引导让剧情沿主线走、同时不违背人物行为逻辑；\n"
        "2. **主动设计剧情走向**：只要情节需要（新场景人物、新势力成员、后宫新成员、"
        "推动主线的关键角色等），就主动用 action=add_character 引入新角色"
        "（附完整 new_character 角色卡，只立形象、不预设身世与秘密；"
        "**形象字段要立体丰满**：description 写 200-400 字（外貌气质/性格全貌/行为习惯/说话方式），"
        "personality/appearance/speech_style 各写一句以上具体细节，勿三言两语），"
        "主AI会自动建档并让该角色本章登场；需要转折或新矛盾时用 new_event 设计新事件；"
        "两者可同时给出；走向没问题才用 none；\n"
        "3. 裁定本章最终走向 approved_direction（**给正文AI的写作方向，必须按固定要素逐行写，"
        "v1.93 格式**）：\n"
        "   · 本章核心事件：『谁做了什么导致/发现什么』（动词+具体对象+结果）；\n"
        "   · 从哪到哪：承接上一章结尾状态（可引用其场景/悬念），本章结束时剧情推进到什么新状态；\n"
        "   · 必须传达的信息/对话要点：本章要露出的情报、要说清的关键话（没有写『无』）；\n"
        "   · 节奏与氛围（可执行版）：如『前半热闹铺垫，中段转暗巷独处、对话密度升高，结尾一句短句收在柜门声』；\n"
        "   · 结尾落点（为下一章衔接）：具体钩子/悬念/余波（没有写『无』）。\n"
        "   **每一行要素名都必须出现**；要素在本章确实没有时写『要素名：无』；"
        "**禁止用『升华/张力/氛围感/细腻/递进/精彩/震撼』等不可执行的空洞词指挥正文AI**"
        "（例：空洞『渲染温馨气氛』不如落地『写晚饭热气升起时两人谁都不先开口的沉默』——"
        "精确大于天，正文AI看不懂文艺腔）；总体≤180字；\n"
        "4. 伏笔管理（v1.100 双账本：事件伏笔=跨章故事线，人物伏笔=角色的未了之事，两条账分开记）：\n"
        "   - **事件性质伏笔**（f_category=\"event\"，默认）：新埋线必须给 storyline（线名，同线后续伏笔沿用同名）、"
        "related_chars（干系人角色名，事件牵涉谁就写谁）、planted_note（怎么埋的，≤60字）。"
        "**埋线不等于埋完**：若本章让某条已开放事件线取得哪怕一小步进展（发现线索/逼近一步/引出新矛盾），"
        "必须把进展写进 progress_update（step 给本章推进的具体一步，动词+对象；next 给下一步该在哪展开/由谁触发）；"
        "开放线本章完全没碰时，在 issues 里评估该线是否应推进（线不能凭空消失）；\n"
        "   - **人物性质伏笔**（f_category=\"character\"）：挂在特定角色身上的未了之事（渐变的秘密状态、临死留言、"
        "未兑现的承诺等）——target_character 必填，台账只记简账，详细前因后果会同步到该角色卡 plot_arc"
        "（本章若是伏笔新埋/推进/了结的关键章，战后更新会更新角色卡）；\n"
        "   - 回收（payoff）：可按伏笔文本、也可按事件线名回收（如『回收打渔令线』）；"
        "检查开放伏笔是否应在本章回收（先看【开放伏笔清单】的逾期与下一步）；\n"
        "   - **新埋伏笔必须给 planted_note（埋设要点，≤60字）**：写清这枚伏笔这一幕是**怎么露出来的**"
        "——依托的物件/场景/动作/无意间的一句话（如『主角在当铺翻到一封盖着陈记火漆的信，没敢拆』），"
        "供正文AI把埋设写实、供后续回收时精准呼应；\n"
        "5. 知识库维护：若本章有值得长期记住的内容（重要设定确认、关键人物伏笔落定、"
        "联网搜到的可复用灵感等），用 kb_update 给出一句话备忘（追加进主AI知识库，正文AI看不到）；"
        "没有则留空数组。\n"
        "6. 规划本章剧情点（chapter_beats）：2-3 个本章**要推进的具体剧情点**（每条 ≤25 字，"
        "写清本章发生的具体事与结果，如「潜入城主府摸清账册存放处」「与陈管家摊牌获知身世线索」）。"
        "**事件节奏（v1.37 必须遵守）**：一个完整事件（酝酿→发展→高潮→收尾）通常跨多章推进"
        "（几章到十几章、几十章），**绝不在单章内把一个事件从头到尾讲完**——本章 beats 只是当前"
        "事件链上的**一步**（推进一个环节/一个阶段），不是完整事件；参照【故事整体进度】的目标章数"
        "定节奏：目标章数多（长篇）→ 事件放慢、铺垫充分、高潮前置多章酝酿；目标章数少（短篇/紧凑）"
        "→ 事件密度高但也保留铺垫-发展-高潮-收尾的层次，且写完的章节仍与前后文衔接。"
        "**前后衔接**：beats 必须承接【最近章节概要】中上一章结尾的状态/悬念/现场继续推进；"
        "本章结尾为下一章留衔接（未解决的事件/新悬念/情绪余波），不在章内强行收束大事件；"
        "平淡铺垫章完全可以没有高潮，其作用就是酝酿。除非本章恰好处于事件的收尾位置，"
        "否则不要把『完成整个事件』写成 beat。正文写作必须逐条落地。\n"
        "7. 生成本章规划卡（v2.63 框架驱动，用于指导写作而非硬性条款）：\n"
        "   - planning_note：结合故事框架（本卷主线/故事简介/当前进度/用户约束）说明本章在整体故事中的"
        "定位与要达成的效果，≤60 字（如「以陈管家之死引主角深挖身世，奠定第一卷阴谋基调」；"
        "效果类型由框架决定——推进主线/悬念/情感/铺垫/转折均可，**不预设爽点**）；\n"
        "   - cliche_watch：结合本章具体情节，判断最可能落入的 2-3 个套路陷阱并给出规避点"
        "（具体到情节，如「不要让主角靠巧合获知密道位置」「反派不要主动解释阴谋」「不要用打脸循环收尾」；"
        "无明显风险可给 1 条通用提醒，也可留空数组）。\n"
    )
    if search_enabled:
        lines.append(
            "8. **联网搜索灵感（可选）**：若你对本章/后续剧情走向没有把握、或希望参考"
            "同类题材的常见写法来设计剧情，可在 search_queries 里给出 1-3 个搜索查询词"
            "（如\"悬疑推理 密室杀人 经典布局\"、\"废土公路片 团队冲突 情节设计\"），"
            "系统会联网搜索并把结果喂回给你重新决策；不需要则留空数组。\n"
        )
    kb_text = kb_prompt or "知识库维护：追加一句话备忘"
    lines.append(
        "仅输出 JSON："
        '{"verdict":"ok"或"adjust",'
        '"issues":["当前走向的问题(可空)"],'
        '"adjustment":{"action":"add_character|new_event|none",'
        '"new_character":{角色卡JSON: name,role,age,gender,personality,traits,values,goals,fears,speech_style,backstory,relationships,appearance,description,scenario,first_mes,mes_example,system_prompt},'
        '"event":"(仅new_event时必填)新事件描述——按结构写：事件名（拟占用章数范围）；引发的局面/后果或制造的悬念（30-60字，动词+对象，可执行）"},'
        '"approved_direction":"本章走向的最终裁定——按固定要素逐行写，每行『要素名：』开头'
        '（本章核心事件/从哪到哪/必须传达的信息与对话要点/节奏与氛围(可执行版)/结尾落点；'
        '某要素确实没有就写『要素名：无』，但要素名必须逐行出现；总体≤180字；禁空洞词见任务说明）",'
        '"chapter_beats":["本章推进的剧情点1(≤25字,当前事件链上的一步,非完整事件)","剧情点2"(2-3条)],'
        '"planning_note":"本章在整体故事中的定位与要达成的效果(≤60字,基于故事框架裁定,不预设爽点)",'
        '"cliche_watch":["本章最可能落入的套路陷阱规避点1","规避点2"(2-3条,可空数组)],'
        '"scene_cards":["(可选)选中的正文AI情景规则卡名（**只填卡名本身，不要带【分类】前缀和来源标注**，如\\"环境奇观渲染描写\\"而不是\\"〔氛围酝酿〕环境奇观渲染描写\\"，否则系统按卡名匹配不到库里的卡会白选；**可多选——本章同时出现几个特殊情景就选几张、全选不漏**，各卡对应本章不同的情景片段、分工组合互不冲突；无匹配则空数组）"],'
        '"scene_cards_reason":"(必填,一句话)本条选卡判断的理由：选中=本章哪个情景命中了哪张卡；不选=本章为何常规叙事/库卡为何不匹配；自做=需要但无匹配所以设计新卡（供运行记录展示，漏用匹配卡会被认为失职）",'
        '"new_scene_cards":[{"name":"(可选,仅当本章正文类型在本项目可用库里无匹配卡时)自行设计的新情景卡名,不得与已有卡重名;自制前必须参考上方清单中已有卡的写法摘录(结构/详略/表述风格),不凭空创造","content":"按范例结构(核心定位+分节+写作执行自检清单)的完整卡内容,只存入本项目库"}],'
        '"foreshadows":[{"f_type":"plant|payoff","f_category":"event|character(事件=跨章故事线/人物=角色未了之事,缺省event)","text":"伏笔内容","storyline":"(事件伏笔必填)事件线名,同线沿用同名,如『打渔令』","related_chars":["(事件伏笔)干系人角色名"],"target_character":"角色名或空","timing":"本卷|下卷|近几章","planted_note":"(仅plant必填,≤60字)埋设要点：借什么物件/场景/动作/台词怎么露出来的"}],'
        '"progress_update":[{"key":"已有事件线的伏笔id或线名","step":"本章该线推进的具体一步(30字内,动词+对象)","next":"下一步该在哪展开/由谁触发(20字内,可空)"}](开放事件线有推进才填,无则空数组),'
        '"need_chapters":["若前文概要不足以支撑判断,列出需要回顾的章节号,如\\"3\\";否则留空数组"],'
        '"kb_update":["%s(可空数组)"],'
        '"search_queries":["(可选,仅联网搜索开启时)需要搜索的查询词;不需要则空数组"]}'
        % kb_text
    )
    return sys, "\n".join(lines)


def adapt_project_scene_card_ai(project, cards):
    """v1.42 主AI按本项目正文AI基础文风（story_writer_prompt + story_style_note）改写项目库情景卡。

    每张卡只调整写法表述（详略/句式/用词/示例口吻），**保持卡名、分类、核心定位与适用情景
    完全不变**——卡仍然只讲该情景怎么写、不写怎么做，只是让它读起来、执行起来契合本项目
    正文AI的基础文风。只改项目库，无关总库。返回 (sys, user)。
    """
    sys = (
        "你是一位资深小说主笔兼情景写作规则设计师。用户给定了本项目正文AI的**基础文风**"
        "（全文第一优先的全局风格限定）。下面每张情景规则卡都要**保持情景内核与结构完全不变**，"
        "只把写法表述调整到契合该基础文风：该浓的浓、该省的省，句式口吻、详略取舍、示例风格"
        "贴合基础文风，但卡的适用情景、核心定位、自检清单的**语义**一个字都不许丢，也不许新增"
        "剧情/行为指令（卡只讲怎么写）。"
    )
    _lines = ["【正文AI基础文风（第一优先，适配必须契合它）】"]
    _base = (getattr(project, "story_writer_prompt", None) or "").strip()
    if _base:
        _lines.append("- 正文AI角色/风格限定：%s" % _base)
    _note = (getattr(project, "story_style_note", None) or "").strip()
    if _note:
        _lines.append("- 风格要点：%s" % _note)
    if not (_base or _note):
        _lines.append("（项目未设置基础文风——按卡的原写法保持，只做轻度润色）")
    _lines.append("【待适配情景卡（逐张输出 adapted，name 保持原名，content 为适配后的完整卡内容）】")
    for _i, _c in enumerate(cards, 1):
        _nm = str((_c or {}).get("name") or "").strip()
        _ct = str((_c or {}).get("content") or "").strip()
        _lines.append("%d. 卡名：%s\n卡内容：\n%s" % (_i, _nm or "未命名", _ct or "（空）"))
    _lines.append(
        '仅输出 JSON：{"adapted":[{"name":"卡名原样保留","content":"适配后的完整卡内容"},...]}——'
        '每张输入卡对应一条 adapted；卡名保持一致；content 是完整新卡（含核心定位+分节+自检清单），'
        '不得省略结构。')
    return sys, "\n".join(_lines)


def _writer_prior_context(project, store, chapter_no, inferences):
    """v1.92 正文AI「前文脉络」增强：开放伏笔台账（含埋设要点）+ 出场关键角色的
    立场/动机/行事风格——正文AI据此写言行，不再只凭几句裁定干写。返回块文本或空串。"""
    blocks = []
    try:
        fs_block = open_foreshadows_text(store.load_foreshadows(), current_no=chapter_no)
        if fs_block and fs_block != "（当前无开放伏笔）":
            blocks.append("【前文伏笔台账（埋过的线不能断：正文涉及这些伏笔时按「埋设要点」写实，"
                          "该回收时呼应埋设；逾期优先处理）】\n%s" % fs_block)
    except Exception:
        pass
    stance_lines = []
    for char_id, data in list(inferences.items())[:7]:
        card = None
        try:
            card, _lib = store.load_character(char_id)
        except Exception:
            card = None
        name = data.get("_name") or (getattr(card, "name", None) if card is not None else None) or char_id
        role = (getattr(card, "role", "") or "").strip() if card is not None else ""
        bits = []
        if card is not None:
            for label, attr in (("目标", "goals"), ("原则", "values"),
                                ("忌惮", "fears"), ("行事风格", "traits"),
                                ("人物线", "plot_arc")):  # v1.102 人物线跟身走
                v = getattr(card, attr, "")
                if isinstance(v, (list, tuple)):
                    v = "、".join(str(x) for x in v if str(x).strip())
                v = str(v or "").strip()
                if v:
                    bits.append("%s：%s" % (label, v[:60]))
        intent = (data.get("intent", "") or "").strip()
        if intent:
            bits.append("本章意图「%s」" % intent[:60])
        if not bits:
            continue
        stance_lines.append("■ %s%s：%s" % (
            name, ("（%s）" % role) if role else "", "；".join(bits)))
    if stance_lines:
        blocks.append("【关键角色立场与动机（正文AI必须据此写言行——立场/动机/行事风格决定怎么做事，"
                      "本章意图决定这一章的动作）】\n%s" % "\n".join(stance_lines))
    return "\n\n".join(blocks)


def write_chapter(project, store, chapter_no, scene_focus, direction, inferences,
                  foreshadow_lines, target_chars, recent_chapters=3, draft="",
                  beats=None, planning_note=None, cliche_watch=None,
                  scene_cards=None, min_chars=None, max_chars=None):
    """正文AI写作本章正文。

    recent_chapters：注入最近 N 章正文全文（默认3，设置页可配），保证行文衔接；
    剧情压缩卷（story_summary）一并给出；主AI知识库（story_knowledge）不注入正文AI。
    draft：用户提供的本章草稿（可详细可粗略），AI 在草稿情节基础上扩写润色，禁止改变剧情。
    beats：主AI规划的本章剧情点（2-3 条，必须逐条在正文中落地，硬要求）。
    planning_note：v2.63 主AI基于故事框架裁定的本章意图（定位与效果，供定调，非硬条款）。
    cliche_watch：v2.63 主AI判断的本章套路陷阱规避点（负向约束，写作时主动规避）。
    scene_cards：v1.17 主AI按本章正文类型选中的情景规则卡（[{"name","content"}]），逐条注入。
    min_chars/max_chars：v1.17 用户自设的正文长度上下限（None=按 target×0.8/×1.15 自动）。
    """
    lore_text = fmt_lore(project, "\n".join([
        _recent_scan(project, store), scene_focus, direction, draft or ""]))
    lore_bullet = ("- 严格遵循【项目设定锚点】（若有）：人物状态/能力/关系、地点方位、"
                   "世界观规则不得与锚点或前文已定设定冲突；\n") if lore_text else ""
    # v2.62：黄金三章（开篇钩子）+ 承接上章结尾（续写衔接）
    # v2.63：开场方式由故事框架决定，不再硬性规定「危机/紧迫开场」
    golden_bullet = ("- 开篇黄金三章（本章在全书前 3 章）：本章要快速建立主角的核心冲突与吸引力，"
                     "开场方式由故事框架决定（参考：危机开场/悬念开场/紧迫情境开场/日常切入，"
                     "节奏快慢以故事类型为准），避免慢热铺陈、避免大段世界观说明；\n"
                     ) if chapter_no <= 3 else ""
    handover_bullet = ("- 承接上章结尾：开写前先承接上一章结尾留下的悬念/情绪/现场"
                       "（不突兀、不重复概述），在其基础上推进本章事件；\n") if chapter_no > 1 else ""
    beats_block = ""
    if beats:
        beats_block = "【本章剧情点（主AI规划，**必须逐条在正文中完成**，不得遗漏或跳过）】\n" + \
            "\n".join("· %s" % b for b in beats)
    intent_block = ""
    if planning_note and str(planning_note).strip():
        intent_block = "【本章意图（主AI基于故事框架裁定，据此定调，不视为固定模板）】%s" % \
            str(planning_note).strip()
    cliche_block = ""
    if cliche_watch:
        items = [str(x).strip() for x in cliche_watch if str(x).strip()]
        if items:
            cliche_block = "【本章套路陷阱预警（写作时主动规避，不得踩中）】\n" + \
                "\n".join("- 规避：%s" % s for s in items)
    lines = [
        fmt_story(project),
        "【主AI管理笔记（剧情压缩卷）】%s" % ((project.story_summary or "").strip() or "（暂无）"),
    ]
    # v1.92 正文AI前文脉络：开放伏笔台账（含咋埋的）+ 出场角色立场动机行为
    prior_block = _writer_prior_context(project, store, chapter_no, inferences)
    if prior_block:
        lines.append(prior_block)
    lines += [
        lore_text,
        beats_block,
        intent_block,
        cliche_block,
        "【本章场景焦点】%s" % scene_focus,
        "【主笔裁定与写作方向】%s" % direction,
        "【各角色行为指导】",
    ]
    # 最近 N 章正文全文（供行文衔接/风格延续参考；0 表示不读前文）
    done = sorted(store.list_chapter_indices())
    recent_n = int(recent_chapters or 0)
    if done and recent_n > 0:
        tail = [i for i in done if i < chapter_no][-recent_n:]
        if tail:
            lines.append("【前 %d 章正文（衔接参考——续写必须从**上一章结尾**的原句/现场接起，"
                         "不得另起炉灶；上一章话说到一半就从半句续，场景悬在哪就从哪开始）】"
                         % len(tail))
            for i in tail:
                ch_prev = store.load_chapter(i)
                if ch_prev and ch_prev.status == "approved":
                    content = ch_prev.content or ""
                    # v1.106 正文AI 直接读前文全文（用户：正文/主AI 就那几章，直接看全文，
                    # 不要截断限制——v1.105 的「开头400+结尾800」也是多此一举，一并放开）
                    if len(content) <= 20000:
                        excerpt = content
                    else:
                        excerpt = ("%s\n……（超长章中间省略）……\n%s"
                                   % (content[:4000], content[-2000:]))
                    lines.append("——第%d章《%s》——\n%s" % (
                        ch_prev.index, ch_prev.title or "", excerpt))
    for char_id, data in inferences.items():
        name = data.get("_name", char_id)
        lines.append("■ %s：意图「%s」；行动倾向：%s；言语倾向：%s" % (
            name, data.get("intent", ""),
            "；".join(data.get("actions", [])),
            "；".join(data.get("speech_hints", []))))
        card, _ = store.load_character(char_id)
        if card and (card.mes_example or "").strip():
            lines.append("  %s 的示例对话（严格模仿此语气写作该角色的台词）：%s"
                         % (name, card.mes_example.strip()[:400]))
        if card and (card.first_mes or "").strip() and data.get("is_first_appearance"):
            lines.append("  %s 首次登场：以「%s」开场" % (name, card.first_mes.strip()[:200]))
    lines.append("【遵循要求】各角色的**意图/行动倾向/言语倾向是本阶段 RP 推理的成果**，"
                 "正文中该角色的行为与对白必须据此落实（这是人设推演出的行为逻辑，"
                 "不得因情节推进而违背；卡/范式等写法参考不得凌驾其上）。")
    if foreshadow_lines:
        lines.append("【本章伏笔指令】%s" % "；".join(foreshadow_lines))
    style_ref = (project.story_style_ref or "").strip()
    if style_ref:
        lines.append(
            "【参考文风样本（用户指定的文风标杆，写作时必须主动模仿其语感、句式、节奏与描写手法，"
            "但不能照抄其内容）】\n%s" % style_ref)
    style_note = (project.story_style_note or "").strip()
    if style_note:
        lines.append(
            "【风格要点（归纳自文风样本与前文，写作时逐条体现，不可违背）】\n%s" % style_note)
    # v1.17 情景规则卡：主AI按本章剧情选中，注入正文AI。
    # v1.32 注入语义改「片段级参考」：卡只约束本章**对应情景片段**的写法；铺垫/过渡/
    # 日常/开篇引入等常规叙事段落必须按正常节奏写足，绝不为了套卡压缩铺垫或改变剧情。
    if scene_cards:
        _sc_lines = ["【本章情景规则卡（主AI按本章剧情选中，**多卡分工·片段级写法参考**）】",
                     "**优先级（v1.42 必须遵守）**：系统提示词中「用户对正文AI的角色设定/风格要求」"
                     "是全文**第一优先**的全局风格限定——情景卡只在其框架之内、对各自对应的情景片段做"
                     "写法精修；卡的任何规则与它冲突时一律以该全局风格为基准，卡不得凌驾或背离它。",
                     "适用方式：本章同时出现的多个情景片段（对话交锋、氛围酝酿、景致反衬等），"
                     "各自有一张对应的卡——**写哪类片段，就只参考对应的那张卡**；其他卡不适用于"
                     "该段。**铺垫/过渡/日常/开篇引入角色等常规段落按正常叙事节奏写足、自然推进，"
                     "既不受卡约束、也不许为了套卡压缩铺垫或改变剧情节奏**。"
                     "**多卡组合规则（必须遵守）**：① 每段文字只受『它所属片段类型』对应的那张卡"
                     "约束，**不得把多张卡的规则叠加在同一段**（对话段别用氛围卡的句式，氛围段别用"
                     "对话卡的节奏）；② 写对话交锋片段→用〔对话攻防〕类卡、写氛围酝酿/对视冲击→用"
                     "〔氛围酝酿〕类卡、写景致反衬人物内心→用〔氛围反衬〕类卡，依此类推——"
                     "卡名带〔分类〕或首行带【分类】即标注适用片段类型，据此对号入座；"
                     "③ 卡只是该情景片段的写法建议，不影响剧情判断。"
                     "**卡的边界（必须遵守）**：卡**只讲这类情景『怎么写』**——节奏铺陈、"
                     "感官细节密度、氛围用词、对白与留白的比例、段落长短变化、情绪渐变的"
                     "语言手法等**写法技法**；卡里**出现的任何具体行为/事件/情节字样都只是"
                     "写法的示例，绝不是让你照着做**——人物做什么、事件怎么发展、剧情怎么推进"
                     "一律以【本章剧情】与【各角色行为指导】为准。"]
        for _sc in scene_cards:
            _sc_name = str(_sc.get("name") or "").strip()
            _sc_ct = str(_sc.get("content") or "").strip()
            if _sc_ct:
                _cat_tag = ""
                _cat = str(_sc.get("category") or "").strip()
                if _cat:
                    _cat_tag = "〔%s〕" % _cat
                _sc_lines.append("■ %s%s：%s" % (_cat_tag, _sc_name or "未命名", _sc_ct))
        lines.append("\n".join(_sc_lines))
    if draft and draft.strip():
        lines.append("【本章草稿（用户提供，**必须以其情节为底**扩写润色成正式正文，禁止改变剧情）】\n%s"
                     % draft.strip())
    # v1.17 篇幅上下限：用户自设（min_chars/max_chars）优先，否则按目标×0.8/×1.15 自动
    if min_chars and max_chars and int(min_chars) > 0 and int(max_chars) >= int(min_chars):
        _lo = max(300, int(min_chars))
        _hi = int(max_chars)
        _len_text = ("全章必须控制在 %d～%d 字（中文），超出 %d 字或低于 %d 字都算不达标"
                     % (_lo, _hi, _hi, _lo))
    else:
        _len_text = ("全章必须控制在 %d±500 字（中文），即 %d～%d 字；超出 %d 字或低于 %d 字都算不达标"
                     % (target_chars, max(300, target_chars - 500), target_chars + 500,
                        int(target_chars * 1.15), max(300, int(target_chars * 0.8))))
    lines.append(
        "【写作要求】\n"
        "- 篇幅（**硬性要求，不符合会判定失败整章重写**）：%s；\n"
        "- 写前先定剧情量：本章只推进 **2-3 个剧情点**（宁可少写，写不完的明确留到下一章，"
        "绝不硬塞），全章按 4-6 个场景/幕组织、**每幕约 %d 字**，写完全章后自查总字数"
        "——不足就充实描写细节，超了就删减铺陈，务必落在目标区间内；\n"
        "- 以第三人称限知或跟随视角写作，突出人物内心与互动；\n"
        "- 对话要贴合各角色说话风格，行为要符合其意图；\n"
        "- 招式/技能/法宝/称号等命名要克制不浮夸：威力与使用者实力层级相称"
        "（凡人武者不用毁天灭地之招、低阶不用高阶禁术）；优先化用古代典籍典故"
        "（《周易》《道德经》《山海经》《孙子兵法》《庄子》《诗经》《楚辞》等）"
        "或传统武侠风格命名，杜绝中二堆砌、为炫而炫；\n"
        "- 用词与情景相称：日常/平淡场景用语克制，不用『砸』『撕裂』『气势凛然』『命悬一线』"
        "等程度过重的大词，比喻修辞贴合场景、不堆砌；\n"
        "- 行文反「AI八股」（要有真实的人味，研究结论：AI味=过度圆滑、过度工整、解释太满）："
        "段落长短随节拍变化（爽点压短、情绪链放长），忌通篇等长；对话标签少而自然，"
        "多用动作引出说话，忌每句「说道/问道/笑道」；情绪直写且带后果，"
        "忌空转总结（如「一丝悲伤涌上心头」）和每个情绪词都配微动作；比喻贴生活，"
        "忌「如寒冰般」式文学腔；留白让读者自己脑补，忌面面俱到解释太满；"
        "排比偶尔一两个，忌连续三五个；结尾用动作或对话收尾，忌总结升华感慨；"
        "禁用高频套词（出现必须改写）：「深吸一口气」「眼中闪过一丝」「嘴角勾起一抹」"
        "「不禁」「缓缓开口」「仿佛」等；\n"
        "- 情绪节奏（结合本故事框架与本章意图定调，v1.37）：情绪支点**不强制每章都有**——"
        "本章是铺垫/发展/过渡章时以自然推进与氛围为主，可以有平缓起伏而**不硬造高潮**；"
        "只有本章处于事件链的高潮/爆发位置（或主AI明确把本章定位为高潮章）才集中写高潮名场面；"
        "位置分布合理、别全堆在结尾；幕与幕之间可留小钩子/悬念牵引；**结尾按事件进度收束**——"
        "事件未完则留衔接钩子（承接上章-延续下章），不强行在章内收束大事件；\n"
        "- 反套路（负面约束，宁可慢不可套，v2.63）：杜绝『巧合推进』（主角刚需要就恰好得到/"
        "恰好遇见）、『反派主动解释计划或临死全盘托出』、『对话沦为设定说明书』"
        "（台词要服务性格与关系，不在对话里大段交代设定）、『每章固定受辱-打脸循环』、"
        "『危机全靠突然觉醒或天降救兵』；情节转折要有前文铺垫的因果，"
        "不给读者『这也太巧了』的观感；\n"
        "%s"
        "%s"
        "- 若提供了【本章草稿】：以其情节为底**扩写润色**成正式正文——补足描写与细节、"
        "修复与前文文风不一致处、丰富必要修辞；**可调整叙事结构**（如视角、叙述顺序）以优化叙事，"
        "但**禁止改变剧情走向、事件内容、人物决定与对话含义**；输出是完整的正式正文，"
        "不保留草稿的痕迹（不要出现'草稿'字样）；\n"
        "- 行文语感与前面已写章节保持一致（衔接前文风格，不突兀不跳戏；无前文时贴近文风样本"
        "与故事设定的基调）；\n"
        "%s"
        "- 人物言行要合乎身份、人设与场景逻辑（动手有动机、强弱分明、该回避就回避），"
        "不做尬演；\n"
        "- 结尾留下钩子或推进信息；\n"
        "- 先输出一行章节标题（格式：第%d章 标题），空一行后输出正文。"
        % (_len_text, int(target_chars / 5), golden_bullet, handover_bullet,
           lore_bullet, chapter_no)
    )
    # v1.01 章节标题风格引导：贴合本书类型与书名气质；v1.88 支持用户自定义命名规则
    # （story_title_rules，项目页「文风参考」可填，填了最高优先——不硬禁任何句式，
    # 只要求「合适、贴内容、合类型」）
    _trules = ((project.story_title_rules or "") if project is not None else "").strip()
    if _trules:
        lines.append(
            "- 章节标题要浓缩**本章发生的事**（冲突/转折/威胁/秘密/动作/抉择/悬念），"
            "贴合书名《%s》的气质，一般 2~10 字（文学向可略长）；\n"
            "- 【你为本书设定的章节标题命名规则（最高优先，必须执行）】\n%s"
            % (project.title or "", _trules))
    else:
        # 内置默认规则（与「重置为默认」按钮同一文本，见 DEFAULT_TITLE_RULES）
        lines.append(DEFAULT_TITLE_RULES)
    return writer_system(project), "\n".join(lines)


def retitle_chapters(project, store, start, end, with_content=True):
    """批量重新设计章节标题（v1.01；v1.82 默认读**完整正文**）：按本书类型与书名气质取题，
    逐章**依据该章完整正文取题**（开头铺垫+中间冲突+结尾钩子全看到，杜绝只看开头被带偏、
    杜绝脱离内容瞎取名），也可关闭读正文只按梗概/原标题（省 token，取题精度下降）。
    只改标题不碰正文。返回 (sys, user)。"""
    chs = []
    for i in range(int(start), int(end) + 1):
        ch = store.load_chapter(i)
        if ch is None:
            continue
        excerpt = ""
        if with_content:
            body = (ch.content or "").strip()
            if len(body) > 20000:
                # 异常超长章（正常章节 2~5 千字）：给开头+结尾——取题看点（高潮/钩子）多在结尾
                excerpt = (body[:15000] + "……（中间省略）……" + body[-5000:]).replace("\n", " ")
            else:
                excerpt = body.replace("\n", " ").strip()
        chs.append({"chapter": i,
                    "title": (ch.title or "").strip(),
                    "brief": (ch.brief or "").strip(),
                    "excerpt": excerpt})
    if not chs:
        raise ValueError("区间内没有可重命名的章节。")
    # v1.88 章节标题命名规则：内置通用默认（不硬禁任何句式，只要求合适/贴内容/合类型）
    # + 用户自定义（story_title_rules，项目页「文风参考」填写后最高优先）
    _trules = ((project.story_title_rules or "") if project is not None else "").strip()
    if _trules:
        _title_guide = [
            "- 先判断本书类型与基调（题材/文风从设定判断），标题要浓缩**这一章发生的事**"
            "（冲突/转折/威胁/秘密/动作/抉择/悬念），贴合**书名《%s》的气质**，一般 2~10 字"
            "（文学向可略长）；" % (project.title or ""),
            "- 【你为本书设定的章节标题命名规则（最高优先，必须执行）】%s" % _trules,
        ]
    else:
        _title_guide = ["%s" % DEFAULT_TITLE_RULES]
    user = "\n\n".join([
        fmt_story(project),
        "【任务】为下面各章**重新设计章节标题**（只改标题，不改正文与章节顺序）：",
        *_title_guide,
        "- 给了【正文摘录】的章节：**必须依据摘录里的实际内容取题**——这章的关键转折/威胁/"
        "秘密/钩子是什么，就围绕它取题；摘录不足以判断时再结合梗概与剧情走向，"
        "禁止脱离内容凭空硬套模板；",
        "- 没给【正文摘录】的章节（用户选择了省 token）：按梗概与前后文走向取题，"
        "能取多准取多准；",
        "- 不剧透关键转折与结局；原标题如合适可保留或微调；",
        "仅输出 JSON：{\"titles\":[{\"chapter\":章号,\"title\":\"新标题\"}]}",
        "【各章：原标题 / 梗概 / 正文摘录（摘录=该章完整正文）】",
        "\n".join("- 第%d章《%s》：梗概：%s；正文摘录：%s"
                  % (c["chapter"], c["title"] or "无题",
                     c["brief"] or "（无）", c["excerpt"] or "（未读取正文）") for c in chs),
    ])
    return writer_system(project) + "\n现在执行章节标题重设计。", user


def review_chapter(project, store, chapter, target, beats=None):
    """主AI审查（全自动模式下决定是否继续）。

    beats：主AI规划的本章剧情点（若有），审查时逐条核对是否在正文落地。
    """
    sys = main_system(project) + "\n现在执行本章审查。"
    beats_block = ""
    if beats:
        beats_block = "【本章剧情点（主AI规划，审查时逐条核对是否在正文中完成）】\n" + \
            "\n".join("· %s" % b for b in beats)
    user = "\n\n".join([
        fmt_story(project),
        fmt_lore(project, _recent_scan(project, store)),
        overdue_foreshadow_lines(store.load_foreshadows(),
                                 current_no=project.written_chapters() + 1),
        beats_block,
        "【本章正文】%s" % chapter.content,
        "【出场角色设定】",
    ])
    for cid in chapter.characters:
        card, lib = store.load_character(cid)
        if card:
            user += "\n" + fmt_card(card)
    user += "\n\n【下一章目标】%s" % target
    user += (
        "\n【审查要求】检查：人设是否OOC、是否推进主线、节奏是否拖沓、本章是否完整（有头有尾有钩子）；"
        "招式/技能/法宝/称号等命名是否浮夸违和——与使用者实力层级相称"
        "（凡人武者不用毁天灭地之招、低阶不用高阶禁术）、是否中二堆砌、"
        "是否可化用古代典籍典故（《周易》《道德经》《山海经》《孙子兵法》《庄子》《诗经》《楚辞》等）；"
        "人物行为是否符合身份、人设与场景逻辑、动机是否成立（不尬）；"
        "行文与用词是否贴合小说文风与当下情景——日常/平淡场景用词过重"
        "（动不动『砸』『撕裂』『气势凛然』『万籁俱寂』『命悬一线』等）、修辞堆砌、夸张失当"
        "都属于问题；"
        "AI八股/AI味：行文是否模板化——高频套词（「深吸一口气」「眼中闪过一丝」「嘴角勾起一抹」"
        "「不禁」「缓缓开口」「仿佛」等）、句式套路（连续三句以上排比、「不是……而是……」滥用、"
        "解释腔上帝感如「她不知道的是…」）、情绪空转、每章结尾总结升华感慨——"
        "密集出现的重度AI味属明显问题；"
        "设定一致性：对照【项目设定锚点】（若有）与本章正文，检查是否存在设定矛盾——"
        "人物状态/能力/关系、时间线、地点方位、世界观规则与锚点或前文已定设定冲突"
        "（如角色前文已断臂本章却完好、已毁地点又出现、人物对应当知道的信息表现得毫不知情等）；"
        "逾期伏笔：若上方给出【逾期伏笔提醒】而本章未回收其中任何一条，须在 issues 中"
        "说明延后回收的合理理由（不是剧情时机则说明，无理由延后算问题）；"
        "剧情点完成度：对照【本章剧情点】（若有），逐条核对是否在正文中落地——"
        "遗漏或只提不写的剧情点列入 issues（确需延后的说明理由）。"
        "套路化/情节尴尬（v2.63）：检查本章是否落入常见套路——巧合推进（主角靠巧合获得关键信息、"
        "逢凶化吉）、反派降智（主动解释阴谋、临死全盘托出）、对话沦为设定说明书（台词只为交代设定）、"
        "打脸循环（固定受辱-翻盘-炫耀三拍）、生硬转折（为推进剧情强行安排、缺少因果铺垫）；"
        "明显套路化或转折生硬属问题。"
        "**issues 必须如实列出本章发现的具体问题**（引用原文片段与问题所在，含轻微瑕疵；"
        "确实没有问题才留空数组）。只有**明显到出戏**的问题（命名浮夸、行为或文风严重违和、"
        "重度AI味模板化、明显套路化/情节尴尬、与锚点明显冲突）才 approved=false 并给出 "
        "rewrite_feedback 要求重写。\n"
        "仅输出 JSON："
        '{"approved":true或false,'
        '"issues":["发现的问题(若无则空数组)"],'
        '"pacing":"节奏评价",'
        '"scores":{"immersion":7,"rhythm":8,"payout":6,"character":8,"natural":7},'
        '"cliches":["检测到的套路(巧合推进/反派降智/对话灌输设定/打脸循环/生硬转折等;无则空数组)"],'
        '"rewrite_feedback":"(若需重写)给作者的修改指令；若通过则留空",'
        '"brief":"本章一句话梗概(30字内,供后续存档)",'
        '"next_direction":"下一章的推进方向建议"}'
        "（scores 为量化打分，各 1-10 分：immersion=沉浸感（有无出戏处）、"
        "rhythm=节奏感（爽点间距/有无大段无聊）、payout=情绪支点（本章是否有情绪支点、"
        "类型是否契合故事框架、位置是否合理）、character=人设贴合、"
        "natural=情节自然度（推进是否有因果铺垫、巧合是否适度、转折是否生硬、对话是否自然）；"
        "评分须与 issues 一致，缺项可不给）"
    )
    return sys, user


def editor_review(project, store, chapter):
    """AI 编辑审稿：以资深编辑视角通读整章，给全面修改意见。

    与主AI审查（判过不过+驱动重写）不同，编辑审稿输出面向作者的编辑批注：
    情节/人设/文风/节奏/逻辑/伏笔/对话逐项点评 + 具体修改建议。
    """
    sys = (
        "你是一位拥有二十年经验的资深小说编辑（审稿人），擅长长篇小说的结构、文风与连载质量把关。"
        "你的职责是像真人编辑一样通读整章，站在读者与平台的角度给出**可执行的修改意见**——"
        "包括：情节合理性与戏剧张力、人物言行是否偏离人设（OOC）、文风语感与句式问题、"
        "节奏张弛（该快则快该慢则慢）、伏笔的埋设与呼应、对话是否自然有个性、逻辑硬伤与时间线矛盾、"
        "招式/技能/法宝等命名是否浮夸违和（与使用者实力层级相称、是否中二堆砌、可否化用古代典籍典故）、"
        "人物行为是否合乎身份与场景逻辑（不尬）、"
        "设定一致性（对照项目设定锚点与前文已定设定，检查人物状态/能力/关系、时间线、地点方位、"
        "世界观规则是否有矛盾）等。"
        "你基于项目设定与角色卡判断，绝不臆造设定之外的内容；只点评本章，不替作者规划后续剧情。"
    )
    user_lines = [
        fmt_story(project),
        fmt_lore(project, _recent_scan(project, store)),
        "【本章标题】%s" % (chapter.title or "第%d章" % chapter.index),
        "【本章正文】%s" % chapter.content,
        "【本章出场角色设定】",
    ]
    got_card = False
    for cid in chapter.characters:
        card, _ = store.load_character(cid)
        if card:
            user_lines.append(fmt_card(card))
            got_card = True
    if not got_card:
        user_lines.append("（本章无角色卡记录或角色卡缺失）")
    user_lines.append(
        "【你的输出】仅输出 JSON：\n"
        '{"verdict":"整体评价（三选一：通过 / 问题较多 / 建议重写）",'
        '"strengths":["优点1","优点2",...],'
        '"issues":[{"category":"情节|人设|文风|节奏|逻辑|伏笔|对话|招式|行为|设定|其他","detail":"具体问题，尽量引用原文片段"}],'
        '"suggestions":["具体修改建议1（可直接执行）","建议2",...],'
        '"overall":"180字内总评：先总后分，语气像给作者的编辑批注"}'
    )
    user = "\n".join(user_lines)
    return sys, user


def update_after_chapter(project, store, chapter, open_fs_ids, planned_plants=()):
    """主AI战后更新：信息库、角色卡微调、角色状态(阵亡/游历)判断、伏笔回收。

    v1.101 新增正文反扫：new_foreshadows（正文AI/作者加戏新冒出的伏笔，登记进账本防丢线）
    + missed_plants（本章主AI安排的伏笔正文是否写实，未落地则提示）。
    """
    sys = "你是小说世界的维护引擎。本章正文已定稿，请更新世界状态。"
    extra = (project.story_main_prompt or "").strip()
    if extra:
        sys += "\n【用户对主AI的全局要求（最高优先，必须遵守）】\n%s" % extra
    user_lines = [
        fmt_story(project),
        fmt_lore(project, _recent_scan(project, store)),
        "【本章正文】%s" % chapter.content,
        "【本章出场角色及其当前角色卡】",
    ]
    for cid in chapter.characters:
        card, lib = store.load_character(cid)
        if card:
            user_lines.append(fmt_card(card))
            user_lines.append(fmt_library(lib))
        else:
            user_lines.append("- 未知角色ID：%s（角色卡已删除，忽略更新）" % cid)
    user_lines.append(
        "【你的任务】\n"
        "1. 对每个出场角色：\n"
        "   - 更新其信息库 library：**当前场景/处境 scenario**（本章结束后该角色身处何地、处境如何）、"
        "本章经历的事件 events、了解到的新信息 knowledge、可能获知的秘密 secrets、其他备注 notes；\n"
        "   - 若本章事件足以改变该角色**本身**（人设层面），给出 card_updates（只列发生变化的字段，可用: "
        "personality/goals/values/speech_style/relationships/description/plot_arc 等，"
        "description 是综合人设描述——仅当事件从本质上改变了其性格/言行习惯时才重写；"
        "处境变化请写入信息库 scenario，不要写进角色卡）；\n"
        "   - **人物剧情线（plot_arc）维护（v1.100）**：若本章涉及该角色身上的**未了之事/人物性质伏笔**"
        "（新埋、推进、变化——如暗怀身孕、身世线索又进一步、临死留言的指向出现新线索），"
        "把最新状态写进 card_updates.plot_arc（≤200字，写清前因后果与当前进展，如"
        "『自第12章起暗怀身孕未公开（仅贴身丫鬟知晓），本章显怀，正筹谋离京养胎』）；"
        "**没有变化或该角色没有人物线就不要给 plot_arc 字段**（避免覆盖旧记录）；\n"
        "   - 判断其世界状态 status：active(存活)/dead(阵亡，给出可信缘故)/traveling(离场游历)；不影响则填 unchanged；\n"
        "2. 角色阵亡或游历会导致信息传递中断——若某角色死亡，其掌握的未及传递信息自然消失或埋为悬念，不必强行解释。\n"
        "3. 检查开放伏笔（id 列表如下），若本章正文已自然回收/回应，列入 foreshadow_resolved。\n"
        "开放伏笔ID：%s\n"
        "4. **反扫本章正文（v1.101）**——正文里可能埋着主AI没安排的雷，必须把它登记回来：\n"
        "   - **new_foreshadows（正文新冒出的伏笔）**：通读【本章正文】，找出**账本上没有、本章主AI 也没安排过**"
        "的新伏笔/新悬念/新隐患——即正文AI 或作者加戏埋下的钩子（角色留一句没头没尾的话、出现一件透着蹊跷却"
        "与主线无关的物件/信件、某个举动明显留有后手等）。判断标准：有留白、有悬念感、读者会惦记『这后面有什么』；"
        "**纯日常描写/普通对话/氛围铺陈不算**。登记规则沿用伏笔双账本："
        "事件性质（跨章故事线）给 storyline（线名）+ related_chars（干系人）+ planted_note（在正文哪一幕、"
        "借什么露出的，≤60字）；人物性质（挂在某角色身上的事）给 target_character（必填）+ planted_note。"
        "**与账本已有伏笔重复的不报**（文本/线名/含义相同都算）；**本章主AI 安排过且正文写实了的不报**"
        "（那是正常落地，不是新增）；\n"
        "   - **missed_plants（本章安排的伏笔没写实）**：核对下列本章主AI 安排的伏笔文本，"
        "若正文里**完全没有出现、也看不出痕迹**（找不到对应描写），列入 missed 并给一句话原因；"
        "正文里有迹象就不算漏（不必逐字一致）。\n"
        "本章主AI 安排的伏笔：%s\n"
        "仅输出 JSON："
        '{"characters":[{"id":"角色ID","card_updates":{...仅人设变化字段...},"status":"active|dead|traveling|unchanged",'
        '"status_reason":"状态变化原因(unchanged则空)",'
        '"library":{"scenario":"当前场景/处境(50字内)",'
        '"events":[{"chapter":本章章号,"event":"经历的事","impact":"影响"}],'
        '"knowledge":[{"chapter":本章章号,"info":"了解到的新信息"}],'
        '"secrets":[...],"notes":"其他备注"}}],'
        '"foreshadow_resolved":["开放伏笔id"],'
        '"new_foreshadows":[{"text":"正文新出现的伏笔内容","f_category":"event|character(可空,自动推断)",'
        '"storyline":"(事件性质)线名,可空","related_chars":["干系人,可空"],'
        '"target_character":"依托角色名或空","planted_note":"在正文哪一幕/借什么露出的(≤60字)"}](无则空数组),'
        '"missed_plants":["本章安排但正文没写实的伏笔文本"](无则空数组)}'
        % ("、".join(open_fs_ids),
           "；".join(planned_plants) if planned_plants else "（本章无安排，跳过核对）")
    )
    return sys, "\n".join(user_lines)


def volume_closing(project, store, vol):
    """卷末总结与承接下一卷。"""
    sys = main_system(project) + "\n本卷已完结，请撰写卷末衔接。"
    indices = store.list_chapter_indices()
    user = "\n\n".join([
        fmt_story(project),
        "【全书最近章节】",
    ])
    for i in sorted(indices)[-6:]:
        ch = store.load_chapter(i)
        if ch:
            user += "\n- 第%d章：%s — %s" % (ch.index, ch.title, _brief_content(ch.content))
    user += (
        "\n\n仅输出 JSON："
        '{"summary":"卷末总结(150字内)：回顾本卷主线如何收束",'
        '"next":"承接下一卷(80字内)：结合故事设定已有的走向；若设定未规划下一卷则由你设计"}'
        "——禁止输出 JSON 之外的任何内容。"
    )
    return sys, user


def compress_summary(project, store, recent=8):
    """把前文归纳成主AI管理笔记；同时评估人物池，建议归档已无剧情价值的角色。"""
    sys = ("你是小说主AI的管理笔记整理器。把已写章节的剧情与各项信息归纳概括成一份详实的「管理笔记」，"
           "供主AI在后续章节决断/校验时快速把握全局，也让作者（用户）只看笔记就能知道前面发生了什么；"
           "要求按剧情脉络写清：之前发生了哪些事（起因→经过→结果）、涉及谁、对人物关系/局势有什么影响、"
           "当前各角色在何处/在做什么、哪些伏笔已埋/待回收、有哪些未兑现的承诺与设定——信息要具体可还原，"
           "宁可详细也不要压缩成干巴巴的要点；同时负责人物池管理，避免角色无限膨胀。")
    extra = (project.story_main_prompt or "").strip()
    if extra:
        sys += "\n【用户对主AI的全局要求（最高优先，必须遵守）】\n%s" % extra
    indices = sorted(store.list_chapter_indices())
    user_lines = [
        fmt_story(project),
        "【当前主AI管理笔记（旧版，可被覆盖重写；其中仍然有效的前情与信息必须保留，不得丢弃）】%s" % (
            (project.story_summary or "").strip() or "（无）"),
        "【当前主AI笔记·后续剧情灵感（旧版；其中仍值得展开的方向必须保留，不得因本次重写丢失）】%s" % (
            ("；".join(str(i) for i in (getattr(project, "story_ideas", None) or []))) or "（无）"),
        "【近期章节摘要（最近 %d 章）】" % recent,
    ]
    for i in indices[-recent:]:
        ch = store.load_chapter(i)
        if ch:
            brief = (ch.brief or "").strip() or _brief_content(ch.content)
            user_lines.append("- 第%d章：%s — %s" % (ch.index, ch.title or "无题", brief))
    user_lines.append("【开放伏笔（含逾期标注；逾期优先安排回收）】\n%s" %
                      open_foreshadows_text(store.load_foreshadows(),
                                            current_no=project.written_chapters()))
    user_lines.append("【当前主AI知识库】%s" % (
        (project.story_knowledge or "").strip() or "（无）"))
    user_lines.append(char_pool(project, store))
    user_lines.append(
        "【你的任务】\n"
        "1. 归纳概括管理笔记（写入 note 字段，篇幅可较自由——通常 800~1500 字，"
        "剧情量大时宁多勿少），按剧情脉络写清，包含：\n"
        "   - 主线进度：已推进到哪一步、当前局面、下一步要衔接什么；\n"
        "   - 已发生的关键剧情（按时间/因果顺序归纳）：最近这段前面发生了什么——"
        "事件起因→经过→结果、涉及谁、对人物关系与全局局势带来了什么影响；"
        "同时把旧笔记中仍然有效的前情**完整保留下来**（不是只留一句概括），"
        "保证用户单看这份笔记就能还原前面发生过的故事；\n"
        "   - 人物现状与立场动机：各出场角色现在身处何地、状态如何、与主角/势力的关系到了哪一步，"
        "以及**当前立场/动机/对主角的态度**（每人一两句，写清事实而非空话；正文AI会按此写言行）；\n"
        "   - 伏笔状态（v1.100 双账本）：哪些已埋/待回收——"
        "**事件性质伏笔（故事线）按线详录**：每条线写清 线名 + 埋于第几章 + 当时怎么埋的 + "
        "当前推进到哪一步 + 下一步应在哪里回收/展开（主AI靠这条持续展开不丢线）；"
        "**人物性质伏笔只写角色名+一句话**（详细前因后果存在该角色卡 plot_arc，此处简略即可、不重复占篇幅）；\n"
        "   - 重要承诺与未兑现设定（别丢）。\n"
        "2. 重要角色档案（key_characters 数组，每个一条：name + info 一句话）：\n"
        "   - 把**当前仍在剧情前线、后续很可能再出场**的角色挑出来（一般 5-15 个），"
        "info 写清：ta 现在身处何地、状态如何、与主角/势力的关系到了哪一步、"
        "接下来可能的动向或未解的心结（如：『身在铁砧城，暗查城主府账册，与主角关系回暖但仍有戒心』）；\n"
        "   - 每人再给 arc 字段（**该角色身上的未了之事/人物性质伏笔当前状态**，≤80字，"
        "如『暗怀身孕未公开（第12章起），正筹谋离京养胎』『第21章临死留言\"后面还有人\"，所指未明』；"
        "没有就写空字符串）——系统会把 arc 回写进对应角色卡 plot_arc，供后续章节主AI直接查阅；\n"
        "   - 只列重要角色，NPC/一次性龙套不列；信息要具体可执行，供主AI后续决断直接使用；\n"
        "3. 后续剧情灵感（ideas 数组，每条一句话）：\n"
        "   - 把值得展开的剧情方向写下来：待回收伏笔的展开方式、悬而未决的冲突、"
        "可回归角色的回归时机、新势力/新场景的引入点、人物关系的升级或破裂机会等；\n"
        "   - 3-8 条即可，宁缺毋滥，要具体（如：『某城支线：老板娘与城主府的旧怨可在主角下次到访时引爆』）；\n"
        "4. 人物池管理：识别**已无剧情价值**的角色（一次性龙套、剧情线已收尾、"
        "单场景用完不再出场、长期未出场且本卷主线不再需要），列入 archive 数组（附角色 id 与一句话理由）；"
        "**核心角色、仍有剧情价值或埋有回收伏笔的角色绝不归档**；"
        "拿不准的小角色宁可归档（归档进角色卡库可随时恢复，不丢数据）也不要让它继续占在籍名额。\n"
        "5. 知识库维护（knowledge 字段，追加而非覆盖）：把值得长期记住的内容整理成条目"
        "（每条一行「- 内容」）：重要设定确认、关键伏笔落定、联网搜到的可复用灵感/剧情设计参考、"
        "角色的长期目标与秘密备忘等；若无新增内容则返回空字符串。\n"
        "仅输出 JSON：{\"note\":\"管理笔记正文(800-1500字，按剧情脉络归纳前文)\","
        "\"key_characters\":[{\"name\":\"角色名\",\"info\":\"现状/动向一句话\","
        "\"arc\":\"该角色身上的未了之事/人物伏笔当前状态(≤80字,无则空串)\"}],"
        "\"ideas\":[\"后续剧情灵感1\",\"灵感2\"],"
        "\"archive\":[{\"id\":\"角色ID\",\"reason\":\"一句话理由\"}],"
        "\"knowledge\":\"知识库新增条目(每行一条,无则留空)\"}"
    )
    return sys, "\n".join(user_lines)


def plan_story_ai(opening, user_notes, total_chapters_constraint="",
                  targets=("story", "world", "rules")):
    """AI 按用户想法起草故事设定（三块可勾选：剧情/世界观/特殊规则）。

    返回 JSON dict，键取 targets 中的项：story/world/rules。
    v1.95 结构硬性规范化：不预设题材、不强制宏大、不限定篇幅（具体类型与格局由用户想法决定），
    但**输出结构硬性规范**——与拆书工坊成果同构（主线总览→卷/事件细纲→人物/伏笔池），
    栏名必须全出现（无则写『栏名：无』）、禁空洞词；是否提供主AI提示词/拆书文档不影响该结构。
    """
    sys = (
        "你是一位小说创作顾问。你的任务是把用户的想法起草成**一套完整、可长期执行的故事设定**"
        "（剧情发展/世界观/特殊规则三块）。这套设定**会原样存入项目概况，主AI 后续每一章的判断"
        "都只看这三栏**——所以这不是一次性草稿：结构必须完整、内容必须可执行，宁可充实也不要"
        "一句带过。写什么由用户想法决定（不预设题材、不强行拔高格局），**但输出结构是硬性的，"
        "与用户是否提供额外的主AI提示词/拆书文档无关，一律按下述规范成文**。\n"
        "【硬性总则】三块都按规范结构输出：每个「栏名：」都必须出现，栏里确实没内容就写"
        "『栏名：无』，但**不允许省略任何栏名**；禁止用『氛围感/张力/精彩/细腻』这类不可执行的"
        "空洞词，用动词+对象、写明怎么推进的表述（组织方式对齐拆书工坊的成果：主线总览→卷/事件"
        "细纲→人物/伏笔池，让主AI 能照着推进剧情）。\n"
        "**表达形式（v1.97 硬性）**：三块一律用**给人看的自然语言文段**输出——就用普通中文句子、"
        "换行和『·』『①』这类自然标记分条，**严禁输出任何编程式语法**：不允许大括号{}、方括号[]、"
        "冒号引号键值对（'键': '值'）或 Python/JSON 字典数组写法；卷/事件/栏里的条目直接写中文，"
        "每卷或每事件一行/一段，读起来像一本书的设计稿，而不是数据结构。"
    )
    part_notes = []
    if "story" in targets:
        part_notes.append(
            "「story」剧情发展：**必须按四段结构输出，缺一不可**（与拆书成果『全书总览→卷事件细纲』"
            "同构）：\n"
            "一、主线总判：全书核心主线与终局走向（60-120字）；\n"
            "二、卷划分：**由你按全书规模判断分几卷**（短篇可不分或仅1~2卷，中长篇3~5卷，"
            "超长篇可更多），每一卷必须给出：卷题（5-15字）、**起止章号**、本卷剧情任务（30-60字），"
            "各卷章号要连起来**覆盖全书总章数**；\n"
            "三、卷内主要事件：每卷列主要事件（按该卷剧情量取，剧情密的多列、短小的少列），"
            "每个事件给：事件名（5-15字）+**占用章数范围**+一句话推进（15-30字）；\n"
            "四、全书结尾方向：终局如何收束、留哪些钩子/余味（30-60字）。\n"
            "没有用户想法时按你判断的题材基调自行构思，但**结构必须完整、章节号必须落得下**；"
            "本块建议 400-900 字。")
    if "world" in targets:
        part_notes.append(
            "「world」世界观：**必须按五栏输出，栏名全部出现**——①世界背景（时代/基调/大背景）；"
            "②地理或大概念地图；③势力格局（各势力/组织及其关系）；④力量体系（规则/等级/来源）；"
            "⑤种族/文明（如有）。每栏用「栏名：」开头；某栏确实没有内容就写『栏名：无』，"
            "但**栏名不许缺**；每条目按剧情需要写实写具体（30-100字/条），"
            "不堆砌无关设定，也不许一句话敷衍。本块建议 300-800 字。")
    if "rules" in targets:
        part_notes.append(
            "「rules」特殊规则/其他设定：**必须按三栏输出，栏名全部出现**——"
            "①金手指/主角特殊能力（若有）；②禁忌（剧情与写作层面都不允许的，如：不降智、不拖沓）；"
            "③叙事偏好（节奏/视角/文风等硬性要求）。每栏用「栏名：」开头；"
            "没有就写『栏名：无』，栏名不许缺；有实质内容就写具体（20-60字/条）。本块建议 200-600 字。")
    user = "\n".join([
        "【用户的故事想法】%s" % (user_notes or "（无）"),
        "【用户已有的开局/设定草稿（可留空）】%s" % (opening or "（无）"),
        "【章数约束】%s" % (total_chapters_constraint or "（无，章数由用户后续在项目页决定）"),
        "【需要你起草的部分】%s" % "\n".join(part_notes),
        (
            "只输出 JSON 对象，键为以上需要起草的部分（story/world/rules），值为自然语言草稿文字，"
            "按上述结构展开（story 约400~900字、world 约300~800字、rules 约200~600字，按剧情需要取长）。"
            "不要输出 JSON 之外的任何说明。"
        ),
    ])
    return sys, user


def revise_story_ai(project, store, targets, user_req, current, constraint=""):
    """v1.98 故事设定页「AI 辅助·按我的要求修改」：在现有三栏基础上，按用户修改要求
    修订剧情/世界观/特殊规则（只改要求的部分，其余尽量原样保留），输出完整修订版。

    与 plan_story_ai 同一套硬性规范（栏名必在/无则写『栏名：无』/自然语言禁编程式语法/禁空洞词），
    且**直接受主AI全局提示词（story_main_prompt）与拆书风格参考影响**——设计/修改剧情本就是
    主AI的工作。返回 (sys, user)；调用方 llm.chat_json 解析 {"story","world","rules"}。
    """
    require = (user_req or "").strip() or "（未给出具体修改要求——请按现有设定与主AI全局要求做整体完善，结构必须保持完整）"
    _secs = []
    if "story" in targets:
        _secs.append(
            "「story」剧情发展修订版：按四段结构输出——一、主线总判；二、卷划分（每卷含卷题、"
            "起止章号、本卷剧情任务，章号覆盖全书总章数）；三、卷内主要事件（事件名(章数范围)+一句话推进）；"
            "四、全书结尾方向。本块约400~900字。")
    if "world" in targets:
        _secs.append(
            "「world」世界观修订版：按五栏输出——①世界背景 ②地理/大概念 ③势力格局 ④力量体系 ⑤种族文明；"
            "本块约300~800字。")
    if "rules" in targets:
        _secs.append(
            "「rules」特殊规则修订版：按三栏输出——①金手指/主角特殊能力 ②禁忌 ③叙事偏好；本块约200~600字。")
    sys = (
        main_system(project)
        + "\n现在执行任务：按用户给出的修改要求，修订本项目的【剧情发展 / 世界观 / 特殊规则】设定。"
        "这是设定修订任务，不是章节正文写作。"
    )
    _extra = (getattr(project, "story_main_prompt", None) or "").strip()
    if _extra:
        sys += "\n【用户对主AI的全局要求（最高优先，必须遵守——修订后的设定要与它一致）】\n%s" % _extra
    user = "\n\n".join([
        "【现有剧情发展】%s" % ((current or {}).get("story") or "（无）"),
        "【现有世界观】%s" % ((current or {}).get("world") or "（无）"),
        "【现有特殊规则】%s" % ((current or {}).get("rules") or "（无）"),
        "【用户的修改要求】%s" % require,
        "【章数约束】%s" % (constraint or "（无，保持现有章数安排）"),
        "【修改原则（硬性）】只按用户要求修改对应栏：用户要求改哪些内容就改哪些，"
        "**没被要求改的段落尽量原样保留**（只做必要的衔接与一致性调整）；不推翻重写、"
        "不擅自扩充与要求无关的设定；修订后的三栏彼此自洽、并与主AI全局要求一致。",
        "【输出规范（硬性）】被勾选输出的每一栏都按规范结构书写，栏名必须全部出现，"
        "某栏确实没有内容就写『栏名：无』；一律用**给人看的自然语言文段**（普通中文、换行、"
        "『·』『①』分条），**严禁输出任何编程式语法**（大括号{}、方括号[]、引号键值对或"
        "Python/JSON 字典数组写法）；禁空洞词；每栏输出**完整修订版**，不要只写改动点。\n"
        "%s" % "\n".join(_secs),
        "仅输出 JSON 对象：{\"story\":\"…\",\"world\":\"…\",\"rules\":\"…\"}"
        "（只包含被勾选要修订的栏；值为自然语言完整文本；不要输出 JSON 之外的任何说明）。",
    ])
    return sys, user


def plan_chapters_ai(idea, story="", world="", rules="", author_constraint=""):
    """v1.73 一键成书「AI 自动判断章节数」：让 AI 根据故事想法+三栏设定判断全书合理总章数。

    返回 JSON {"chapters": int}（建议值）,由调用方 clamp 到 [1, 3000]。
    提示词要求按题材复杂度/剧情量定篇幅：短篇 20-40、中篇 60-120、长篇 200-500、
    超长篇 800+；不要只按用户有无明确数字——用户已给数字时直接遵循。
    v1.80：想法里写了章数要求时（如「不低于120章」）author_constraint 就是那条原话，
    这里把它当硬性约束：不低于/至少 N 章 = 下限，只可上浮不可低于。
    """
    sys = (
        "你是资深小说策划编辑。根据用户的小说想法与已起草的故事设定，判断这本书**全书总共"
        "写多少章**最合适：\n"
        "· 考虑题材复杂度、卷划分、事件量、主线长度——设定起草时已有的卷划分是最可靠的"
        "篇幅依据；\n"
        "· 参考量级（不是硬性规定，依剧情量灵活）：短篇 20-40 章、中篇 60-120 章、"
        "长篇 200-500 章、超长篇 800 章以上；\n"
        "· **【用户章节要求】必须严格遵循**：用户写了「不低于/至少 N 章」表示全书至少 N 章"
        "（只可上浮、不可低于）；写了「约 N 章」以 N 为基准小幅浮动；两者都是硬约束，"
        "不允许无视用户数字自行定一个更小的数；\n"
        "· 只输出 JSON：{\"chapters\": 数字}，不要多余解释。"
    )
    idea_txt = (idea or "").strip() or "（无想法）"
    user = "\n".join([
        "【用户的想法/要求】%s" % idea_txt,
        "【用户章节要求（有则必须严格遵循，不可低于）】%s" % ((author_constraint or "").strip() or "（未指定）"),
        "【剧情发展（草案）】%s" % ((story or "").strip()[:1500] or "（无）"),
        "【世界观（草案）】%s" % ((world or "").strip()[:800] or "（无）"),
        "【特殊规则（草案）】%s" % ((rules or "").strip()[:600] or "（无）"),
        "请判断全书总章数，只输出 JSON。",
    ])
    return sys, user


def extract_scene_card_ai(type_name, sample_text, prompt=None):
    """v1.19 根据用户提供的文本，提取某类型情景的规则卡内容。

    与 generate_scene_card_ai 同结构（核心定位 + 分节细则 + 写作执行自检清单，字数不限），
    但规则从「参考文本」的实际写法中提炼（可迁移的具体手法），不照抄原文；
    返回纯文本，由调用方允许用户编辑后再入库。
    v1.20 prompt：提取提示词（sys 侧）——传入用自定义，None 用内置初始（取自「初始提取.txt」微调）。
    """
    sys = prompt or _DEFAULT_EXTRACT_SYS
    sample = (sample_text or "").strip()
    if len(sample) > 6000:
        sample = sample[:6000] + "\n…（参考文本过长，已截断，请以可见部分为准）"
    user = "\n".join([
        "【情景类型】%s" % (type_name or "（未命名，请按参考文本实际体现的情景归类）"),
        "【参考文本】\n%s" % (sample or "（未提供文本）"),
        "【输出结构（必须完全按此组织，层与层之间用空行隔开）】",
        "- 第一行：一句「你是一位……的……家/作者，擅长……」式角色定位（声明该类情景下作者的身份与专长）；",
        "- 然后是「**核心定位：**」段：用一两句话点明该类情景写作的底层逻辑（读者在看什么、这段情景的本质是什么），"
        "所有细则都由它派生；",
        "- 然后按情景拆成若干「**一、……：**」「**二、……：**」…分节（可用：动作与对抗/对白与交锋/情绪与心理/"
        "节奏与起伏/氛围与环境/人物关系等，按情景需要取舍节数，不必凑齐固定节数），每节内用「- 」短句给"
        "**具体可执行**的规则（写什么、怎么写、必须出现什么、禁止什么），禁止空泛套话；",
        "- 最后一节必须是「**写作执行与自检清单：**」，把前面所有硬性要求收敛成逐条编号的清单"
        "（写完后逐条自检，任何一条不满足必须重写）；",
        "- **字数不做要求**——细则宁可写足写透也不要压缩成干条；但禁止注水重复同一意思。",
        "- **提炼要求**：规则必须来自参考文本中「%s」类情景的实际写法（句式/动作/对白/节奏/细节/"
        "情绪处理等可迁移的具体手法），把这些手法提炼成泛化规则；**禁止照抄原文句子、人物、情节**——"
        "参考文本只是素材，规则要能套用到任何同情景的正文。若参考文本里没有该类情景的写法，"
        "明确说明并退化为该类情景的通用规则。" % (type_name or "本类"),
    ])
    return sys, user


# v1.20 从文本提取情景规则卡的初始提取提示词（微调自用户提供的「初始提取.txt」：
# 保留通用文风分析师七维度骨架，输出收敛为情景规则卡结构，强调只提风格忽略情节人物）
_DEFAULT_EXTRACT_SYS = (
    "你现在是一位专业的小说写作风格分析师和情景规则卡设计师。\n"
    "我提供了一段参考文本（可能只是一类情景的片段，体裁不限）。\n"
    "你的任务是：\n"
    "仔细阅读参考文本，只提取写作风格特征，完全忽略具体人物姓名、背景设定、具体情节线索和事件发展。\n"
    "重点总结以下通用文学风格维度（必须详细、具体、可操作）：\n"
    "1. 语言质感与用词习惯：词汇的雅俗偏好（如：古风雅致、现代冷峻、口语化、书面语等），"
    "常用的高频形容词、动词及特定领域的术语；句式的长短节奏控制。\n"
    "2. 叙事视角与声音：叙述者的口吻（冷静旁观、深情沉浸、幽默调侃、压抑克制等），"
    "人称选择及其对读者代入感的影响，内心独白与外部描写的比例。\n"
    "3. 修辞与意象系统：最常用的比喻类型（明喻/暗喻/通感），核心意象群（如：自然景物、机械冷硬、"
    "色彩光影等），以及如何处理抽象情感的具体化表达。\n"
    "4. 环境与氛围营造：如何通过环境描写烘托情绪（情景交融的手法），对光线、声音、气味、温度等"
    "感官细节的侧重优先级及融合方式。\n"
    "5. 节奏与结构技巧：场景切换的方式（蒙太奇/线性推进），对话与动作描写的配比，"
    "高潮或转折点的情绪爆发力构建手法，留白与详述的艺术。\n"
    "6. 人物塑造风格：如何通过侧面描写、微表情、潜台词展现角色性格，而非直接陈述；"
    "角色互动的张力来源（权力关系、情感流动等）。\n"
    "7. 整体基调与美学风格：是华丽繁复、极简冷淡、荒诞黑色、还是温暖治愈？语调的情感浓度如何控制。\n"
    "将以上所有风格特征高度浓缩、系统化，整合成一个完整、详细、可直接复制的「该类情景写作规则卡」。\n"
    "规则卡必须以「你是一位……」开头，包含明确的「写作指令」和「禁止事项」，"
    "确保AI在生成新内容时100%遵循提炼出的规则，而非模仿原文剧情。\n"
    "***现在，请开始分析我给你的参考文本，直接给出规则卡，不要给我看分析过程，不要废话。"
)


def generate_scene_card_ai(type_name, detail=None):
    """v1.18 AI 一键写作某类型的情景规则卡内容（武打/文斗/见父母装傻充愣等）。

    v1.23 新增 detail 参数：用户给的细节方向/要求（可选，如「偏兵刃近身、狠辣致命」「大开大合、
    点到即止」），注入生成提示词让该卡的规则按方向设计；留空时与原行为完全一致。

    按「通用情景写作提示词.txt」范例结构组织：核心定位 + 分节细则 + 写作执行自检清单；
    字数不做要求（以完整可行为准）；返回纯文本，由调用方允许用户编辑后再入库。
    """
    sys = (
        "你是一位资深小说写作规则设计师，深谙各类小说各情景的写法差异。"
        "你的任务是为一类「正文情景」设计一段正文AI可直接照做的写作规则，"
        "让正文AI在该情景下写出有起伏、不寡淡、不含糊的内容。"
        "你的输出必须严格模仿范例「情景写作提示词」的结构层次，"
        "只是把具体内容换成针对该类情景的专属规则。"
    )
    _lines_ai = [
        "【情景类型】%s" % (type_name or "（未命名，请按通用情景设计）"),
    ]
    if detail and str(detail).strip():
        _lines_ai.append(
            "【细节方向（用户指定，这张卡必须按此方向设计，不能写跑偏；"
            "用户没给细节方向时才按该类情景的通用思路设计）】%s" % str(detail).strip())
    _lines_ai += [
        "【输出结构（必须完全按此组织，层与层之间用空行隔开）】",
        "- 第一行：一句「你是一位……的……家/作者，擅长……」式角色定位（声明该类情景下作者的身份与专长）；",
        "- 然后是「**核心定位：**」段：用一两句话点明该类情景写作的底层逻辑（读者在看什么、这段情景的本质是什么），"
        "所有细则都由它派生；",
        "- 然后按情景拆成若干「**一、……：**」「**二、……：**」…分节（可用：动作与对抗/对白与交锋/情绪与心理/"
        "节奏与起伏/氛围与环境/人物关系等，按情景需要取舍节数，不必凑齐固定节数），每节内用「- 」短句给"
        "**具体可执行**的规则（写什么、怎么写、必须出现什么、禁止什么），禁止空泛套话；",
        "- 最后一节必须是「**写作执行与自检清单：**」，把前面所有硬性要求收敛成逐条编号的清单"
        "（写完后逐条自检，任何一条不满足必须重写）；",
        "- **字数不做要求**——细则宁可写足写透也不要压缩成干条；但禁止注水重复同一意思。",
        "- 针对「%s」类情景的专属要点：该情景的戏剧张力在哪、怎么写才有起伏"
        "（如武打=攻防节奏与杀招取舍、文斗=言语交锋与心理攻防、见家长装傻=台词机锋与"
        "身份落差），避免写成通用写作套话。" % (type_name or "本类"),
    ]
    user = "\n".join(_lines_ai)
    return sys, user


def generate_character_ai(description, project, store):
    """AI 自动生成角色卡（酒馆 SillyTavern Persona 风格）。

    原则：角色卡只放「能立住形象」的人设（外貌/气质/性格/说话风格）；
    身世、秘密、具体关系等**不预设**，留给小说主AI在剧情中视情况设计。
    scenario（当前处境）属外在信息，写入信息库。
    """
    sys = "你是资深角色设计者，擅长塑造立体可信的人物，熟悉 SillyTavern（酒馆）角色卡体系。"
    pool_text = ""
    try:
        from prompts import char_pool
        pool_text = char_pool(project, store)
    except Exception:
        pass
    user = "\n\n".join([
        fmt_story(project),
        story_context(project, store) if store else "",
        pool_text,
        "【角色要求】%s" % (description or "设计一个与当前主线相关的配角"),
        (
            "生成一张能**立住形象**的角色卡（酒馆 chara_card_v2 规范），**形象要立体丰满、"
            "细节丰富，不要三言两语打发**：\n"
            "- description 写立体形象（250-450字）：外貌气质（体型/五官/神态/穿着风格）、"
            "性格全貌（核心性格 + 具体的行为习惯/口头禅/小动作 + 优缺点与矛盾点 + 隐藏的柔软处）、"
            "说话方式（语气/句式偏好）、日常会怎么待人接物——用具体细节把人物立起来，"
            "让正文AI能据此写出有辨识度的人物；\n"
            "- personality/appearance 字段单独写丰满（personality 100-200字：性格分层描述；"
            "appearance 80-150字：外貌多维度描写），不要只给一两个形容词；\n"
            "- **不要预设身世细节、秘密、具体人际关系和过往经历**——这些由小说主AI在剧情推进中"
            "视情况设计，角色卡的 role/age/gender 给一个基本轮廓即可（可空或模糊）；\n"
            "- scenario 只写该角色在故事当前阶段的基本处境（50字内），会存入信息库；\n"
            "- first_mes 是首次登场时说的话/动作（50字内）；mes_example 给 2-3 组示例对话教模型模仿语气；"
            "system_prompt 写扮演规则（可空）；post_history_instructions 剧情后置指示（可空）；\n"
            "- tags 给 2-4 个角色标签（如：主角/配角/反派/女性/青年 等分类标签）；"
            "character_version 固定 \"main\"；creator_notes 写一行设计备注（可空）。\n"
            "- **先核对上面的【全量名册】：角色名必须在名册中不存在（或明显不同），"
            "绝不生成与现有角色同名的角色卡。**\n"
            "仅输出 JSON："
            '{"name":"姓名","role":"身份/职业(可空)","age":"年龄(可空)","gender":"性别(可空)",'
            '"personality":"性格分层描述(100-200字)","traits":["2-4个特质标签"],'
            '"values":"价值观(可空)","goals":"当前目标(可空)","fears":"弱点(可空)",'
            '"speech_style":"说话风格(含口头禅示例)","backstory":"(留空)","relationships":"(留空)",'
            '"appearance":"外貌气质多维度(80-150字)",'
            '"description":"立住形象的综合描述(250-450字)","scenario":"当前基本处境(信息库用,50字内)",'
            '"first_mes":"首次登场台词/动作(50字内)","mes_example":"2-3组示例对话",'
            '"system_prompt":"扮演规则(可空)","post_history_instructions":"(可空)",'
            '"tags":["2-4个标签"],"character_version":"main","creator_notes":"(可空)"}'
        ),
    ])
    return sys, user


def generate_batch_roles(description, project, store):
    """AI 按用户自然语言需求批量生成角色卡：需求里直接指定角色/数量，AI 自行拆解。"""
    sys = ("你是资深角色设计者，擅长把一段模糊的需求拆解成一组立体可信、互不重复的角色，"
           "熟悉 SillyTavern（酒馆）角色卡体系。")
    pool_text = ""
    try:
        from prompts import char_pool
        pool_text = char_pool(project, store)
    except Exception:
        pass
    user = "\n\n".join([
        fmt_story(project),
        story_context(project, store) if store else "",
        pool_text,
        "【角色需求】%s" % (description or "设计 3 个与本卷主线相关的配角"),
        (
            "把上面的需求拆解成具体角色（**数量按需求决定且必须给满**：需求里明确写了几个"
            "（如『ABC 三个角色』）就必须输出几个，缺一不可——本批条数不足会整批不合格重试；"
            "需求未明确数量时 2-8 个）。"
            "每个角色**形象立体丰满、细节丰富，不要三言两语打发**（酒馆 chara_card_v2 规范）：\n"
            "- **name 是必填项、必须唯一**：不得与【全量名册】中任何角色同名或近似（会与已有角色"
            "合并），本批内部也不得重名——重名/缺名都会导致整批不合格被重试；\n"
            "- description 写立体形象（250-450字）：外貌气质（体型/五官/神态/穿着风格）、"
            "性格全貌（核心性格 + 具体行为习惯/口头禅/小动作 + 优缺点与矛盾点 + 隐藏的柔软处）、"
            "说话方式（语气/句式偏好）、日常待人接物——用具体细节立住人物，让正文AI能写出有辨识度的人物；\n"
            "- personality 100-200字（性格分层描述）、appearance 80-150字（外貌多维度描写），"
            "不要只给一两个形容词；\n"
            "- **不要预设身世细节、秘密、具体人际关系和过往经历**——由小说主AI在剧情中视情况设计；\n"
            "- scenario 只写该角色当前基本处境（50字内）；first_mes 是首次登场台词/动作（50字内）；\n"
            "- mes_example 给 2-3 组示例对话；system_prompt 写扮演规则（可空）；"
            "post_history_instructions 剧情后置指示（可空）；\n"
            "- tags 给 2-4 个角色标签；character_version 固定 \"main\"；creator_notes 一行设计备注（可空）；\n"
            "- 角色之间要有辨识度。\n"
            "仅输出 JSON："
            '{"characters":[{"name":"姓名","role":"身份/职业(可空)","age":"年龄(可空)",'
            '"gender":"性别(可空)","personality":"性格分层描述(100-200字)","traits":["2-4个特质标签"],'
            '"values":"价值观(可空)","goals":"当前目标(可空)","fears":"弱点(可空)",'
            '"speech_style":"说话风格(含口头禅示例)","backstory":"(留空)","relationships":"(留空)",'
            '"appearance":"外貌气质多维度(80-150字)","description":"立住形象的综合描述(250-450字)",'
            '"scenario":"当前基本处境(信息库用,50字内)","first_mes":"首次登场台词/动作(50字内)",'
            '"mes_example":"2-3组示例对话","system_prompt":"扮演规则(可空)",'
            '"post_history_instructions":"(可空)","tags":["2-4个标签"],'
            '"character_version":"main","creator_notes":"(可空)"}]}'
        ),
    ])
    return sys, user


# ======================================================================
# 去AI味（对已生成章节做后处理润色：不改剧情，只动表达/描写/用词）
# ======================================================================
DEAI_DEFAULT_RULES = """【清除/改写类】
1. “不是……而是……”式说教转折（“他感到恐惧，不是因为……而是因为……”）——删掉，改用直接呈现；
2. 上帝视角解释句（“他不知道……”“他忽然明白……”“他意识到……”“他想……”）——能改用动作/对话呈现的就改写，纯解释直接删；
3. 段末升华说教（“这让他明白，人生就是这样……”“原来世间……”“他终于懂得……”）——删掉，给读者留白；
4. 程度副词堆砌（很、非常、极其、彻底、完全、瞬间、无比）——多数删去，有必要处换具体细节（“很冷”→“呵气成霜”）；
5. AI 高频动作套话（指尖发白、目光一凝、嘴角勾起一抹、心头一凛、眼神一暗、喉结滚动）——换成有具体细节的动作或删；
6. 连用“似乎/仿佛/好像”——全段至多保留一处；
7. 描述写成解释（“他感到愤怒”“她心里委屈”）——改用动作、神态、语言呈现；
8. 说教口吻：俯视读者地把道理讲出来——删。

【句式/词形替换类】（只替换，不动结构内容）
1. “缓缓”等慢动作副词连用——删或换一步具体动作；
2. “不由地/忍不住/下意识地”——视语境删或换；
3. “顿时/当即/霎时”——至多留一处；
4. “一股……涌上心头/心头一热”——换直接描写；
5. “眸中/眼底”——口语化上下文换“眼中/眼神”。"""


def deai_audit(project, chapter, rules="", nearby_text=""):
    """去AI味·整体审查：通读整章，按规则找出所有 AI 味问题位置（引用原文片段 + 问题类型 + 建议）。

    审查结果再喂给 deai_chapter 的 audit_issues，让清洗/替换/重写有据可依——
    而不是单纯按句子机械替换（用户要求：不先审查整体，只换句子没意义）。
    nearby_text：v1.07 前后章节参考（main_ai 组装传入）——核对剧情衔接用，
    审查时若发现本章与前后文已写内容冲突（人物状态/地点/时间线），也列入问题。
    """
    sys = writer_system(project)
    parts = [
        "【任务】对本章做**整体文风审查**：逐句通读全文，按下面规则找出所有 AI 味问题。"
        "重点排查：\n"
        "1. “不是……而是……”式说教转折；\n"
        "2. 上帝视角解释句（他不知道/他忽然明白/他意识到/他想…）；\n"
        "3. 段末升华说教（这让他明白…/原来世间…/他终于懂得…）；\n"
        "4. 程度副词与重词堆砌（很/非常/极其/彻底/完全/瞬间/无比/砸/砍/撕裂/狠狠/猛地）；\n"
        "5. AI 高频动作套话（指尖发白/目光一凝/嘴角勾起一抹/心头一凛/眼神一暗/喉结滚动/眼底一沉）；\n"
        "6. “似乎/仿佛/好像”连用、慢动作副词（缓缓）滥用；\n"
        "7. 描述写成解释（他感到愤怒/她心里委屈）等；\n"
        "8. 说教口吻、俯视读者的道理总结。\n"
        "**宁可多列不可漏**：只要某句明显有上述问题的都要列出。",
        "【用户校对规则（可编辑；优先遵循，与上面重复的以它为准）】\n%s" % ((rules or "").strip() or DEAI_DEFAULT_RULES),
    ]
    if (nearby_text or "").strip():
        parts.append(nearby_text.strip())
    parts.append("【本章原文（完整）】\n%s" % (chapter.content or ""))
    parts.append(
        "【你的输出】仅输出 JSON：\n"
        '{"issues":[{"quote":"有问题的原文句子（逐字引用，30-80字）",'
        '"problem":"问题类型（如：上帝视角解释/说教转折/重词滥用/套话/程度副词堆砌）",'
        '"suggest":"建议怎么改（如：删去/改为动作呈现/换成轻量表达）"}],'
        '"summary":"整体文风评价（100字内：本章AI味的总体程度与最突出的问题）"}'
    )
    user = "\n\n".join(parts)
    return sys, user


def deai_chapter(project, chapter, mode="clean", rules="", selected_text="", directive="",
                 audit_issues=None, style_ref="", revise_note="", nearby_text=""):
    """去AI味提示词：mode = clean（按规则清洗）/ replace（句式词形替换）/ rewrite（整章或局部重写）。

    三种模式都要求剧情/事件/对话/人物行为/结局不变，输出润色后的整章完整正文。
    mode=rewrite 且给了 selected_text 时，只重写该段，其余内容必须逐字保留。
    audit_issues：可选，整体审查发现的问题清单（[{"quote","problem","suggest"},...]），
    处理时优先覆盖这些位置——避免只换句子、漏掉或误改整体。
    style_ref：v1.02 参考文风样本（可选）——**可贴多段不同情景的笔调**（打斗/文斗/日常/
    情绪酝酿等，v1.07 起不再限制"几百字"），去AI味时按原文所处情景取对应笔调模仿，不照抄内容。
    revise_note：v1.04 自动去AI味上一轮验收未达标的反馈（可选）——本轮重写必须修正的点
    （剧情不一致处/字数浮动方向/文风问题），注入整章重写任务；留空=不注入。
    nearby_text：v1.07 前后章节参考（main_ai 组装传入）——核对剧情衔接用，
    改写时不得改变与前后文已写内容相关的状态（人物/地点/时间线/事件连续性）。
    """
    sys = writer_system(project)
    rule_text = (rules or "").strip() or DEAI_DEFAULT_RULES
    # v2.60：八股核心治理始终随去AI味规则生效（与校对同一标准，用户自定义规则不绕开）
    rule_text = (rule_text + "\n\n【AI八股文分级治理（核心治理，始终生效；与用户规则冲突时以本段为准）】\n"
                 + PROOFREAD_CORE_GOVERNANCE)
    if mode == "replace":
        head = ("现在对本章做「句式/词形替换」。只对个别明显的 AI 味用词/句式做等义替换"
                "（优先执行规则中【句式/词形替换类】条目，【清除/改写类】仅在必要时做最小处理），"
                "保持语序结构、内容与篇幅基本不变，改动越少越好，不新增描写、不改剧情。")
    elif mode == "rewrite":
        head = ("现在对本章做「重写润色」。保持全部剧情、事件、对话内容、人物行为、出场与结局逐字不变，"
                "只重写文字表达本身，让行文更自然、更有纸书味。")
    else:
        head = ("现在对本章做一轮「去AI味清洗」。**先逐条比对规则，在原文中只找出确切命中规则的句子/片段**\n"
                "（如“不是……而是……”转折句、“他不知道……”上帝视角解释句、程度副词堆砌处、AI 高频套话模板、"
                "段末升华说教、描述写成解释等），**只重写/删改/替换这些命中处**；\n"
                "**其余一切内容——包括未命中的每一句话、每一个标点——必须逐字保留，一个字都不许改动**；\n"
                "不新增描写、不补戏、不改剧情；篇幅与命中处的增减一致。")
    lines = [
        "【任务】%s" % head,
        "【去AI味规则（必须逐条遵守）】",
        rule_text,
    ]
    if (revise_note or "").strip():
        lines.append("【上一轮验收反馈（本轮必须修正；与规则冲突以本段为准）】\n%s"
                     % revise_note.strip())
    if (style_ref or "").strip():
        lines.append("【参考文风样本（可能含多段不同情景的笔调：打斗/文斗/日常/情绪酝酿等，"
                     "每段对应一类情景；去AI味时按原文所处情景取对应笔调模仿其句式/节奏/描写手法与用词习惯；"
                     "只学味道，不照抄内容）】")
        lines.append(style_ref.strip())
    if (nearby_text or "").strip():
        lines.append(nearby_text.strip())
    if audit_issues:
        lines.append("【整体审查已发现的问题（处理时优先覆盖这些位置；其余内容仍按规则/要求处理）】")
        for i, it in enumerate(audit_issues[:40], 1):
            if not isinstance(it, dict):
                continue
            q = str(it.get("quote") or "").strip()
            p = str(it.get("problem") or "").strip()
            s = str(it.get("suggest") or "").strip()
            if q:
                lines.append("%d. 原文「%s」（%s%s）"
                             % (i, q[:80], p or "AI味问题",
                                ("；建议：%s" % s[:60]) if s else ""))
        lines.append("（若发现的问题与你的判断一致就重点处理；不一致处以你的判断为准，"
                     "未命中任何问题的内容仍须逐字保留。）")
    if mode == "rewrite" and selected_text and selected_text.strip():
        lines.append("【本次只重写下面这一部分（其余内容必须逐字保留原样，一个字都不要改）】")
        lines.append(selected_text.strip())
        if directive and directive.strip():
            lines.append("【修改意图】%s" % directive.strip())
    lines.append("【本章原文（完整）】")
    lines.append(chapter.content or "")
    lines.append("【输出】只输出润色后的本章完整正文，不要任何解释、前言、标题或标记。")
    return sys, "\n".join(lines)


def deai_verify(project, chapter, original, polished, rules="", style_ref="", nearby_text=""):
    """去AI味·自动验收（v1.04 一键自动去AI味）：对比原文与润色稿，评三件事——

    ① 文风契合度 style_score（0-100）：有参考样本时=润色稿与样本语感/句式/节奏的契合程度
       （并按【去AI味规则】检查 AI 味是否清除干净，残留套话/上帝视角/说教/重词堆砌会扣分）；
       无参考样本时=去AI味完成度（润色稿是否自然、AI 味残留多少，越高越自然）；
    ② 剧情一致性 plot_same（true/false）：事件、对话内容与含义、人物行为、事实信息、出场与结局
       是否与原文完全一致——去AI味只许改文字表达，任何剧情/信息变动都算不一致；
    ③ style_issues：未达标的文风问题（≤60字，可空）。
    nearby_text：v1.07 前后章节参考（main_ai 组装传入）——验收另核：润色稿与前后文衔接
    （人物状态/地点/时间线/已发生事件）不得冲突偏移，冲突则 plot_same 判 false。
    仅输出 JSON 供工作流判定是否达标自动合并。判定从严（v1.05）：你的结论直接决定稿件能否自动写回。
    """
    sys = ("你是一位**标准极严**的小说文字验收员，验收结论直接决定稿件能否自动写回章节。"
           "**宁严勿松**：拿不准就给低分、判不一致，绝不因为整体观感尚可就放行；"
           "任何一处可感知的 AI 味残留、任何一点剧情层面的变动都如实扣分/判定。"
           "你只验收打分，绝不修改任何文本。")
    parts = [
        "【任务】对比【原文】与【润色稿】，严格验收三项：",
        "1. style_score（0-100，**按锚点从严打分，拉开差距，不要通篇七八十分**）：" + (
            "润色稿的语感/句式/节奏/描写手法与【参考文风样本】的契合程度，高于一切观感；"
            "并按【去AI味规则】逐条核对残留。**扣分锚点**：90-100=优秀（几乎无 AI 味、"
            "明显向样本语感靠拢）；80-89=良好（个别残留，可接受）；70-79=一般（残留可感知，"
            "如套话/解释腔/副词堆砌仍有）；**<70=不合格（AI 味明显）**；"
            if (style_ref or "").strip() else
            "去AI味完成度（润色稿读起来是否自然、AI 味残留多少）。**扣分锚点**："
            "90-100=优秀（几乎无 AI 味）；80-89=良好（个别残留，可接受）；70-79=一般"
            "（套话/上帝视角/说教/副词堆砌仍有残留）；**<70=不合格（AI 味明显）**；"),
        "2. plot_same（true/false，**从严核对**）：润色稿与原文在**事件推进、对话内容与含义、"
        "人物行为与反应、事实信息（人名/地名/数字/关系/时间线）、出场与结局**上必须完全一致。"
        "逐项核对：①事件有没有增减/调序/合并；②对话措辞变没变含义（含语气/态度/潜台词）；"
        "③人物动作/反应/决定是否一致；④有没有新增原文没有的描写信息或删掉原文信息；"
        "⑤视角/人称/叙述顺序重排是否影响信息。**只要任何一项可能改变读者对剧情的理解，"
        "即判 false**；仅个别词语同义替换、句型重写而不变含义不算不一致。false 时 plot_issue 必填具体位置；",
        "3. style_issues：未达标的文风问题（≤60 字；无问题写「无」）。",
    ]
    if (style_ref or "").strip():
        parts.append("【参考文风样本（可能含多段不同情景的笔调，按原文所处情景取对应笔调对照评分）】\n%s"
                     % style_ref.strip()[:6000])
    if (nearby_text or "").strip():
        parts.append(nearby_text.strip())
    parts.append("【去AI味规则（验收按它逐条检查残留）】\n%s"
                 % ((rules or "").strip() or DEAI_DEFAULT_RULES)[:2000])
    parts.append("【原文（完整）】\n%s" % (original or "")[:6000])
    parts.append("【润色稿（完整）】\n%s" % (polished or "")[:6000])
    parts.append(
        "【你的输出】仅输出 JSON（**严格按上面的扣分锚点与核对清单打分判定**）：\n"
        '{"style_score":0-100,"style_issues":"文风问题(无问题写无)",'
        '"plot_same":true或false,"plot_issue":"剧情不一致之处(可空，plot_same=false时必填)"}'
    )
    return sys, "\n\n".join(parts)


# ======================================================================
# 写后校对（正文AI写完 → 主AI审查 之间：只改文本，不改剧情）
# ======================================================================
DEFAULT_PROOFREAD_RULES = """【一、描写逻辑错误（必须修正）】
1. 物品/道具位置前后矛盾：前文把某物放在某处（如放在桌上、挂在墙边），后文不能莫名跑到人物身上或别处；
2. 人物位置/姿态前后矛盾：前文把人物安置在房间某处（坐着/站着/躺着/抱着某人），后文不能瞬移到别处、或突然保持抱着的姿势；
3. 时间线/顺序矛盾：天色、昼夜、季节、先后顺序前后一致，不许出现天亮了又天黑、先说出门又写还在屋内等错乱；
4. 数字/数量矛盾：人数、物品数量、距离、时间长度前后一致。

【二、语句、字词、修辞（酌情修正）】
1. 程度很重、语气很重的词要少用：「砸」「砍」「撕裂」「狠狠」「猛地」「轰然」这类词不要出现在日常表达里，
   只在冲突激烈、情绪到达顶点的场景按程度使用；程度要匹配场景，不滥用；
2. 慎用被用滥的修辞与套话：如「像被撕碎」「指尖泛白」「眼底一沉」「空气仿佛凝固」等，避免堆砌；
   比喻、夸张要贴合场景、克制使用，日常描写里不用；
3. 语句通顺、用词准确、去除重复赘述；口语与书面语协调，标点与分段符合规范。

【三、绝对红线（违反即不合格）】
1. 只修改描写、用词、语句与修辞，绝不改变剧情走向、对话内容与含义、人物的决定和行为结果；
2. 不增删情节、不新增或删除角色动作、不改变任何事实信息、不改动结局。

【四、AI八股文分级治理（防模板化；只治读感，不注水、不改剧情）】
1. 禁用高频套词（出现即改，优先按替换方向处理）：
   「深吸一口气」→删或改动作（如"他呼出一口气"）；「眼中闪过一丝…」→删或用具体神态（"他垂下眼"）；
   「嘴角勾起一抹…」→删或用具体表情；「不禁」→删或用具体反应；「缓缓开口」→直接用动作引出说话；
   「仿佛…」→慎用，能删则删；
2. 句式套路（连续出现即改）：连续三句以上排比/对仗；「不是……而是……」滥用；「……，带着……」
   式状语堆叠；预告式收尾（"她不知道的是……"）；解释腔/上帝感（"之所以……是因为……"）；
3. 情绪空转：每个情绪词都配微动作（"他眼眶一红，攥紧了拳头"连发）、空转总结句（"一丝悲伤涌上心头"）——
   情绪要直写且有后果，删空转；
4. 节奏均匀：段落通篇等长（段段 4-6 句）——按节拍调整：爽点压短、情绪链放长；
5. 对话腔调：所有人说话一个语气——按角色卡区分说话方式，多用动作引出；
6. 结尾升华：每章以总结/感慨/升华收尾——改回动作或对话收尾；
7. 分级判定与处理：禁用词 ≤5 处/千字且无连续 3+ 套路=轻（只处理上述 1、2）；
   6-15 处/千字或连续 3+ 套路=中（再处理 3、4、6 类）；>15 处/千字或多类并发=重
   （全部类别处理 + 重点段落重写，notes 中标「[需复核]」）；
8. 三条保护规则：①改最少——能改一个词就不改一句，能删一句就不重写一段，
   人名/地名/数字/专有名词优先保留；②删除有上限——轻 ≤15%、中 ≤25%、重 ≤35%，
   不得整段删除，删除前确认该处无伏笔/钩子/角色特征/情节推进，会丢就降级改写不删；
   ③只改怎么说，不改说什么——不新增原文没有的情节、设定、关系或时间线。"""

# v2.58：核心八股治理段——用户自定义校对规则时也**始终生效**（与用户规则冲突以本段为准）
PROOFREAD_CORE_GOVERNANCE = """（与用户规则冲突时以本段为准）
1. 禁用高频套词（出现即改）：「深吸一口气」→删或改动作；「眼中闪过一丝…」→删或用具体神态；
   「嘴角勾起一抹…」→删或用具体表情；「不禁」→删或用具体反应；「缓缓开口」→用动作引出说话；
   「仿佛…」→慎用能删则删；
2. 句式套路（连续出现即改）：连续三句以上排比/对仗；「不是……而是……」滥用；「……，带着……」
   状语堆叠；预告式收尾（"她不知道的是……"）；解释腔/上帝感（"之所以……是因为……"）；
3. 情绪空转：每个情绪词配微动作连发、空转总结句（"一丝悲伤涌上心头"）——删空转、情绪直写有后果；
4. 节奏均匀：段落通篇等长——按节拍调整（爽点压短、情绪链放长）；
5. 对话腔调：所有人一个语气——按角色卡区分，多用动作引出；
6. 结尾升华：总结/感慨/升华收尾——改回动作或对话收尾；
7. 分级：禁用词≤5处/千字且无连续3+套路=轻（处理1、2）；6-15处/千字或连续3+套路=中（再处理3、4、6）；
   >15处/千字或多类并发=重（全部+重点段落重写，notes标「[需复核]」）；
8. 保护规则：改最少（能改一词不改一句、人名地名数字专名优先保留）；删除有上限
   （轻≤15%中≤25%重≤35%、不得整段删除、会丢伏笔钩子就降级改写不删）；只改怎么说不改说什么。"""


def proofread_chapter(project, store, chapter, rules="", nearby_text=""):
    """写后校对提示词：正文AI完稿后、主AI审查前，由校对AI细读整章。

    只修改描写/用词/语句/修辞（按用户可编辑的 rules），不改剧情。输出修正后完整正文 + 修改说明。
    nearby_text：v1.07 前后章节参考（main_ai 组装传入）——校对时核对本章与前后文的剧情衔接
    （人物状态/地点/时间线/事件连续性），发现冲突在 notes 中说明并保持不改动已定剧情。
    """
    sys = (
        "你是一位极度细致的小说文字校对员，为长篇小说逐字把关。你的职责是通读整章正文，"
        "找出描写上的硬伤与行文上的毛病并直接改好：物品/人物位置姿态前后矛盾、时间数量错乱、"
        "程度过重的字词滥用、被用滥的修辞堆砌、语句不通顺，以及**AI八股文**（模板化表达："
        "高频套词、句式套路、情绪空转、节奏均匀、对话腔调一致、结尾升华、解释腔）。"
        "你**只做文本层面的修正**，绝不动剧情、对话含义、人物决定与行为结果；"
        "并对照【前后章节参考】（若有）核对本章与前后文的衔接是否一致——衔接冲突只在校对"
        "说明中提示，同样不改动已定剧情。"
        "修改要克制：没有问题的句子一个字都不改，改动的都是真正有问题的部分；"
        "按规则第4节对 AI 八股分级（轻/中/重）处理并统计命中处数 ai_hits。"
    )
    card_lines = ["【本章出场角色设定】"]
    got = False
    for cid in chapter.characters:
        card, _ = store.load_character(cid)
        if card:
            card_lines.append(fmt_card(card))
            got = True
    if not got:
        card_lines.append("（无角色卡记录）")
    user_parts = [
        fmt_story(project),
        "【本章标题】%s" % (chapter.title or "第%d章" % chapter.index),
    ]
    user_rules = (rules or "").strip()
    rules_block = user_rules or DEFAULT_PROOFREAD_RULES
    if user_rules:
        # v2.58：自定义规则时核心八股治理始终追加生效（默认规则已含【四】段）
        rules_block = (rules_block + "\n\n【AI八股文分级治理（核心治理，始终生效；"
                       "与用户规则冲突时以本段为准）】\n" + PROOFREAD_CORE_GOVERNANCE)
    user_parts.append("【校对规则（用户可编辑；必须逐条遵守）】\n%s" % rules_block)
    style_ref = (project.story_style_ref or "").strip()
    if style_ref:
        user_parts.append(
            "【参考文风样本（用户指定的文风标杆，可含多段不同情景的笔调（打斗/文斗/日常/情绪酝酿等）；"
            "校对时以其语感/句式/节奏为对照，按原文所处情景取对应笔调，"
            "把偏离文风的句子改回这个味道）】\n%s" % style_ref[:6000])
    if (nearby_text or "").strip():
        user_parts.append(nearby_text.strip())
    style_note = (project.story_style_note or "").strip()
    if style_note:
        user_parts.append(
            "【风格要点（归纳自文风样本与前文，校对时检查正文是否逐条体现，偏离的改回）】\n%s"
            % style_note[:400])
    user_parts.append("【本章正文（完整）】\n%s" % (chapter.content or ""))
    user_parts.append("\n".join(card_lines))
    user_parts.append(
        "【你的输出】逐条对照校对规则细读全文后，输出修正后的**完整正文**与修改说明，仅输出 JSON：\n"
        '{"content":"修正后的本章完整正文（逐字包含全章，只有真正需要修改的地方被改；'
        '没问题的部分一字不动）","notes":["修改说明1（哪一处、改了什么、为什么，如：第三段“狠狠砸在桌上”'
        '改为“放在桌上”——日常场景程度过重）",...]，'
        '"ai_grade":"轻|中|重（按规则第4节分级；无 AI 八股问题可省略）",'
        '"ai_hits":12（AI 八股命中处数，无则省略）}'
    )
    user = "\n\n".join(user_parts)
    return sys, user


def extract_style_points(project, store):
    """从文风样本 + 最近几章正文归纳可执行的风格要点（供写作/校对逐条模仿）。

    要点要具体可执行（句式节奏/用词习惯/对话方式/描写手法/段落组织），忌空泛套话。
    """
    sys = ("你是资深小说编辑，擅长把文风样本与正文凝练成**可执行**的风格要点"
           "（短句长句节奏、用词习惯、对话方式、描写手法、段落组织等），供写作时逐条模仿。"
           "只输出风格要点，不做其他。")
    parts = [
        "通读下面的文风样本与最近几章正文，归纳 3-6 条可执行风格要点，每条 ≤20 字。",
        "要求：具体可执行，忌空泛套话（如「文笔优美」「行文流畅」「语言生动」都不算要点）；"
        "宁可一条只讲一个具体的习惯，也不要一条笼统的概述。",
    ]
    sample = (project.story_style_ref or "").strip()
    if sample:
        parts.append("【参考文风样本】\n%s" % sample[:1200])
    recent = []
    for i in sorted(store.list_chapter_indices())[-3:]:
        ch = store.load_chapter(i)
        if ch and (ch.content or "").strip():
            recent.append("第%d章（节选）：%s" % (i, (ch.content or "").strip()[:400]))
    parts.append("【最近章节正文（节选，确认当前实际文风）】\n%s" %
                 ("\n".join(recent) if recent else "（尚无已写章节，仅依据文风样本）"))
    parts.append('仅输出 JSON：{"points":["要点1（≤20字）","要点2","要点3"...]}（3-6 条）')
    return sys, "\n\n".join(parts)


def classify_characters(project, store):
    """角色自动分类提示词：AI 通读全部角色卡，按剧情定位分成几类（主要角色/配角/NPC/反派/其他…），
    输出 {角色名: 分类名} 映射。分类名要简短（2-6 字），同一类归一类名。"""
    lines = ["【故事设定】%s" % (project.story_brief or "（未设定）")]
    lines.append("【全部角色卡】")
    for cid, name, _ in store.list_characters():
        card, _ = store.load_character(cid)
        if not card:
            continue
        desc = (card.description or card.personality or "").strip()
        lines.append("- %s（%s）：%s" % (card.name, card.role or "身份未知", (desc[:80] or "无描述")))
    sys = (
        "你是一位小说编辑，负责给一部连载的全部角色做档案分类。"
        "请根据每个角色的剧情定位与戏份重要性归类。"
    )
    user = "\n".join(lines) + (
        "\n\n【分类要求】\n"
        "1. 一般分 2-6 类即可，常用：主要角色（主角与核心配角）、配角（有戏份的次要角色）、"
        "NPC（路人/服务型角色）、反派（敌对势力，可并入主要或单列）、其他（未定/背景）。"
        "可按这个故事的具体情况调整或细分（如把反派单列、把宗门/家族成员归一组），"
        "但分类名要简短（2-6 字，如“主要角色”“反派”“酒馆日常”），不要给每个角色单独一类；\n"
        "2. 戏份重、推动主线、有完整人物弧光的归“主要角色”；有固定戏份但不主导主线的归“配角”；"
        "只出场一两次、承担功能（掌柜/护卫/路人）的归“NPC”；\n"
        "3. 已阵亡/已归档的角色也要归入合适类别（如“已离场”），不要漏掉。\n"
        "仅输出 JSON：{\"roles\":{\"角色名\":\"分类名\",...}}"
    )
    return sys, user


# ======================================================================
# AI 段落工具（v0.53 写作工作台桌面端/安卓端共用：选中文本就地润色）
# ======================================================================
def polish_paragraph(project, text, mode="polish", style_ref="", directive="",
                     ctx_style=True, ctx_notes=True, ctx_rp=True, store=None):
    """AI 段落工具提示词：对选中的一段文本做润色/扩写/缩写/去AI味，不改剧情与人物设定。

    mode: polish（润色文笔）/ expand（扩写补足）/ shorten（精简浓缩）/ deai（去AI味）。
    style_ref：v1.02 参考文风样本（可选，全局「去AI味」配置）——处理时模仿其语感句式，不照抄内容。
    directive：v1.67 用户附加要求（可选）——如"缩写成一半""保留所有对白""去AI味但保留口语"，
              优先于模式默认规则执行。
    ctx_style/ctx_notes/ctx_rp（v1.68 可配置上下文开关，省 token 可关）：
      ctx_style=正文AI提示词与文风要求（story_writer_prompt + 参考文风样本 + 风格要点）；
      ctx_notes=主AI笔记（管理笔记/重要角色档案/灵感/知识库）；
      ctx_rp=涉及人物读取推理（store 传入时读角色卡，按人设推理其言行并落实）。
    输出只给处理后的段落文本。
    """
    sys = writer_system(project)
    if mode == "expand":
        head = ("对下面这段文字做**扩写**：在保持情节推进、对话含义与人物行为完全不变的前提下，"
                "补充环境氛围、动作细节、感官描写、心理层次与节奏铺陈，让段落更丰满更有画面感，"
                "篇幅约为原文的 1.5~2 倍。不得新增事件、不改变原意、不堆砌辞藻。")
    elif mode == "shorten":
        head = ("对下面这段文字做**精简**：删去重复赘述、冗余修饰与拖沓铺陈，保留全部情节信息、"
                "对话核心与人物的关键行为，行文紧凑有力，篇幅压缩到原文的一半左右，"
                "不得丢失剧情要点。")
    elif mode == "deai":
        head = ("对下面这段文字做**去AI味润色**：清除翻译腔、模板化表达、空泛描写、解释腔与"
                "AI 高频套话（“仿佛…”“眼中闪过一丝…”“不禁…”“缓缓…”等），"
                "换成具体、自然、有纸书质感的中文表达，句式多变，符合故事语感。"
                "不改剧情、不增删事件、不改对话含义。")
    else:
        head = ("对下面这段文字做**文笔润色**：修正语病与不通顺处，用词更准确生动，"
                "节奏与长短句搭配自然，贴合小说叙述语感，保持原有情节、对话含义、人物行为与篇幅基本不变。")
    style_note = (project.story_style_note or "").strip()
    lines = ["【任务】%s" % head, "【待处理段落】", (text or "").strip()]
    if (directive or "").strip():
        lines.append("【用户附加要求（优先级最高，必须在结果中落实）】%s"
                     % directive.strip())
    if (style_ref or "").strip() and ctx_style:
        lines.append("【参考文风样本（处理时模仿它的语感/句式/节奏/描写手法；只学味道，不照抄内容）】%s"
                     % style_ref.strip())
    # v1.68 可配置上下文：正文AI文风要求 + 主AI笔记 + 涉及人物读取推理（省 token 可关）
    lines.extend(writing_ctx_blocks(project, store, ctx_style=ctx_style,
                                    ctx_notes=ctx_notes, ctx_rp=ctx_rp))
    lines.append("【输出】只输出处理后的段落文本本身，不要引言、解释、标题或任何标记。")
    return sys, "\n".join(lines)


def _story_setting_blocks(project, max_brief=1200, max_world=800, max_rules=600):
    """v1.72 码字任务读取的故事设定块（与主AI fmt_story 同源：剧情发展/世界观/特殊规则）。

    码字任务（续写/段落工具）需要世界观、剧情规划等主AI能看到的内容，不应只注入主AI笔记——
    否则续写不知道世界设定、主线规划而"没灵魂"。这里复用 fmt_story 的三栏语义，
    但按上下文预算做长度截断（后续再拼故事原文时用全文）。
    返回 str 列表（有内容的块），无内容为空列表。
    """
    blocks = []
    brief = (project.story_brief or "").strip()
    if not brief:
        # 旧版兼容：opening + 结构化卷规划拼接（与 fmt_story 一致）
        parts = []
        if (project.opening or "").strip():
            parts.append("开局设定：%s" % project.opening.strip())
        for v in project.volumes:
            parts.append("第%d卷（目标%d章）：%s" % (v.index, v.total_chapters, v.title or "无题"))
            for i, ev in enumerate(v.main_events, 1):
                parts.append("  %d. %s" % (i, ev))
            if v.ending:
                parts.append("  本卷结尾目标：%s" % v.ending)
            if v.next_hook:
                parts.append("  承接下一卷：%s" % v.next_hook)
            if v.notes:
                parts.append("  补充约束：%s" % v.notes)
        brief = "\n".join(parts)
    if brief:
        blocks.append("【剧情发展（主线/卷规划，任务须贴合，不得违背）】%s" % brief[:max_brief])
    world = (project.story_world or "").strip()
    if world:
        blocks.append("【世界观（世界的背景/势力格局/地理/力量体系，任务必须服从）】%s"
                      % world[:max_world])
    rules = (project.story_rules or "").strip()
    if rules:
        blocks.append("【特殊规则/其他设定（用户的硬性要求，任务不得违反）】%s"
                      % rules[:max_rules])
    return blocks


def writing_ctx_blocks(project, store, ctx_style=True, ctx_notes=True, ctx_rp=True):
    """v1.68 码字 AI 任务的可配置上下文章节（段落工具与续写共用，省 token 可关）。

    ctx_style：README 文风要求（story_writer_prompt 用户对正文AI的设定 + 风格要点 story_style_note）；
    ctx_notes：主AI笔记（管理笔记 story_summary / 重要角色档案 story_characters / 灵感 story_ideas / 知识库 story_knowledge）
               + v1.72 故事设定（剧情发展/世界观/特殊规则 fmt_story 三栏，主AI同源依据）；
    ctx_rp：涉及人物读取推理（store 传入时读角色卡，按人设推理其言行并落实）。
    返回 str 列表（要追加进任务提示词的块），无内容时为空列表。
    """
    lines = []
    if ctx_style:
        style_note = (project.story_style_note or "").strip()
        if style_note:
            lines.append("【本故事风格要点（处理时贴合这些要点）】%s" % style_note)
        wpro = (project.story_writer_prompt or "").strip()
        if wpro:
            lines.append("【正文AI提示词（用户对正文AI的角色设定/风格要求，最高优先，必须遵守）】%s"
                         % wpro)
    if ctx_notes:
        # v1.72 故事设定（剧情发展/世界观/特殊规则）——主AI 通过 fmt_story 注入的核心依据，
        # 码字任务此前只注入主AI笔记、漏掉世界观与剧情规划（用户质疑"看不到世界观/剧情规划"）
        lines.extend(_story_setting_blocks(project))
        if (project.story_summary or "").strip():
            lines.append("【主AI管理笔记（剧情进度/主线安排，处理时贴合）】%s"
                         % project.story_summary)
        kcs = getattr(project, "story_characters", None) or []
        if kcs:
            klines = ["【主AI笔记·重要角色档案（涉及人物贴合其人设）】"]
            for kc in kcs[:12]:
                nm = str(kc.get("name", "") or "").strip()
                info = str(kc.get("info", "") or "").strip()
                if nm:
                    klines.append("- %s：%s" % (nm, info or "（无备注）"))
            lines.append("\n".join(klines))
        ideas = getattr(project, "story_ideas", None) or []
        if ideas:
            lines.append("【主AI笔记·灵感/可展开方向（处理时可选贴合）】%s"
                         % "；".join(str(i) for i in ideas[:8]))
        if (project.story_knowledge or "").strip():
            lines.append("【主AI知识库（重要设定/伏笔备忘，处理时不得与冲突）】%s"
                         % project.story_knowledge[:800])
    if ctx_rp and store is not None:
        rp_lines = _rp_char_lines(project, store)
        if rp_lines:
            lines.append("【涉及人物读取推理（按各角色既定人设推理其在本段中的行为/语言/情绪"
                         "并落实，不得违背人设）】\n%s" % "\n".join(rp_lines))
    return lines


def _rp_char_lines(project, store, limit=8):
    """v1.68 涉及人物读取推理：取近期出场 + 主AI笔记点名的重要角色卡，精简成行。

    返回如 ["■ 林晚（主角，在世）：意图…，行动倾向…", ...]；最多 limit 行。
    供段落工具/续写共用——按"最近出场（正文几章内）+ 管理笔记点名"加权排序，
    避免把几百张卡全塞进上下文；每张卡截取人设概况（性格/身份/说话风格/目标）。
    """
    items = store.list_characters()
    if not items:
        return []
    recent_ids = set()
    try:
        for i in store.list_chapter_indices()[-3:]:
            ch = store.load_chapter(i)
            if ch and ch.status == "approved":
                recent_ids.update(ch.characters or [])
    except Exception:
        pass
    note_names = set()
    for kc in getattr(project, "story_characters", None) or []:
        if isinstance(kc, dict) and kc.get("name"):
            note_names.add(str(kc["name"]))
    scored = []
    for cid, name, status in items:
        card, _lib = store.load_character(cid)
        if not card or not (card.name or "").strip():
            continue
        score = 0
        if cid in recent_ids or (card.name or "") in recent_ids:
            score += 2
        if (card.name or "") in note_names:
            score += 1
        scored.append((score, card))
    scored.sort(key=lambda x: -x[0])
    lines = []
    for _score, card in scored[:limit]:
        parts = ["■ %s" % (card.name or "")]
        if (card.role or "").strip():
            parts.append("%s" % card.role.strip())
        st = {"active": "在世", "dead": "已阵亡", "traveling": "外出游历",
              "archived": "已归档", "discarded": "已废弃"}.get(card.status, card.status)
        parts.append("状态：%s" % st)
        desc = (card.description or "").strip()
        if not desc and (card.personality or "").strip():
            desc = "性格：%s" % card.personality.strip()
        if desc:
            parts.append(desc[:180])
        goals = (card.goals or "").strip()
        if goals:
            parts.append("目标：%s" % goals[:80])
        lines.append("；".join(parts))
    return lines