# -*- coding: utf-8 -*-
"""主AI：出场决断 / 综合校验与伏笔管理 / 写作 / 审查 / 战后更新 / 卷末衔接 / 卷规划 / 角色生成。"""
import re

import config
import llm
import prompts
from models import CharacterCard, InfoLibrary


def _deai_nearby_n():
    """去AI味/写后校对·前后章节参考数（v1.07 配置 deai_nearby_chapters，0=不看）。

    注意：0 是合法值（关闭 nearby），不能用 `get(...) or 2` 兜底（0 会被 falsy 吞掉变 2）。
    """
    try:
        val = config.load_config().get("deai_nearby_chapters")
        if val is None:
            return 2
        return max(0, int(val))
    except Exception:
        return 2


def _nearby_context(store, chapter, n):
    """前后各 n 章参考文本（标题+梗概+正文节选），供去AI味/校对核对剧情衔接：

    人物状态/地点/时间线/已发生事件须与前后文一致——只作衔接参考，不模仿其文风。
    返回空串表示无需注入（n=0、无前后章或读取失败）。
    """
    if not n or store is None:
        return ""
    idx = getattr(chapter, "index", None)
    if idx is None:
        return ""
    try:
        indices = sorted(store.list_chapter_indices())
    except Exception:
        return ""
    before = [i for i in indices if i < idx][-n:]
    after = [i for i in indices if i > idx][:n]
    if not before and not after:
        return ""
    lines = ["【前后章节参考（核对剧情衔接用：本章人物状态/地点/时间线/已发生事件"
             "必须与前后文一致，不得偏移；仅作衔接核对，不模仿其文风）】"]
    for i in before:
        ch = store.load_chapter(i)
        if ch and (ch.content or "").strip():
            lines.append("·前文·第%d章《%s》%s：%s"
                         % (i, ch.title or "", (ch.brief or "").strip() or "",
                            (ch.content or "").strip().replace("\n", " ")[:300]))
    for i in after:
        ch = store.load_chapter(i)
        if ch and (ch.content or "").strip():
            lines.append("·后文·第%d章《%s》%s：%s"
                         % (i, ch.title or "", (ch.brief or "").strip() or "",
                            (ch.content or "").strip().replace("\n", " ")[:300]))
    return "\n".join(lines)


def _main_nearby_n():
    """主AI判断（出场决断/综合校验/审查）可读前几章正文数（v1.86 配置 main_recent_chapters，0=不看）。

    注意：0 是合法值（关闭），不能用 `get(...) or n` 兜底（0 会被 falsy 吞掉）。
    """
    try:
        val = config.load_config().get("main_recent_chapters")
        if val is None:
            return 1
        return max(0, int(val))
    except Exception:
        return 1


def _main_prev_context(store, chapter_no, n):
    """主AI判断用·前 N 章回顾（v1.86）：最近一章给完整正文（结尾钩子/正文AI写下的
    关键细节是本章必须承接的），更早的章给「梗概+结尾约800字」省 token。
    返回空串表示无需注入。"""
    try:
        n = int(n or 0)
    except (TypeError, ValueError):
        n = 0
    if n <= 0 or store is None:
        return ""
    try:
        done = sorted(store.list_chapter_indices())
    except Exception:
        return ""
    tail = [i for i in done if i < int(chapter_no)][-n:]
    if not tail:
        return ""
    lines = []
    for i, idx in enumerate(tail):
        ch = store.load_chapter(idx)
        if ch is None or ch.status != "approved":
            continue
        brief = (ch.brief or "").strip()
        body = (ch.content or "").strip()
        is_last = i == len(tail) - 1
        if is_last and len(body) <= 20000:
            excerpt = body                      # 最近一章：完整正文
        elif body:
            excerpt = "（前半略）……" + body[-800:]  # 更早章：结尾
        else:
            excerpt = ""
        lines.append("第%d章《%s》：%s%s"
                     % (ch.index, ch.title or "",
                        ("梗概：%s；" % brief) if brief else "",
                        ("结尾/当前状态：\n%s" % excerpt) if excerpt else "（无正文）"))
    if not lines:
        return ""
    return ("\n\n【前 %d 章回顾（主AI判断依据：上一章的结尾状态/悬念钩子/已写下的关键细节"
            "必须延续，人物与物的状态不得凭空丢失或冲突）】\n%s"
            % (len(lines), "\n\n".join(lines)))


def decide_characters(project, store, chapter_no, vol_no, vol_rank, user_directive="",
                      extra_context=""):
    sys, user = prompts.decide_characters(project, store, chapter_no, vol_no, vol_rank)
    if user_directive:
        user = user + "\n【你的临场指示】%s" % user_directive
    if extra_context:
        user = user + "\n【补充的角色档案（你点名召回的名册角色，读完后再决断）】\n%s" % extra_context
    # v1.86 主AI可读前 N 章：决断前先回顾上一章结尾/细节，避免丢钩子与状态
    _prev = _main_prev_context(store, chapter_no, _main_nearby_n())
    if _prev:
        user = user + _prev
    data = llm.chat_json(sys, user, tag="decide_characters", role="decide")
    if not isinstance(data, dict):
        data = {}
    cast = []
    for c in data.get("characters", []) or []:
        cid = (c or {}).get("id", "")
        if cid:
            cast.append({"id": cid, "role_in_scene": c.get("role_in_scene", ""),
                         "notes": c.get("notes", "")})
    data["characters"] = cast
    return data


def consolidate(project, store, chapter_no, scene_focus, inferences,
                new_char_pool_hint="", extra_context="", search_enabled=False,
                kb_prompt=""):
    sys, user = prompts.consolidate(project, store, chapter_no, scene_focus,
                                    inferences, new_char_pool_hint,
                                    extra_context=extra_context,
                                    search_enabled=search_enabled,
                                    kb_prompt=kb_prompt)
    if extra_context:
        user = user + "\n【补充上下文（主AI回顾章节/联网搜索结果）】\n%s" % extra_context
    # v1.86 主AI可读前 N 章：校验主线前先看上一章结尾/细节，防止设定与状态脱节
    _prev = _main_prev_context(store, chapter_no, _main_nearby_n())
    if _prev:
        user = user + _prev
    data = llm.chat_json(sys, user, tag="consolidate", role="decide")
    return data if isinstance(data, dict) else {}


def compress_summary(project, store, recent=8):
    """主AI管理笔记 + 角色归档建议。

    返回 dict：{"note": 管理笔记正文, "archive": [{"id","reason"}, ...]}
    """
    sys, user = prompts.compress_summary(project, store, recent)
    data = llm.chat_json(sys, user, tag="compress_summary", role="decide")
    return data if isinstance(data, dict) else {}


def write_chapter(project, store, chapter_no, scene_focus, direction, inferences,
                  foreshadow_lines, target_chars, user_feedback="", recent_chapters=3,
                  max_tokens=None, draft="", beats=None, planning_note=None,
                  cliche_watch=None, scene_cards=None, min_chars=None, max_chars=None):
    sys, user = prompts.write_chapter(project, store, chapter_no, scene_focus,
                                      direction, inferences, foreshadow_lines,
                                      target_chars, recent_chapters=recent_chapters,
                                      draft=draft, beats=beats,
                                      planning_note=planning_note,
                                      cliche_watch=cliche_watch,
                                      scene_cards=scene_cards,
                                      min_chars=min_chars, max_chars=max_chars)
    if user_feedback:
        user = user + "\n【用户/审稿修改意见】%s（在遵循上述要求的前提下，重点按此调整。）" % user_feedback
    text = llm.chat_text(sys, user, tag="write_chapter", role="write",
                         max_tokens=max_tokens)
    if not (text or "").strip():
        # 空输出（网关偶发）：给占位标题与提示，交由上层审查/用户处理，不产生空章归档
        return "第%d章" % chapter_no, "（本章内容为空，请凭意见重新生成。）"
    parts = text.split("\n", 1)
    title = parts[0].strip().lstrip("#* ").strip()  # 去 markdown 标题符（## 第N章 → 第N章）
    content = parts[1].strip() if len(parts) > 1 else text.strip()
    if not title or len(title) < 3 or "章" not in title:
        title = "第%d章" % chapter_no
        content = text.strip()
    return title, content


def review_chapter(project, store, chapter, target_desc, beats=None):
    sys, user = prompts.review_chapter(project, store, chapter, target_desc,
                                       beats=beats)
    # v1.86 主AI可读前 N 章：审查时对照上一章结尾/细节，报前后衔接冲突
    _prev = _main_prev_context(store, chapter.index, _main_nearby_n())
    if _prev:
        user = user + _prev
    data = llm.chat_json(sys, user, tag="review_chapter", role="review")
    return data if isinstance(data, dict) else {}


def editor_review_chapter(project, store, chapter):
    """AI 编辑审稿：以资深编辑视角通读整章，给全面修改意见（不替代主AI过章审查）。"""
    sys, user = prompts.editor_review(project, store, chapter)
    data = llm.chat_json(sys, user, tag="editor_review", role="review")
    return data if isinstance(data, dict) else {}


def extract_style_points(project, store):
    """从文风样本 + 前几章正文归纳可执行风格要点（用户点「AI 提炼」时调用）。

    返回 3-6 条要点（每条 ≤30 字）；失败返回空列表。
    """
    sys, user = prompts.extract_style_points(project, store)
    data = llm.chat_json(sys, user, tag="extract_style", role="write")
    if not isinstance(data, dict):
        return []
    pts = data.get("points") or []
    out = [str(x).strip()[:30] for x in pts if str(x).strip()]
    return out[:6]


def update_world(project, store, chapter):
    open_fs = store.load_foreshadows()
    # 逾期伏笔在 ID 后附标注（如 abc123⚠逾期18章），让战后更新知道哪些该优先安排回收
    open_ids = []
    for f in open_fs:
        if f.status == "open":
            mark = prompts._overdue_mark(f, project.written_chapters())
            open_ids.append(f.id + ("　" + mark if mark else ""))
    # v1.101 本章主AI安排的伏笔指令文本（正文反扫核对用：正文AI/作者加戏新埋的钩子要登记回来）
    planned = []
    cons = (chapter.reasoning or {}).get("consolidation", {}) or {}
    for f in cons.get("foreshadows", []) or []:
        if isinstance(f, dict) and f.get("f_type") == "plant" \
                and str(f.get("text", "") or "").strip():
            planned.append(str(f["text"]).strip())
    sys, user = prompts.update_after_chapter(project, store, chapter, open_ids,
                                             planned_plants=planned)
    data = llm.chat_json(sys, user, tag="update_world", role="decide")
    return data if isinstance(data, dict) else {}


def volume_closing(project, store, vol):
    """卷末总结与承接下一卷。返回 {"summary":..., "next":...}（v1.96 结构化，便于后续处理）。"""
    sys, user = prompts.volume_closing(project, store, vol)
    try:
        data = llm.chat_json(sys, user, tag="volume_closing", role="decide")
        if isinstance(data, dict) and (data.get("summary") or data.get("next")):
            return {"summary": str(data.get("summary") or "").strip(),
                    "next": str(data.get("next") or "").strip()}
    except llm.StopRequested:
        raise
    except llm.LLMError:
        pass
    except Exception:
        pass
    # 兜底：模型没给 JSON 时退回原始文本，engine 按字符串处理
    return llm.chat_text(sys, user, tag="volume_closing", role="decide")


def plan_story_ai(opening, notes, constraint="", targets=("story", "world", "rules")):
    """AI 按用户想法起草故事设定（三块可勾选：story/world/rules）。

    返回 dict：{"story":..., "world":..., "rules":...}（仅含勾选部分；值为草稿文字）。
    """
    sys, user = prompts.plan_story_ai(opening, notes, constraint, targets)
    data = llm.chat_json(sys, user, tag="plan_story", role="decide")
    if not isinstance(data, dict):
        data = {}
    return data


def revise_story(project, store, targets, user_req, current, constraint=""):
    """v1.98 故事设定页「AI 辅助·按我的要求修改」：在现有三栏（current dict）基础上，
    按用户要求修改剧情/世界观/特殊规则，输出完整修订版 dict（仅含勾选栏）。

    直接受主AI全局提示词（story_main_prompt）+ 拆书风格参考影响（revise_story_ai 用
    main_system(project) 注入）；结果**不落盘**，由 UI 展示供用户截取替换。
    """
    sys, user = prompts.revise_story_ai(project, store, targets, user_req, current, constraint)
    data = llm.chat_json(sys, user, tag="revise_story", role="decide")
    if not isinstance(data, dict):
        data = {}
    return data


def generate_scene_card(type_name, detail=None):
    """v1.17 AI 一键写作某类型的情景规则卡内容（武打/文斗/见父母装傻充愣等）。

    v1.19 起走「用途分工·情景提示词制作」配置（role=scene_card；未单独指定时跟随通用）。
    v1.23 新增 detail 细节方向（可选，如「偏兵刃近身、狠辣致命」）——注入生成提示词让
    该卡按用户指定的方向设计，留空与原行为完全一致。
    返回纯文本规则（可编辑后入库）；失败抛 LLMError，由调用方提示。
    """
    sys, user = prompts.generate_scene_card_ai(type_name, detail=detail)
    text = llm.chat_text(sys, user, tag="gen_scene_card", role="scene_card",
                         max_tokens=1500)
    return (text or "").strip()


def extract_scene_card(type_name, sample_text):
    """v1.19 根据用户提供的文本，提取某类型情景的规则卡内容。

    与 generate_scene_card 同结构（核心定位+分节+自检清单，字数不限），但规则从参考文本
    的实际写法提炼（不照抄原文）；走「用途分工·情景提示词制作」配置（role=scene_card）。
    v1.20 提取提示词可自定义：config["extract_scene_card_prompt"] 有值用之，None 用内置初始。
    返回纯文本规则（可编辑后入库）；失败抛 LLMError，由调用方提示。
    """
    import config as _cfg120
    prompt = (_cfg120.load_config().get("extract_scene_card_prompt") or "").strip() or None
    sys, user = prompts.extract_scene_card_ai(type_name, sample_text, prompt=prompt)
    text = llm.chat_text(sys, user, tag="extract_scene_card", role="scene_card",
                         max_tokens=2500)
    return (text or "").strip()


def adapt_project_scene_cards(project, cards):
    """v1.42 主AI按本项目正文AI基础文风（story_writer_prompt）适配项目库情景卡。

    保持每张卡的情景内核/卡名/分类不变，只把写法表述调整到契合本项目正文AI基础文风；
    只改项目库、不动总库。返回 {"adapted": [{"name","content"}, ...]}；
    失败抛 LLMError，由调用方提示。
    """
    sys, user = prompts.adapt_project_scene_card_ai(project, cards)
    data = llm.chat_json(sys, user, tag="adapt_scene_cards", role="scene_card")
    return data if isinstance(data, dict) else {}


def plan_title(idea):
    """一键成书（v0.54）：AI 为这个故事起一个书名。

    返回书名（去掉引号/多余空白）；没起成返回空串，由调用方生成临时名并提示。
    v1.97 修复「AI 新书」谜案：LLM 失败不再在此处静默吞掉——直接上抛给调用方
    打印真实原因；另外模型常把书名连同解释一起输出（超过 12 字被判空），
    这里先尝试从《》或首个片段里提取书名，再不行才判空。
    """
    idea = (idea or "").strip()
    sys = (
        "你是一位小说书名设计师。根据用户给的小说想法，起一个**有吸引力、贴合题材、"
        "读起来上口**的书名：2-8 个字之间，避免生僻字与太长名词堆砌，不要带「之/传/录」等"
        "套路后缀硬凑三字（除非自然）。只输出书名本身，不要引号、不要解释。"
    )
    user = "【小说想法】%s" % (idea or "（未提供，请起一个通用但出彩的爽文书名）")
    # v0.76：不再限 40 token——推理模型思考会先吃预算，限 40 必然空正文 → 书名
    # 永远回退临时名；不限制让模型自己停（提示词已要求只输出书名）
    title = llm.chat_text(sys, user, tag="plan_title", role="decide")
    title = (title or "").strip().strip('"\'“”《》').strip()
    if not title:
        return ""
    # 模型常输出「书名：《xx》」或书名+一句解释 → 优先从《》里取第一个片段
    import re as _re
    _m = _re.search(r"[《]([^《》]{1,16})[》]", title)
    if _m:
        return _m.group(1).strip()
    # 去掉首句末尾标点与多余说明（按第一个中英标点截断）
    _cut = _re.split(r"[，。！？;；、:：\s]+", title, maxsplit=1)[0].strip()
    if _cut and len(_cut) <= 12:
        return _cut
    if _cut:
        return _cut[:12]
    return ""


def _fallback_title(idea):
    """v1.97 起名失败时的临时名：从想法里抽几个关键词（民国/黑道/重生…），
    不再产出「AI 新书」这种莫名其妙的占位名。"""
    import re as _re
    seg = _re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", idea or "")
    if len(seg) >= 2:
        return seg[:8]
    return "未命名小说"


def extract_chapter_hint(text):
    """从想法/要求文本里提取用户明确写出的章数要求（如「不低于120章」「约80章」）。

    返回 (n, label)：n 为数字（当全书下限用），label 为原话片段（进提示词让 AI 严格遵循）；
    没找到返回 (None, "")。只认阿拉伯数字 + 限定词，避免把「每章3000字」「第5章」
    这类无关数字误判成章数要求。
    """
    if not text:
        return None, ""
    t = re.sub(r"\s+", "", str(text))
    pats = [
        (r"(?:不低于|至少|最少|不少于|不能低于|不得少于)(\d{1,4})章", "min"),
        (r"(?:共|总|全书|计划|目标|打算|准备|想|要|约|大概|大约)(?:写|出|更)?(\d{1,4})章", "min"),
        (r"(\d{1,4})章(?:左右|上下|起步|以上|出头)", "min"),
    ]
    for pat, _kind in pats:
        m = re.search(pat, t)
        if m:
            return int(m.group(1)), m.group(0)
    return None, ""


def plan_chapters(idea, story="", world="", rules="", author_constraint="",
                  default=30, lo=1, hi=3000):
    """v1.73 一键成书「AI 自动判断章节数」：AI 按想法+设定判断全书合理总章数。

    返回 clamp 后的 int；AI 调用失败返回 default（不阻塞成书流程）。
    story/world/rules：plan_story_ai 已起草的三栏设定（草案，AI 据此判断篇幅）；
    author_constraint：用户想法/约束里已给数字时优先遵循（提示词层处理）。
    v1.80 加固：
    · 想法/约束里写了明确章数（如「不低于120章」）→ 提示词里作为硬性要求注入，
      并且该数字是全书章数的底线（AI 判断只可上浮、不可低于——用户明说过的数要兑现）；
    · AI 判断失败时回退到「想法里写的数字」，而不是面板默认值（此前失败就按默认小数值
      走，用户看到的全是没考虑他想法的结果）。
    """
    hint_n, hint_label = extract_chapter_hint(idea)
    if hint_n is None:
        hint_n, hint_label = extract_chapter_hint(author_constraint)

    def _clamp(n):
        return max(lo, min(hi, int(n)))

    try:
        import config as _cfg173
        _cfg173.load_config()  # 保持与其它环节一致的现读配置习惯
        req = hint_label or (author_constraint or "").strip()
        sys, user = prompts.plan_chapters_ai(
            idea, story=story, world=world, rules=rules,
            author_constraint=req)
        data = llm.chat_json(sys, user, tag="plan_chapters", role="decide")
        if isinstance(data, dict):
            try:
                n = int(data.get("chapters") or 0)
            except (TypeError, ValueError):
                n = 0
            if n > 0:
                n = _clamp(n)
                if hint_n is not None and n < hint_n:
                    n = _clamp(hint_n)  # 用户明说「不低于 N 章」→ 只可上浮
                return n
    except llm.StopRequested:
        raise  # v1.71 停止红线：用户停止必须优先传播，不能被 LLMError 兜底吞掉
    except llm.LLMError:
        pass
    except Exception:
        pass
    if hint_n is not None:
        return _clamp(hint_n)  # AI 判断失败：用户想法里写的数优先于默认值
    return int(default)


def generate_character_ai(description, project, store):
    sys, user = prompts.generate_character_ai(description, project, store)
    data = llm.chat_json(sys, user, tag="gen_character", role="decide")
    return data if isinstance(data, dict) else {}


def generate_batch_roles(description, project, store):
    """AI 按自然语言需求批量生成角色卡，返回 [角色dict, ...]（只立形象）。

    v1.99 修「B 缺失 + A 重复」：不再静默丢弃缺 name 的条目——模型给出缺姓名的角色
    视为不合格，抛 ValueError 让调用方显式提示重试；防重由落库入口
    save_generated_character（同名查重/复用）统一负责。
    """
    sys, user = prompts.generate_batch_roles(description, project, store)
    data = llm.chat_json(sys, user, tag="gen_batch_roles", role="decide")
    if isinstance(data, list):
        chars = data
    elif isinstance(data, dict):
        chars = data.get("characters") or []
    else:
        chars = []
    out = []
    dropped = 0
    for c in chars:
        if isinstance(c, dict) and (str(c.get("name") or "")).strip():
            out.append(c)
        else:
            dropped += 1  # 缺姓名/格式异常：不再静默吞，交给调用方提示
    if dropped:
        raise ValueError("批量拆解出 %d 条缺少姓名的角色（模型可能没给全），"
                         "已丢弃请重试，或把要生成的角色列得更明确。" % dropped)
    return out


def deai_audit(project, store, chapter, rules=""):
    """去AI味·整体审查：先通读整章找出所有 AI 味问题位置，再交给 deai_chapter 处理。

    返回问题清单 [{"quote","problem","suggest"},...]；解析失败时返回 []（降级为不审查直接处理）。
    前后章节参考（v1.07 配置 deai_nearby_chapters）：同注入，审查时报出与前后文衔接冲突处。
    """
    nearby = _nearby_context(store, chapter, _deai_nearby_n())
    sys, user = prompts.deai_audit(project, chapter, rules, nearby_text=nearby)
    try:
        data = llm.chat_json(sys, user, tag="deai_audit", role="deai")
    except llm.LLMError:
        return []
    issues = []
    if isinstance(data, dict):
        items = data.get("issues")
        if isinstance(items, list):
            for it in items:
                if isinstance(it, dict) and str(it.get("quote") or "").strip():
                    issues.append(it)
    return issues


def deai_chapter(project, store, chapter, mode="clean", rules="", selected_text="", directive="",
                 audit_issues=None, style_ref="", revise_note=""):
    """对已生成章节做去AI味润色（不改剧情）。

    mode: clean（按规则清洗）/ replace（句式词形替换）/ rewrite（整章或局部重写）。
    audit_issues：可选，整体审查发现的问题清单（main_ai.deai_audit 产出），注入处理提示词，
    让清洗/替换/重写优先覆盖审查命中的位置。
    style_ref：v1.02 参考文风样本（可选，全局「去AI味」配置）——v1.07 起支持多段不同情景笔调
    （打斗/文斗/日常/情绪酝酿等），去AI味时按原文所处情景取对应笔调模仿其语感句式，不抄内容。
    revise_note：v1.04 自动去AI味上一轮验收未达标的反馈（可选）——本轮重写必须修正的点，注入提示词。
    返回润色后的整章完整正文。模型取自「用途分工·去AI味」（未指定则用通用/当前）。
    """
    nearby = _nearby_context(store, chapter, _deai_nearby_n())
    sys, user = prompts.deai_chapter(project, chapter, mode, rules, selected_text, directive,
                                     audit_issues=audit_issues, style_ref=style_ref,
                                     revise_note=revise_note, nearby_text=nearby)
    # 去AI味输出约等于整章长度，给足 16000（仍受用户设置收敛），避免超大 max_tokens 烧限流配额
    return llm.chat_text(sys, user, tag="deai_%s" % mode, role="deai",
                         max_tokens=16000).strip()


def _deai_verify(project, store, chapter, original, polished, rules, style_ref):
    """去AI味·自动验收（chat_json）：返回 {"style_score":0-100|None,"style_issues":str,
    "plot_same":bool|None,"plot_issue":str}。LLM 验收失败时相关字段为 None，由判定方降级处理
    （不因验收调用失败卡死工作流；StopRequested 照常传播不吞）。
    前后章节参考（v1.07）：验收另核润色稿与前后文衔接一致（人物状态/地点/时间线不偏移）。"""
    nearby = _nearby_context(store, chapter, _deai_nearby_n())
    sys, user = prompts.deai_verify(project, chapter, original, polished, rules, style_ref,
                                    nearby_text=nearby)
    try:
        data = llm.chat_json(sys, user, tag="deai_verify", role="deai", think_role="deai")
    except llm.StopRequested:
        raise
    except llm.LLMError:
        return {"style_score": None, "style_issues": "", "plot_same": None, "plot_issue": ""}
    out = {"style_score": None, "style_issues": "", "plot_same": None, "plot_issue": ""}
    if isinstance(data, dict):
        try:
            out["style_score"] = max(0.0, min(100.0, float(data.get("style_score"))))
        except Exception:
            pass
        out["style_issues"] = str(data.get("style_issues") or "").strip()
        ps = data.get("plot_same")
        out["plot_same"] = bool(ps) if isinstance(ps, bool) else None
        out["plot_issue"] = str(data.get("plot_issue") or "").strip()
    return out


def _deai_metrics(original, polished, style_ref, verify, evaluator):
    """自动去AI味验收合成：文风得分（有参考样本=0.4×TFIDF(稿,样本)+0.6×LLM 契合度，
    与文风校对 v0.64 同一套混合权重；无参考样本=LLM 去AI味完成度）、字数差（字）、剧情一致性。

    返回 (final, tfidf, diff_chars, plot_ok, verify_ok)：
    final=合成文风得分；tfidf=字符 bigram TFIDF 相似度(有样本时有效)；
    diff_chars=字数差（|润色稿-原文| 字符数，v1.05 起按字判容差，与正文写作 ±500 标准一致）；
    plot_ok=剧情是否一致（验收未返回判定时视为通过，不误伤）；verify_ok=验收调用是否有效。"""
    ln_o = len(original or "")
    ln_p = len(polished or "")
    diff_chars = abs(ln_p - ln_o)
    style_score = verify.get("style_score")
    tfidf = 0.0
    ref = (style_ref or "").strip()
    if ref:
        tfidf = evaluator.tfidf_cosine((polished or "")[:1500], ref[:1500]) * 100.0
        final = 0.4 * tfidf + 0.6 * (style_score if style_score is not None else 50.0)
    else:
        final = style_score if style_score is not None else 50.0
    verify_ok = style_score is not None
    plot_ok = True if verify.get("plot_same") is None else bool(verify.get("plot_same"))
    return round(final, 1), round(tfidf, 1), diff_chars, plot_ok, verify_ok


def deai_auto_workflow(project, store, chapters, rules="", style_ref="",
                       threshold=80.0, max_rounds=3, length_tol=500,
                       stop_check=None, log=None):
    """v1.04 一键自动去AI味（v1.05 修订）：结合文风校对的「评分→优化→达标自动通过」验收循环。

    逐章执行：整体审查 → 改写（rewrite，带审查问题/参考样本/上轮反馈）→ 自动验收
    （文风契合度 + 剧情一致性 + 字数容差[字，默认±500 与正文写作一致]）；
    **每章从已跑轮次中选评分最高的一轮作为成果**：它三项全过（达标）→ 自动用该轮稿合并回原文
    （旧稿自动备份草稿箱可恢复）——**不是直接用最后一轮**；若最高分轮仍不达标 → 保留原文不合并，
    结束报告给"最高 X 分（第 N 轮）"；未达标则把验收反馈注入下一轮重写，直到达标或达到最大轮次。

    yield (kind, data)：
      ("chapter_start", {"chapter","title","total"})
      ("round_done", {"chapter","round","score","tfidf","diff(字)","plot_ok","length_ok",
                      "verify_ok","passed","style_issues","plot_issue"})
      ("chapter_done", {"chapter","rounds","score","best_round"})   # 达标并已用最高分达标轮自动合并
      ("chapter_fail", {"chapter","rounds","score","best_round","reason"})
    """
    from style_extract import SimilarityEvaluator
    evaluator = SimilarityEvaluator()
    for i, idx in enumerate(chapters, 1):
        ch = store.load_chapter(idx)
        if ch is None:
            yield ("chapter_fail", {"chapter": idx, "rounds": 0, "score": 0.0,
                                    "best_round": 0, "reason": "章节缺失"})
            continue
        original = (ch.content or "").strip()
        if not original:
            yield ("chapter_fail", {"chapter": idx, "rounds": 0, "score": 0.0,
                                    "best_round": 0, "reason": "章节正文为空"})
            continue
        yield ("chapter_start", {"chapter": idx, "title": ch.title or "",
                                 "total": len(chapters)})
        if stop_check and stop_check():
            raise llm.StopRequested("已停止")
        # ① 整体审查定位 AI 味问题位置（失败静默降级为不审查）
        issues = []
        try:
            issues = deai_audit(project, store, ch, rules) or []
        except llm.StopRequested:
            raise
        except Exception:
            issues = []
        best = {"score": 0.0, "rounds": 0}
        rounds_log = []      # 每轮 {"score","polished","passed"}，章节结束时取最高分轮
        revise_note = ""
        for r in range(1, max(1, int(max_rounds)) + 1):
            if stop_check and stop_check():
                raise llm.StopRequested("已停止")
            # ② 改写（第一轮无反馈；后续轮带上一轮验收反馈）
            try:
                polished = deai_chapter(project, store, ch, mode="rewrite", rules=rules,
                                        audit_issues=issues, style_ref=style_ref,
                                        revise_note=revise_note)
            except llm.StopRequested:
                raise
            except Exception as e:
                best = {"score": 0.0, "rounds": r, "reason": "改写失败：%s" % e}
                break
            if not (polished or "").strip():
                best = {"score": 0.0, "rounds": r, "reason": "模型未返回有效内容"}
                break
            # ③ 自动验收（文风契合度 + 剧情一致性 + 字数容差）
            verify = _deai_verify(project, store, ch, original, polished, rules, style_ref)
            final, tfidf, diff_chars, plot_ok, verify_ok = _deai_metrics(
                original, polished, style_ref, verify, evaluator)
            length_ok = diff_chars <= float(length_tol)
            passed = final >= float(threshold) and plot_ok and length_ok
            yield ("round_done", {"chapter": idx, "round": r, "score": final,
                                  "tfidf": tfidf, "diff": diff_chars, "plot_ok": plot_ok,
                                  "length_ok": length_ok, "verify_ok": verify_ok,
                                  "passed": passed,
                                  "style_issues": verify.get("style_issues", ""),
                                  "plot_issue": verify.get("plot_issue", "")})
            rounds_log.append({"score": final, "polished": polished, "passed": passed,
                               "round": r})
            best = {"score": final, "rounds": r, "passed": False}
            if passed:
                best = {"score": final, "rounds": r, "passed": True}
                break
            # ④ 未达标：组验收反馈注入下一轮重写
            parts = ["上一轮去AI味未达标（阈值 %s，得分 %s）。本轮必须修正以下问题："
                     % (threshold, final)]
            if not verify_ok:
                parts.append("- 自动验收调用失败/未返回有效评分，请严格按照【任务】要求做整章去AI味重写。")
            if not plot_ok:
                parts.append("- 剧情一致性不通过：%s（把改动的剧情/对话含义/人物行为/"
                             "事实信息/结局逐字改回原文，只保留文字润色）"
                             % (verify.get("plot_issue") or "有剧情变动"))
            if not length_ok:
                parts.append("- 字数差 %d 字超出容差 %d 字（当前原文 %d 字）：把篇幅改回接近原文"
                             % (diff_chars, length_tol, len(original)))
            if (style_ref or "").strip():
                parts.append("- 文风契合度不足（TFIDF %.0f）：往【参考文风样本】的语感/句式/节奏上再靠近"
                             % tfidf)
            si = (verify.get("style_issues") or "").strip()
            if si:
                parts.append("- 文风问题：%s" % si)
            revise_note = "\n".join(parts)
        if best.get("reason"):
            yield ("chapter_fail", {"chapter": idx, "rounds": best.get("rounds", 0),
                                    "score": best.get("score", 0.0),
                                    "best_round": best.get("rounds", 0),
                                    "reason": best["reason"]})
            continue
        # ⑤ 从已跑轮次中选评分最高者作为该章成果（达标轮里取最高分；不达标轮里也取最高分供报告）
        best_item = max(rounds_log, key=lambda x: x["score"]) if rounds_log else None
        if best_item is None:
            yield ("chapter_fail", {"chapter": idx, "rounds": best["rounds"], "score": 0.0,
                                    "best_round": 0, "reason": "无有效轮次结果"})
            continue
        best_passed = max((it for it in rounds_log if it["passed"]),
                          key=lambda x: x["score"], default=None)
        if best_passed is not None:
            # ⑥ 达标 → 用**评分最高的达标轮**自动合并回原文（不是最后一轮；写回前自动备份草稿箱）
            try:
                import engine as _engine_mod
                eng = _engine_mod.NovelEngine(store, log or (lambda _k, _m: None))
                ok = eng.apply_deai(project, idx, best_passed["polished"])
            except llm.StopRequested:
                raise
            except Exception:
                ok = False
            if ok:
                yield ("chapter_done", {"chapter": idx, "rounds": best["rounds"],
                                        "score": best_passed["score"],
                                        "best_round": best_passed["round"]})
            else:
                yield ("chapter_fail", {"chapter": idx, "rounds": best["rounds"],
                                        "score": best_passed["score"],
                                        "best_round": best_passed["round"],
                                        "reason": "自动合并回原文失败"})
        else:
            yield ("chapter_fail", {"chapter": idx, "rounds": best["rounds"],
                                    "score": best_item["score"],
                                    "best_round": best_item["round"],
                                    "reason": "轮次耗尽仍未达标"})


def retitle_chapters(project, store, start, end, with_content=True):
    """批量重新设计第 start~end 章标题（v1.01；v1.82 默认读**完整正文**）：
    勾选「让 AI 阅读章节正文后命名」= 每章附完整正文给 AI 依据全章内容取题
    （异常超长章给开头+结尾）；with_content=False = 只按梗概/原标题取题（省 token）。
    返回 (成功数, 失败数)。
    """
    sys, user = prompts.retitle_chapters(project, store, start, end,
                                         with_content=with_content)
    data = llm.chat_json(sys, user, tag="retitle_chapters", role="write",
                         think_role="write", timeout=180)
    titles = {}
    for t in (data.get("titles") or []):
        try:
            titles[int(t.get("chapter"))] = str(t.get("title") or "").strip()
        except Exception:
            continue
    ok = fail = 0
    for i in range(int(start), int(end) + 1):
        ch = store.load_chapter(i)
        if ch is None:
            continue
        nt = titles.get(i)
        if nt:
            ch.title = nt
            store.save_chapter(ch)
            ok += 1
        else:
            fail += 1
    return ok, fail


def proofread_chapter(project, store, chapter, rules="", max_tokens=None):
    """写后校对：正文AI完稿后、主AI审查前，由校对AI只改文本（描写/用词/语句/修辞），不改剧情。

    前后章节参考（v1.07 配置 deai_nearby_chapters）：校对时核对本章与前后文衔接
    （人物状态/地点/时间线/事件连续性），防剧情偏移。
    返回 {"content": 修正后完整正文, "notes": [修改说明...]}；解析失败或内容为空时返回 {}，
    由调用方兜底保留原文（校对环节失败不阻断生成）。
    """
    nearby = _nearby_context(store, chapter, _deai_nearby_n())
    sys, user = prompts.proofread_chapter(project, store, chapter, rules, nearby_text=nearby)
    data = llm.chat_json(sys, user, tag="proofread", role="write", max_tokens=max_tokens)
    if not isinstance(data, dict):
        return {}
    content = str(data.get("content") or "").strip()
    if not content:
        return {}
    notes = data.get("notes") or []
    if not isinstance(notes, list):
        notes = [str(notes)] if str(notes).strip() else []
    return {"content": content, "notes": [str(n) for n in notes if str(n).strip()]}


def polish_paragraph(project, text, mode="polish", style_ref="", directive="",
                     store=None, ctx_style=None, ctx_notes=None, ctx_rp=None):
    """AI 段落工具（v0.53 双端）：对选中文本就地润色。

    mode: polish（文笔润色）/ expand（扩写）/ shorten（精简）/ deai（去AI味）。
    style_ref：v1.02 参考文风样本（可选，全局「去AI味」配置）——处理时模仿其语感句式，不抄内容。
    directive：v1.67 用户附加要求（可选）——优先级最高，必须在结果中落实（如"缩写成一半"）。
    store：v1.68 传当前项目 store 时启用「涉及人物读取推理」（读角色卡按人设写）。
    ctx_style/ctx_notes/ctx_rp：v1.68 上下文开关（None=现读 config 的 tool_ctx_* 键，
          默认全开；需要省 token 时设置页可关）。
    返回处理后的段落文本；模型失败抛 LLMError，由调用方提示。
    """
    import config as _cfg168
    _cfg = _cfg168.load_config()
    if ctx_style is None:
        ctx_style = bool(_cfg.get("tool_ctx_style", True))
    if ctx_notes is None:
        ctx_notes = bool(_cfg.get("tool_ctx_notes", True))
    if ctx_rp is None:
        ctx_rp = bool(_cfg.get("tool_ctx_rp", True))
    sys, user = prompts.polish_paragraph(
        project, text, mode, style_ref=style_ref, directive=directive,
        ctx_style=ctx_style, ctx_notes=ctx_notes, ctx_rp=ctx_rp, store=store)
    # v1.68 后半程：设置页「码字AI（续写/段落工具）」指定了 API 配置就用它（未指定跟随正文写作）
    tool_prof = str((_cfg.get("role_profiles") or {}).get("write_tool") or "").strip() or None
    return llm.chat_text(sys, user, tag="polish_%s" % mode, role="write",
                         profile=tool_prof, max_tokens=4000).strip()


def classify_characters(project, store):
    """AI 自动给全部角色分类（主要角色/配角/NPC/反派…）。

    返回 {角色名: 分类名} 映射（只含 AI 明确判定的角色）。由调用方写回各角色卡 category。
    """
    sys, user = prompts.classify_characters(project, store)
    data = llm.chat_json(sys, user, tag="classify_characters", role="decide")
    roles = {}
    if isinstance(data, dict):
        m = data.get("roles")
        if isinstance(m, dict):
            for k, v in m.items():
                name = str(k).strip()
                cat = str(v or "").strip()
                if name and cat:
                    roles[name] = cat
    return roles


def character_from_data(data, created_by="ai"):
    card = CharacterCard()
    card.name = str(data.get("name", "") or "").strip()
    card.role = str(data.get("role", "") or "")
    card.age = str(data.get("age", "") or "")
    card.gender = str(data.get("gender", "") or "")
    card.personality = str(data.get("personality", "") or "")
    card.traits = [str(t) for t in (data.get("traits") or []) if str(t).strip()]
    card.values = str(data.get("values", "") or "")
    card.goals = str(data.get("goals", "") or "")
    card.fears = str(data.get("fears", "") or "")
    card.speech_style = str(data.get("speech_style", "") or "")
    card.backstory = str(data.get("backstory", "") or "")
    card.relationships = str(data.get("relationships", "") or "")
    card.appearance = str(data.get("appearance", "") or "")
    card.description = str(data.get("description", "") or "")
    card.scenario = str(data.get("scenario", "") or "")
    card.first_mes = str(data.get("first_mes", "") or "")
    card.mes_example = str(data.get("mes_example", "") or "")
    card.system_prompt = str(data.get("system_prompt", "") or "")
    card.post_history_instructions = str(data.get("post_history_instructions", "") or "")
    card.creator_notes = str(data.get("creator_notes", "") or "")
    raw_tags = data.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = re.split(r"[，,、;；\s]+", str(raw_tags))
    card.tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    card.character_version = str(data.get("character_version", "") or "")
    card.created_by = created_by
    if not card.name:
        raise ValueError("角色名缺失，无法创建角色卡")
    return card


def _match_existing_char(store, name):
    """在现有角色池里按名字找「同名角色」，避免 AI 重复建卡（v0.98）。

    匹配规则：全名精确 → 去除空白后的精确 → 双向包含（唯一命中的才复用，防误并）。
    返回 (cid, card, lib)；未命中返回 None。含已归档（卡库）角色——重复建档时优先复用旧卡。
    """
    name = (name or "").strip()
    if not name:
        return None
    pool = []
    for cid, nm, _st in store.list_characters():
        pool.append((cid, str(nm or "").strip()))
    exact = [x for x in pool if x[1] == name]
    if len(exact) == 1:
        cid = exact[0][0]
        card, lib = store.load_character(cid)
        return (cid, card, lib) if card else None
    name_n = re.sub(r"\s+", "", name)
    norm = [(cid, re.sub(r"\s+", "", nm)) for cid, nm in pool]
    n_exact = [x for x in norm if x[1] == name_n]
    if len(n_exact) == 1:
        cid = n_exact[0][0]
        card, lib = store.load_character(cid)
        return (cid, card, lib) if card else None
    # 双向包含（去空格后）：如「阿梨」vs「客栈老板娘阿梨」；必须唯一命中，否则不并
    hits = []
    for cid, nm in norm:
        if nm and (name_n in nm or nm in name_n) and len(name_n) >= 2:
            hits.append(cid)
    if len(hits) == 1:
        card, lib = store.load_character(hits[0])
        return (hits[0], card, lib) if card else None
    return None


def save_generated_character(store, data, hint=""):
    """AI 生成角色卡的保存入口（v0.98 防重复）：先按名字查重，同名则**复用旧卡**
    （补齐旧卡空缺的 description/personality/scenario，不新建）；
    无同名才新建。返回 (card, lib, created)；valueError/脏数据抛给调用方。
    """
    card = character_from_data(data, created_by="ai")
    hit = _match_existing_char(store, card.name)
    if hit is not None:
        cid, old, lib = hit
        # 只补齐旧卡空缺字段，保留旧信息（信息库已有内容不覆盖）
        changed = False
        for k in ("description", "personality", "first_mes", "mes_example",
                  "scenario", "appearance", "speech_style"):
            v = str(getattr(card, k) or "").strip()
            if v and not str(getattr(old, k) or "").strip():
                setattr(old, k, v)
                changed = True
        new_sc = str(data.get("scenario") or "").strip()
        if new_sc and not str(lib.scenario or "").strip():
            lib.scenario = new_sc
            changed = True
        if old.status in ("archived", "discarded"):
            # 主AI重新把该角色引入剧情 → 自动解除归档/废弃（与「点名召回」语义一致）
            old.status = "active"
            changed = True
        if changed:
            old.version += 1
            store.save_character(old, lib)
        return old, lib, False
    lib = InfoLibrary(card.id)
    if (data.get("scenario") or "").strip():
        lib.scenario = str(data.get("scenario", "")).strip()
    store.save_character(card, lib)
    return card, lib, True