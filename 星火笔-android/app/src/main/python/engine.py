# -*- coding: utf-8 -*-
"""总调度引擎：串联「出场决断 → 角色推理 → 主AI校验 → 写作 → 审查 → 战后更新」全流程。"""
import os

import char_ai
import config
import git_tool
import llm
import main_ai
import web_search
from models import (CHAPTER_STATUS_APPROVED, CHAPTER_STATUS_DRAFT,
                    CHAR_STATUS_ACTIVE,
                    CHAR_STATUS_ARCHIVED, CHAR_STATUS_DISCARDED, Chapter,
                    Foreshadow, InfoLibrary)
from prompts import fmt_card, fmt_library

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_CONSOLIDATE_ROUNDS = 2
MAX_AUTO_REWRITES = 2   # 主AI审查不通过时，最多请正文AI按意见重写的轮数
MAX_AUTO_RETRY = 3      # 全自动模式下单章生成连续失败（API 报错）自动重试上限，超过才停止
LENGTH_RETRY_MAX = 6    # v1.17 字数不达标循环重写上限（每轮带警示直到达标；防死循环）


def _rank_in_volume(project):
    """本卷内章节序号：优先 volume_target（单卷连续），其次旧版 volumes。"""
    next_ch = int(project.state.get("next_chapter", 1))
    if int(project.volume_target or 0) > 0 or not project.volumes:
        return next_ch, None
    vol = project.current_volume()
    start = sum(v.total_chapters for v in project.volumes[:project.state.get("volume", 1) - 1])
    return next_ch - start, vol


def _clean_beats(raw):
    """清洗主AI规划的本章剧情点：仅保留 1-4 条非空字符串、每条截断 40 字。"""
    if not isinstance(raw, list):
        return []
    out = []
    for b in raw:
        s = str(b or "").strip()
        if s:
            out.append(s[:40])
        if len(out) >= 4:
            break
    return out


def _pace_advice(scores):
    """v2.62 自适应节奏：依据上一章量化评分生成本章写作引导（闭环智能化）。

    v2.63 软化：低分项给出**方向提示与参考手段**，把具体取舍交由 AI 结合故事框架自主决定
    （不再硬性规定「必须保证情绪高点」这类条款）；新增 natural 维度。
    评分低项给出对应引导；无评分或全部合格返回空串。
    """
    if not isinstance(scores, dict):
        return ""
    tips = []
    try:
        r = int(scores.get("rhythm") or 0)
        if r and r <= 5:
            tips.append("上章节奏偏平（%d分）：本章结合故事框架自主调整推进结构"
                        "（参考：压缩铺垫、加快事件推进、增强节拍变化，以故事需要为准）" % r)
    except (TypeError, ValueError):
        pass
    try:
        p = int(scores.get("payout") or 0)
        if p and p <= 5:
            tips.append("上章情绪输出弱（%d分）：结合故事框架自主设计本章情绪支点"
                        "（爽点/悬念/情感转折均可，由故事类型决定，不必硬造爽点）" % p)
    except (TypeError, ValueError):
        pass
    try:
        i = int(scores.get("immersion") or 0)
        if i and i <= 5:
            tips.append("上章沉浸感弱（%d分）：避免出戏处与翻译腔，描写贴合本故事语感" % i)
    except (TypeError, ValueError):
        pass
    try:
        c = int(scores.get("character") or 0)
        if c and c <= 5:
            tips.append("上章人设贴合差（%d分）：严格按角色卡言行，防OOC" % c)
    except (TypeError, ValueError):
        pass
    try:
        n = int(scores.get("natural") or 0)
        if n and n <= 5:
            tips.append("上章情节自然度低（%d分）：本章转折要有因果铺垫，避免巧合堆砌与生硬推进" % n)
    except (TypeError, ValueError):
        pass
    return "；".join(tips)


class NovelEngine:
    def __init__(self, store, log_fn=None):
        self.store = store
        self.log = log_fn or (lambda kind, msg: None)

    # ---------- 世界初始化 ----------
    def ensure_world(self, project):
        """角色池为空时，由主AI根据开局与卷规划自动生成核心角色。"""
        chars = self.store.list_characters()
        if chars:
            return
        self.log("info", "角色池为空，主AI正在自动生成核心角色…")
        descriptions = [
            "故事核心主角（第一视角重点刻画，性格要有缺陷与成长空间）",
            "与主角关系最紧密的第一配角（分担冲突与对话，性格与主角互补或对立）",
            "一名推动本卷主线的关键配角（掌握关键线索或权力）",
        ]
        try:
            for desc in descriptions:
                data = main_ai.generate_character_ai(desc, project, self.store)
                card = main_ai.character_from_data(data, created_by="ai")
                lib = InfoLibrary(card.id)
                if data.get("scenario"):
                    lib.scenario = str(data.get("scenario", "")).strip()
                self.store.save_character(card, lib)
                self.log("info", "自动生成角色：%s（%s）" % (card.name, card.role))
        except llm.StopRequested:
            raise   # 用户停止：立即终止，不当作普通失败
        except llm.LLMError as e:
            self.log("error", "自动生成角色失败：%s。可稍后在「角色」页手动生成。" % e)
            raise

    # ---------- 章节草稿 ----------
    def generate_draft(self, project, user_directive="", user_feedback="",
                       user_draft="", beats_override=None, beats_confirm=None):
        """走完整推理管线，产出本章草稿（不入库完成状态）。

        user_directive：本次临场指示；user_draft：用户提供的本章草稿（AI 在草稿基础上
        扩写润色，禁止改变剧情）；章节写作计划（chapter_plans 第 N~M 章生效）自动并入
        user_directive。
        """
        cfg = config.load_config()
        state = project.state
        ch_no = int(state.get("next_chapter", 1))
        rank, vol = _rank_in_volume(project)
        vol_no = int(state.get("volume", 1))

        if state.get("story_complete"):
            self.log("info", "故事已完结，无法继续生成。")
            return None

        # 章节写作计划：用户预置的第 start~end 章写作指示自动生效，与本次临场指示拼接
        plan_note = self._match_chapter_plan(project, ch_no)
        if plan_note:
            self.log("info", "应用章节写作计划（第 %d 章命中）：%s" % (ch_no, plan_note[:60]))
            user_directive = ("%s\n%s" % (plan_note, user_directive)).strip() \
                if user_directive else plan_note

        # 首次生成时留初始世界快照（供日后从第 1 章重写时回滚）
        if not self.store.list_snapshot_indices() and not self.store.list_chapter_indices():
            self.store.save_world_snapshot(0)

        self.log("info", "═══ 开始生成第 %d 章（本卷第 %d 章）═══" % (ch_no, rank))
        if rank == 1:
            target = project.chapter_target()
            if target:
                title = ("：%s" % vol.title) if (vol and vol.title) else ""
                self.log("info", "本卷目标 %d 章%s" % (target, title))
            else:
                self.log("info", "本卷目标：由主AI把控节奏")

        # ① 出场决断
        self.log("info", "① 主AI决断：判断出场角色与场景焦点…")
        decide = main_ai.decide_characters(project, self.store, ch_no, vol_no,
                                           rank, user_directive)
        # ①.1 名册点名召回：主AI点名的池外角色（久未出场的旧角色回归）→ 补充完整档案后重判
        # （角色池两级视图：候选详单 + 全量名册，见 prompts.char_pool；最多补 2 轮）
        for _recall_round in range(2):
            recall_names = [str(n).strip() for n in (decide.get("recall") or [])
                            if str(n).strip()]
            recall_names = recall_names[:8]
            if not recall_names:
                break
            name_to_id = {}
            for cid, nm, _st in self.store.list_characters():
                name_to_id[nm] = cid
            found = []
            for nm in recall_names:
                cid = name_to_id.get(nm)
                if not cid:
                    # 允许部分匹配（名册里名字带前缀/后缀）
                    for n2, c2 in name_to_id.items():
                        if nm and (nm in n2 or n2 in nm):
                            cid = c2
                            break
                if cid:
                    card, lib = self.store.load_character(cid)
                    if card:
                        found.append("%s\n%s" % (fmt_card(card), fmt_library(lib)))
            if not found:
                self.log("warn", "主AI点名召回的角色不在名册中：%s（忽略，按当前名单继续）"
                         % "、".join(recall_names))
                break
            self.log("info", "主AI点名召回角色：%s（补充档案后重新决断…）"
                     % "、".join(recall_names))
            decide = main_ai.decide_characters(project, self.store, ch_no, vol_no,
                                               rank, user_directive,
                                               extra_context="\n".join(found))
        scene_focus = decide.get("scene_focus") or "延续当前主线推进"
        new_hint = (decide.get("new_character_hint") or "").strip()
        cast = [c for c in decide.get("characters", []) if c.get("id")]

        pool_ids = set(self.store.get_character_ids())
        valid_id = lambda cid: cid in pool_ids
        cast = [c for c in cast if valid_id(c["id"])]

        # 主AI点名已归档/已废弃角色出场（剧情需要）→ 自动解除归档恢复在籍
        for c in cast:
            card, lib = self.store.load_character(c["id"])
            if card and card.status in (CHAR_STATUS_ARCHIVED, CHAR_STATUS_DISCARDED):
                was = card.status
                card.status = CHAR_STATUS_ACTIVE
                card.version += 1
                # 带上信息库保存：只传 card 会把该角色的事件/情报/隐秘清空
                self.store.save_character(card, lib)
                self.log("info", "角色 %s 因剧情需要%s，恢复出场。"
                         % (card.name, "解除归档" if was == CHAR_STATUS_ARCHIVED
                            else "解除废弃"))

        # 主AI判断本章需要新角色（如新场景人物/新势力成员/后宫新成员等）
        # → 自动建档并让该角色本章登场，无需用户手动建卡
        if new_hint:
            made = self._introduce_character(project, new_hint)
            if made:
                card, _ = made
                cast.append({"id": card.id, "role_in_scene": "本章新登场",
                             "notes": new_hint})
                self.log("info", "主AI按情节需要引入新角色：%s（%s），本章登场。"
                         % (card.name, card.role))
            new_hint = ""  # 已处理（无论成败），不再作为候选提示传给校验
        if not cast:
            pool = self.store.list_characters()
            if pool:
                cid = next((x[0] for x in pool if x[2] == CHAR_STATUS_ACTIVE), pool[0][0])
                cast = [{"id": cid, "role_in_scene": "主角视角", "notes": ""}]
            else:
                raise llm.LLMError("角色池为空，请先在「角色」页创建或自动生成角色。")
        self.log("info", "本章出场角色：%s" % ", ".join(
            self._char_name(c["id"]) + ("（%s）" % c.get("role_in_scene") if c.get("role_in_scene") else "")
            for c in cast))

        # ② 角色推理
        mode = cfg.get("reasoning_mode", "sequential")
        workers = int(cfg.get("max_workers", 5))
        self.log("info", "② 角色推理（%s模式）：代入各角色推断行为…"
                 % ("并行" if mode == "parallel" else "串行"))
        inferences = char_ai.run_inference(
            project, self.store, cast, ch_no, scene_focus,
            mode=mode, max_workers=workers,
            on_progress=lambda cid: None)
        for cid, data in inferences.items():
            if data.get("_error"):
                self.log("warn", "角色 %s 推理失败：%s" % (self._char_name(cid), data["_error"]))
            elif data.get("_missing"):
                self.log("warn", "角色 %s 已不存在，忽略其推理。" % self._char_name(cid))
            if not self._has_appeared(cid):
                data["is_first_appearance"] = True

        # ③ 综合校验（最多两轮修正；主AI可按需回顾章节/联网搜索，然后重判）
        self.log("info", "③ 主AI综合校验：核对主线方向与伏笔管理…")
        consolidation = {}
        # new_hint 已在 ① 处理后置空（无论建卡成败都不再向校验环节提示候选新角色，避免重复建卡）
        new_hint = ""
        extra_context = ""
        need_rounds = 0
        search_rounds = 0
        search_on = bool(cfg.get("web_search_enabled", False))
        for rnd in range(MAX_CONSOLIDATE_ROUNDS + 4):
            consolidation = main_ai.consolidate(
                project, self.store, ch_no, scene_focus, inferences, new_hint,
                extra_context, search_enabled=search_on)
            # 主AI觉得前文概要不够 → 按需回顾指定章节全文后再判
            need = [str(n) for n in (consolidation.get("need_chapters") or [])]
            need = [n for n in need if n.isdigit()]
            if need and need_rounds < 2:
                need_rounds += 1
                parts = []
                for n in need[:3]:
                    ch_old = self.store.load_chapter(int(n))
                    if ch_old and ch_old.status == "approved":
                        parts.append("【第%s章】%s\n%s" % (n, ch_old.title, ch_old.content[:1500]))
                if parts:
                    extra_context = "\n".join(parts)
                    self.log("info", "主AI按需回顾第 %s 章详情后重新校验…"
                             % "、".join(n for n in need[:3]))
                    continue
            # 联网搜索灵感（开关开启时）：主AI不确定走向 → 搜同类剧情参考后重判
            if search_on and search_rounds < 2:
                queries = [str(q) for q in (consolidation.get("search_queries") or [])
                           if str(q).strip()]
                queries = queries[:3]
                if queries:
                    search_rounds += 1
                    refs = []
                    for q in queries:
                        items = web_search.search(q)
                        if items:
                            refs.append("查询：「%s」\n%s" % (q, web_search.format_results(items)))
                    if refs:
                        extra_context = "\n".join(refs)
                        self.log("info", "主AI联网搜索灵感（%d 组查询）后重新校验…" % len(queries))
                        continue
            if consolidation.get("verdict") != "adjust":
                break
            adj = consolidation.get("adjustment") or {}
            action = adj.get("action", "none")
            if action == "add_character" and adj.get("new_character"):
                try:
                    # v0.98 防重复：同名角色已存在则复用旧卡，不重复建档
                    card, lib, created = main_ai.save_generated_character(
                        self.store, adj["new_character"])
                    if not created:
                        self.log("info", "角色池已有同名角色「%s」，复用旧卡，不重复建档。"
                                 % card.name)
                    else:
                        self.log("info", "主AI引入新角色：%s（%s），并代为推理…"
                                 % (card.name, card.role))
                    _, data = char_ai.reason_one(project, self.store, card.id, ch_no,
                                                 scene_focus, "新登场角色")
                    data["is_first_appearance"] = True  # 本章首登：first_mes 需注入写作
                    inferences[card.id] = data
                    new_hint = ""
                except Exception as e:
                    self.log("warn", "新角色创建失败：%s" % e)
            elif action == "new_event" and adj.get("event"):
                self.log("info", "主AI设计新事件修正走向：%s" % adj["event"])
                scene_focus = scene_focus + "；【本章新增事件】" + adj["event"]
                for c in cast:
                    _, data = char_ai.reason_one(project, self.store, c["id"], ch_no,
                                                 scene_focus, c.get("role_in_scene", ""))
                    if not self._has_appeared(c["id"]):
                        data["is_first_appearance"] = True
                    inferences[c["id"]] = data
                new_hint = ""
            else:
                break

        self.log("info", "主AI裁定本章走向：%s" % (consolidation.get("approved_direction") or "（沿用场景焦点）"))

        # v2.63 框架驱动规划卡：主AI结合故事框架裁定的本章意图与套路陷阱预警，
        # 作为指导注入写作（非硬性条款），随 consolidation 一并存档。
        _pnote = str(consolidation.get("planning_note") or "").strip()
        _cwatch = [str(x).strip() for x in (consolidation.get("cliche_watch") or [])
                   if str(x).strip()]
        if _pnote:
            self.log("info", "本章意图（框架裁定）：%s" % _pnote)
        if _cwatch:
            self.log("info", "本章套路陷阱预警：%s" % "；".join(_cwatch))

        # 章节剧情点（v2.52）：主AI在校验时规划本章 2-3 个必须完成的剧情点，
        # 作为硬要求注入正文写作、审查时核对完成度、随章节 reasoning 存档。
        # v2.55：用户可在生成页编辑剧情点，beats_override 非空时以用户指定为准（接管控制权）。
        beats = _clean_beats(consolidation.get("chapter_beats"))
        override = _clean_beats(beats_override)
        if override:
            beats = override
            self.log("info", "本章剧情点（用户指定）：%s" % " ① ".join(beats))
        elif beats:
            self.log("info", "本章剧情点：%s" % " ① ".join(beats))
        # v2.62 生成前剧情点确认关卡：回调存在时暂停管线，把剧情点交给用户确认/修改
        if beats and callable(beats_confirm):
            try:
                res = beats_confirm(
                    list(beats),
                    str(consolidation.get("approved_direction") or scene_focus))
                if isinstance(res, list) and res:
                    beats = _clean_beats(res)
                    self.log("info", "本章剧情点（用户确认后）：%s" % " ① ".join(beats))
                else:
                    self.log("info", "本章剧情点（用户跳过确认，沿用主AI规划）")
            except Exception as e:
                self.log("warn", "剧情点确认环节异常，沿用主AI规划：%s" % e)

        # v2.62 自适应节奏：读取上一章量化评分，低分项生成强化指令并入写作方向
        # v2.63：引导语言已软化（参考性手段，取舍交 AI 结合故事框架自主决定）
        pace_advice = ""
        prev_ch = None
        if ch_no > 1:
            prev_ch = self.store.load_chapter(ch_no - 1)
            if prev_ch:
                pace_advice = _pace_advice(
                    ((prev_ch.reasoning or {}).get("review") or {}).get("scores"))
                if pace_advice:
                    self.log("info", "自适应节奏（读上章评分）：%s" % pace_advice)

        # 知识库维护：consolidate 给出的 kb_update 条目追加进主AI知识库（仅主AI读）
        kb_items = [str(x).strip() for x in (consolidation.get("kb_update") or [])
                    if str(x).strip()]
        if kb_items:
            old_kb = (project.story_knowledge or "").strip()
            new_kb = "\n".join("- %s" % s for s in kb_items)
            project.story_knowledge = (old_kb + "\n" + new_kb).strip() if old_kb else new_kb
            self.store.save_project(project)
            self.log("info", "主AI知识库新增 %d 条备忘。" % len(kb_items))

        # ④ 写作
        target_chars = int(cfg.get("chapter_target_chars", 2500))
        # v2.63 篇幅自适应（全自动流程优化）：上一章实际字数与目标偏差超过 25% 时，
        # 本章目标微调 ±10%，让篇幅向用户设定目标回归（不硬性压缩单章内容）。
        base_chars = target_chars
        if prev_ch is not None and prev_ch.content:
            prev_len = len(prev_ch.content)
            if prev_len and base_chars:
                diff = (prev_len - base_chars) / float(base_chars)
                if diff > 0.25:
                    target_chars = max(300, int(base_chars * 1.10))
                    self.log("info", "篇幅自适应：上章 %d 字超出目标 %d 字，本章目标调为 %d 字"
                             % (prev_len, base_chars, target_chars))
                elif diff < -0.25:
                    target_chars = max(300, int(base_chars * 0.90))
                    self.log("info", "篇幅自适应：上章 %d 字低于目标 %d 字，本章目标调为 %d 字"
                             % (prev_len, base_chars, target_chars))
        fs_lines = []
        for f in consolidation.get("foreshadows", []) or []:
            if f.get("f_type") == "plant":
                fs_lines.append("埋设伏笔：%s" % f.get("text", ""))
            elif f.get("f_type") == "payoff":
                fs_lines.append("回收伏笔：%s" % f.get("text", ""))
        self.log("info", "④ 主AI写作本章（目标约 %d 字），次数：%s"
                 % (target_chars, ("1" if not user_feedback else "2（含修改意见）")))
        recent_n = int(cfg.get("writer_recent_chapters", 3) or 0)  # 0=不读前文
        # v1.17 正文长度上下限：用户自设（0=自动 target×0.8/×1.15）；自适应目标夹在上下限内
        _min_chars = int(cfg.get("chapter_min_chars") or 0)
        _max_chars = int(cfg.get("chapter_max_chars") or 0)
        if _min_chars > 0 and _max_chars > 0 and _max_chars < _min_chars:
            _min_chars, _max_chars = _max_chars, _min_chars
        if _min_chars > 0:
            target_chars = max(_min_chars, min(target_chars, _max_chars if _max_chars > 0 else target_chars))
        # v1.21 情景规则卡：主AI从项目可用库选卡/无匹配时自做新卡 → 解析内容注入正文AI
        scene_cards = self._collect_scene_cards(project, consolidation)
        sc_reason = str(consolidation.get("scene_cards_reason") or "").strip()
        if scene_cards:
            self.log("info", "主AI选中本章情景规则卡：%s（仅按对应情景片段参考写法，"
                     "不要求改变铺垫/节奏）%s"
                     % ("、".join(c["name"] for c in scene_cards),
                        ("；选卡理由：%s" % sc_reason) if sc_reason else ""))
        else:
            self.log("info", "本章未选用情景卡%s（正文AI按常规叙事自然书写铺垫与推进）"
                     % (("——" + sc_reason) if sc_reason else ""))

        def _write_once(feedback=""):
            fb = feedback
            if user_feedback:
                fb = (fb + "\n" if fb else "") + user_feedback
            direction = consolidation.get("approved_direction") or scene_focus
            if pace_advice:
                direction = "%s（自适应节奏要求：%s）" % (direction, pace_advice)
            return main_ai.write_chapter(
                project, self.store, ch_no, scene_focus,
                direction,
                inferences, fs_lines, target_chars, fb,
                recent_chapters=recent_n, max_tokens=int(target_chars * 3) + 2000,
                draft=user_draft, beats=beats,
                planning_note=_pnote, cliche_watch=_cwatch,
                scene_cards=scene_cards,
                min_chars=_min_chars if _min_chars > 0 else None,
                max_chars=_max_chars if _max_chars > 0 else None)

        title, content = _write_once()
        # 字数硬约束（双向）：超出上限或低于下限自动重新生成（不压缩不截断；循环直到达标）
        title, content = self._ensure_chapter_length(
            project, ch_no, target_chars, title, content,
            lambda fb: _write_once(fb))

        chapter = Chapter(ch_no, vol_no)
        chapter.characters = [c["id"] for c in cast] + [
            cid for cid in inferences if cid not in [c["id"] for c in cast]]
        chapter.title = title
        chapter.scene = scene_focus
        chapter.content = content

        # ④.3 写后校对（正文AI完稿后、主AI审查前）：只改文本（描写/用词/语句/修辞），
        # 不改剧情。规则开放给用户在设置页编辑；本环节失败不阻断生成（保留原文继续）。
        proofread_notes = self._proofread_once(project, chapter, target_chars)
        content = chapter.content

        # ④.5 主AI审查：不满意时自动请正文AI按意见重写（最多 MAX_AUTO_REWRITES 轮）。
        # 只有首次生成（无用户修改意见）时才自动审查；用户手动带意见重写时直接交给用户。
        review = {}
        if cfg.get("auto_rewrite", True) and not user_feedback:
            self.log("info", "④.5 主AI审查本章：核对人设OOC/主线推进/节奏/完整性…")
            for rnd in range(MAX_AUTO_REWRITES + 1):
                if ch_no <= 1:
                    target = "开篇第 1 章，立足开局推进主线"
                else:
                    target = "第 %d 章，延续第 %d 章结尾推进主线" % (ch_no, ch_no - 1)
                review = main_ai.review_chapter(project, self.store, chapter, target,
                                                beats=beats)
                # 模型可能把布尔写成字符串（"false"/"False"）：只有严格为 true 才算通过
                approved = str(review.get("approved")).strip().lower() == "true"
                if approved or rnd >= MAX_AUTO_REWRITES:
                    break
                feedback = str(review.get("rewrite_feedback", "") or "").strip()
                self.log("info", "主AI审查未通过（第%d轮），请正文AI按意见重写：%s"
                         % (rnd + 1, (feedback[:80] or "（无具体意见）")))
                title, content = _write_once(feedback)
                title, content = self._ensure_chapter_length(
                    project, ch_no, target_chars, title, content,
                    lambda fb: _write_once((feedback + "\n" if feedback else "") + fb))
                chapter.title = title
                chapter.content = content
                chapter.status = CHAPTER_STATUS_DRAFT
                # 重写后的文本未经写后校对，补一次（只改文本不改剧情，失败不阻断）
                proofread_notes += self._proofread_once(project, chapter, target_chars)
                content = chapter.content
            if review.get("approved"):
                self.log("info", "主AI审查通过。")
            else:
                self.log("info", "主AI审查有保留意见：%s"
                         % ("；".join(review.get("issues", []) or [])[:120] or "详见弹窗"))
        else:
            self.log("info", "（用户手动重写模式，跳过自动审查，交用户把关）" if user_feedback else
                     "（自动审查已关闭，直接交用户把关）")

        # v2.57：保留 ④.3 校对阶段写入的 AI八股报告（reasoning 整体重建时不丢）
        _deai = dict(chapter.reasoning["deai_report"]) if \
            isinstance(chapter.reasoning, dict) and chapter.reasoning.get("deai_report") else None
        chapter.reasoning = {
            "decide": decide,
            "inferences": {k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
                           for k, v in inferences.items()},
            "consolidation": {k: v for k, v in consolidation.items()},
        }
        if _deai:
            chapter.reasoning["deai_report"] = _deai
        if beats:
            chapter.reasoning["beats"] = beats
        if review and review.get("scores"):
            _sc = review["scores"]
            self.log("info", "本章评分：沉浸%s / 节奏%s / 爽点%s / 人设%s / 自然%s"
                     % (_sc.get("immersion", "—"), _sc.get("rhythm", "—"),
                        _sc.get("payout", "—"), _sc.get("character", "—"),
                        _sc.get("natural", "—")))
        if review:
            chapter.reasoning["review"] = {k: v for k, v in review.items()}
        if proofread_notes:
            chapter.reasoning["proofread"] = {"notes": list(proofread_notes)}
        if user_feedback:
            chapter.reasoning["user_feedback"] = user_feedback
        chapter.foreshadows = list(consolidation.get("foreshadows", []) or [])
        self.store.save_chapter(chapter)
        self.log("info", "第 %d 章草稿完成：《%s》（%d 字）" % (ch_no, title, len(content)))
        return chapter

    # ---------- 战后更新与完成 ----------
    def finalize_chapter(self, project, chapter, review_data=None):
        """战后更新：信息库/角色卡/状态/伏笔，推进进度（逐章审查模式在用户通过后调用）。"""
        ch_no = chapter.index
        # 生成阶段（generate_draft ④.5）若已做过主AI审查，自动取用其结果（含 brief/存档建议）
        if review_data is None:
            review_data = chapter.reasoning.get("review") or None
        self.log("info", "⑤ 战后更新：更新角色信息库与角色卡…")
        world = {}
        try:
            world = main_ai.update_world(project, self.store, chapter)
        except llm.StopRequested:
            raise   # 用户停止：本章不归档，立即终止
        except llm.LLMError as e:
            self.log("warn", "战后更新调用失败：%s（本章仍将归档，角色卡暂不更新）" % e)

        self._apply_world_updates(project, chapter, world)

        if review_data:
            chapter.reasoning["review"] = {k: v for k, v in review_data.items()}

        # 章节摘要：优先用主AI审查时的 brief，否则取正文首段
        brief = ""
        if review_data and review_data.get("brief"):
            brief = str(review_data["brief"]).strip()
        if not brief:
            first_para = next((p.strip() for p in (chapter.content or "").split("\n")
                               if p.strip()), "")
            brief = first_para[:120]
        chapter.brief = brief
        self._apply_foreshadows(project, chapter)

        chapter.status = CHAPTER_STATUS_APPROVED
        self.store.save_chapter(chapter)

        state = project.state
        state["next_chapter"] = ch_no + 1

        # 写作计划自动清理：区间写完（next_chapter 越过 end）自动移除，避免旧计划残留
        next_no = int(state.get("next_chapter", 1))
        expired = [p for p in (project.chapter_plans or [])
                   if isinstance(p, dict)
                   and int(p.get("end", 0) or 0) < next_no]
        if expired:
            project.chapter_plans = [p for p in (project.chapter_plans or [])
                                     if p not in expired]
            self.store.save_project(project)
            for p in expired:
                self.log("info", "写作计划已写完（第 %d~%d 章），自动移除：%s"
                         % (int(p.get("start", 0) or 0), int(p.get("end", 0) or 0),
                            str(p.get("note") or "")[:40]))

        # 卷信息压缩：每 N 章（设置页可配，默认 5）或卷末，主AI压缩管理笔记 + 评估角色池 + 知识库维护
        cfg = config.load_config()
        compress_n = max(1, int(cfg.get("compress_interval", 5) or 5))
        if ch_no % compress_n == 0 or project.volume_done():
            self.log("info", "⑥ 主AI压缩卷信息（每 %d 章；管理笔记更新 + 角色池整理 + 知识库维护）…" % compress_n)
            try:
                summary_data = main_ai.compress_summary(project, self.store)
                note = str(summary_data.get("note") or "").strip()
                if note:
                    project.story_summary = note
                # 主AI笔记·重要角色档案与后续剧情灵感（结构化保存，供 story_context / 决断候选池使用）
                kcs = summary_data.get("key_characters") or []
                if isinstance(kcs, list):
                    project.story_characters = [
                        {"name": str(x.get("name", "")).strip(),
                         "info": str(x.get("info", "")).strip()}
                        for x in kcs if isinstance(x, dict) and str(x.get("name", "")).strip()]
                ideas = summary_data.get("ideas") or []
                if isinstance(ideas, list):
                    project.story_ideas = [str(x).strip() for x in ideas if str(x).strip()]
                knowledge = str(summary_data.get("knowledge") or "").strip()
                if knowledge:
                    old_kb = (project.story_knowledge or "").strip()
                    project.story_knowledge = (old_kb + "\n" + knowledge).strip() if old_kb else knowledge
                self._apply_archive_suggestions(summary_data.get("archive") or [])
                self.log("info", "主AI管理笔记已更新（含 %d 个重要角色档案、%d 条后续灵感）。"
                         % (len(project.story_characters), len(project.story_ideas)))
            except llm.StopRequested:
                raise
            except llm.LLMError as e:
                self.log("warn", "卷信息压缩失败：%s（沿用旧笔记）" % e)

        # 卷末处理
        if project.volume_done():
            vol = project.current_volume()
            target = project.chapter_target()
            self.log("info", "★ 本卷目标（%d 章）达成！生成卷末衔接…" % target)
            try:
                closing = main_ai.volume_closing(project, self.store, vol)
                self.store.append_log("【本卷卷末】\n%s" % closing)
            except llm.StopRequested:
                raise
            except llm.LLMError as e:
                self.log("warn", "卷末总结失败：%s" % e)
            if len(project.volumes) > int(state.get("volume", 1)):
                state["volume"] = int(state.get("volume", 1)) + 1
                self.log("info", "已进入第 %d 卷（沿用旧版结构化规划）。" % state["volume"])
            elif int(project.volume_target or 0) > 0:
                # 自然语言模式下：目标达成 → 清空目标，由主AI接管节奏继续（用户可在项目页重新设目标）
                project.volume_target = 0
                self.store.append_log("本卷目标达成。继续生成将进入「主AI把控节奏」的自由续写，"
                                      "可在项目页重新设定本卷目标章数。")
                self.log("info", "本卷目标达成；继续生成时由主AI把控节奏（可随时在项目页重设目标）。")
            else:
                state["story_complete"] = True
                self.store.append_log("【全书完】%s 已全部完成。" % project.title)
                self.log("info", "★ 全书完成！")

        self.store.save_project(project)
        self.store.append_log("第%d章《%s》完成并归档。" % (ch_no, chapter.title))
        # 存档世界状态快照（供日后章节重写时回滚角色卡/信息库/伏笔/管理笔记）
        self.store.save_world_snapshot(ch_no)
        git_tool.commit(_ROOT, "第%d章《%s》完成" % (ch_no, chapter.title), self.log)
        return chapter

    # ---------- 章节重写（世界状态回滚） ----------
    def _rollback_world_to(self, chapter_no):
        """世界状态回滚到第 chapter_no 章开始前：删该章及之后章节/旧快照、回退进度。

        返回是否成功。供「重写此章」与「删除本章及之后」共用。
        """
        ch_no = int(chapter_no)
        snap = self.store.load_world_snapshot(ch_no - 1)
        if snap is None:
            # v0.54 小说导入成项目：导入的项目没有逐章世界快照——
            # 改按「角色分章状态轨迹」回退角色卡/信息库/伏笔（每章完成后才留快照的老项目同样兜底）
            self.log("info", "第 %d 章之前无逐章世界快照，按角色分章状态轨迹回退…" % ch_no)
            self.store.rebuild_world_after_delete(ch_no - 1)
            self.store.delete_chapters_from(ch_no)
            for n in self.store.list_snapshot_indices():
                if n >= ch_no:
                    path = self.store.snapshot_path(n)
                    if os.path.exists(path):
                        try:
                            os.remove(path)
                        except OSError:
                            pass
            project = self.store.load_project()
            if project is None:
                return False
            state = project.state
            state["next_chapter"] = ch_no
            state["story_complete"] = False
            self.store.save_project(project)
            return True
        self.store.rollback_world(snap)
        self.store.delete_chapters_from(ch_no)
        # 清理该章及之后的旧快照（重新生成后会覆盖）
        for n in self.store.list_snapshot_indices():
            if n >= ch_no:
                path = self.store.snapshot_path(n)
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
        # 重新载入项目（rollback 已把回滚后的 story_summary 落盘），再回退进度
        project = self.store.load_project()
        state = project.state
        state["next_chapter"] = ch_no
        state["story_complete"] = False
        self.store.save_project(project)
        return True

    def _backup_chapters_from(self, ch_no, tag):
        """重写/删除前把第 ch_no 章及之后的章节备份进草稿箱，防止内容丢失。"""
        for i in self.store.list_chapter_indices():
            if i >= int(ch_no):
                ch = self.store.load_chapter(i)
                if ch:
                    self.store.backup_chapter_draft(ch, tag)

    def rewrite_from(self, project, chapter_no):
        """从第 chapter_no 章开始重写。

        将世界状态（角色卡/信息库/伏笔/管理笔记）回滚到该章开始前，
        删除该章及之后全部章节，进度回退到该章。返回是否成功。
        """
        ch_no = int(chapter_no)
        self._backup_chapters_from(ch_no, "rewrite")   # 先留旧版草稿，改崩可找回
        if not self._rollback_world_to(ch_no):
            return False
        self.store.append_log("【重写】从第 %d 章起重写：世界状态已回滚到该章之前，其后章节已删除。"
                              % ch_no)
        git_tool.commit(_ROOT, "重写：从第%d章重新开始" % ch_no, self.log)
        self.log("info", "已回滚世界状态并删除第 %d 章及之后章节，可从第 %d 章重新生成。"
                 % (ch_no, ch_no))
        return True

    def rollback_delete_from(self, project, chapter_no):
        """删除第 chapter_no 章及之后所有章节（世界状态回滚到该章开始前），不重新生成。

        返回是否成功；成功后进度回退到该章，可直接继续生成补写。
        """
        ch_no = int(chapter_no)
        self._backup_chapters_from(ch_no, "delete")    # 先留旧版草稿
        if not self._rollback_world_to(ch_no):
            return False
        self.store.append_log("【删除】已删除第 %d 章及之后章节，世界状态回滚到第 %d 章开始前。"
                              % (ch_no, ch_no))
        git_tool.commit(_ROOT, "删除章节：从第%d章起" % ch_no, self.log)
        self.log("info", "已删除第 %d 章及之后章节（世界状态已回滚），可从第 %d 章继续生成。"
                 % (ch_no, ch_no))
        return True

    def delete_chapter_only(self, project, chapter_no):
        """仅删除单个章节：保留其后章节，角色卡按剩余最后章节回退（v0.54）。

        删除的是最后一章时进度回退到该章（可直接重新生成补写）；
        删除中间章节时进度不变，后续章节编号保持不变。
        """
        ch_no = int(chapter_no)
        indices = self.store.list_chapter_indices()
        max_idx = max(indices) if indices else 0
        ch = self.store.load_chapter(ch_no)
        if ch:
            self.store.backup_chapter_draft(ch, "delete")   # 先留旧版草稿
        self.store.delete_chapter(ch_no)
        snap = self.store.snapshot_path(ch_no)
        if os.path.exists(snap):
            try:
                os.remove(snap)
            except OSError:
                pass
        if ch_no >= max_idx:
            state = project.state
            state["next_chapter"] = ch_no
            state["story_complete"] = False
            self.store.save_project(project)
        # v0.54 删除后重建角色卡：按分章状态轨迹回退到剩余最后章节
        remain = self.store.list_chapter_indices()
        self.store.rebuild_world_after_delete(max(remain) if remain else 0)
        self.store.append_log("【删除】已删除第 %d 章及其世界快照，角色卡已回退到剩余最后章节；%s"
                              % (ch_no, "进度回退，可继续生成补写。" if ch_no >= max_idx
                                 else "其后章节保留，编号不变。"))
        git_tool.commit(_ROOT, "删除第%d章" % ch_no, self.log)
        self.log("info", "已删除第 %d 章。%s" % (ch_no, "进度已回退到该章。" if ch_no >= max_idx
                                              else "其后章节保留。"))
        return True

    def edit_chapter(self, chapter):
        """就地编辑已归档章节（标题/正文），编辑前自动备份磁盘上的旧版到草稿箱，并 git 存档。"""
        old = self.store.load_chapter(chapter.index)
        if old:
            self.store.backup_chapter_draft(old, "edit")
        self.store.save_chapter(chapter)
        self.store.append_log("编辑第%d章《%s》。" % (chapter.index, chapter.title))
        git_tool.commit(_ROOT, "第%d章《%s》编辑修改" % (chapter.index, chapter.title), self.log)

    def swap_chapters(self, a, b):
        """交换两章叙事内容（排序），旧版自动备份草稿箱，并 git 存档。返回是否成功。"""
        if not self.store.swap_chapters(a, b):
            return False
        self.store.append_log("【交换】第 %d 章与第 %d 章内容互换（旧版已备份草稿箱）。" % (a, b))
        git_tool.commit(_ROOT, "章节交换：第%d章<->第%d章" % (a, b), self.log)
        return True

    def _match_chapter_plan(self, project, ch_no):
        """返回覆盖第 ch_no 章的写作计划内容；多条重叠时取 start 最大者；无则空串。"""
        plans = [p for p in (project.chapter_plans or [])
                 if isinstance(p, dict)
                 and int(p.get("start", 0) or 0) <= int(ch_no)
                 <= int(p.get("end", 0) or 0)]
        if not plans:
            return ""
        best = max(plans, key=lambda p: int(p.get("start", 0) or 0))
        return str(best.get("note") or "").strip()

    def _collect_scene_cards(self, project, consolidation):
        """v1.21 解析主AI综合校验返回的情景规则卡选择/自做结果，返回注入正文AI的卡列表。

        - consolidation.scene_cards：选中的**已有卡名**——优先从项目可用库
          project.scene_cards 取内容（名字在项目库缺失时降级查全局总库兜底）；
        - consolidation.new_scene_cards：主AI按需**自做的新卡**（[{name, content}]）——
          只存入本项目库（source="ai"），同名已存在则跳过（保留已有卡），新卡一并注入本章。

        v1.34 兼容带「〔分类〕」前缀的卡名：主AI可能把清单里的显示格式（如
        「〔氛围酝酿〕环境奇观渲染描写」）整串填进 scene_cards——匹配时先剥离
        「〔…〕」前缀再查库，避免明明选了卡却因名字带前缀匹配不上而白选（2026-10-19
        全链路实测抓出：reasoning 显示选中 2 张卡、日志却落"未选用"）。
        """

        def _strip_cat(nm):
            s = str(nm or "").strip()
            if s.startswith("〔") and "〕" in s:
                s = s[s.index("〕") + 1:].strip()
            return s

        def _c2nc(c):
            """v1.40 卡 dict → {content, category}：分类优先取 category 字段，
            否则回退解析 content 首行【分类】XXX（拆书卡/导入卡常见格式）。"""
            ct = str(c.get("content") or "").strip()
            cat = str(c.get("category") or "").strip()
            if not cat and ct:
                first = ct.splitlines()[0].strip() if ct else ""
                if first.startswith("【分类】"):
                    cat = first[len("【分类】"):].strip()
            return {"content": ct, "category": cat}

        scene_cards = []
        project_cards = []
        try:
            project_cards = [c for c in (getattr(project, "scene_cards", None) or [])
                             if isinstance(c, dict)]
        except Exception:
            project_cards = []
        try:
            _proj_by_name = {str(c.get("name") or "").strip():
                             _c2nc(c) for c in project_cards}
            _names = [str(x).strip() for x in (consolidation.get("scene_cards") or [])
                      if str(x).strip()]
            if _names:
                _cfg_lib = config.load_config().get("writer_scene_cards") or []
                _lib_by_name = {str(c.get("name") or "").strip():
                                _c2nc(c) for c in _cfg_lib if isinstance(c, dict)}
                for _nm in _names:
                    _base = _strip_cat(_nm)
                    _nc = _proj_by_name.get(_nm) or _proj_by_name.get(_base) or {}
                    if not _nc:
                        _nc = _lib_by_name.get(_nm) or _lib_by_name.get(_base) or {}
                    _ct = _nc.get("content") or ""
                    if _ct:
                        scene_cards.append({"name": _base or _nm, "content": _ct,
                                            "category": _nc.get("category") or ""})
            # 主AI自做的新卡：只进本项目库（source="ai"），同名跳过；新卡一并注入本章
            _new = [x for x in (consolidation.get("new_scene_cards") or [])
                    if isinstance(x, dict)
                    and str(x.get("name") or "").strip()
                    and str(x.get("content") or "").strip()]
            _cur_names = {str(c.get("name") or "").strip() for c in project_cards}
            _added = []
            for _x in _new[:2]:
                _nm = str(_x.get("name") or "").strip()
                _ct = str(_x.get("content") or "").strip()
                if _nm in _cur_names:
                    self.log("info", "主AI自做情景卡「%s」与项目库已有卡重名，跳过（保留已有）。"
                             % _nm)
                    continue
                project.scene_cards.append({"name": _nm, "content": _ct, "source": "ai"})
                _cur_names.add(_nm)
                _added.append(_nm)
                scene_cards.append({"name": _nm, "content": _ct,
                                    "category": str(_x.get("category") or "").strip()})
            if _added:
                try:
                    self.store.save_project(project)
                except Exception:
                    pass
                self.log("info", "主AI自做情景规则卡并存入本项目库（AI 制作）：%s"
                         % "、".join(_added))
        except Exception:
            scene_cards = scene_cards or []
        return scene_cards

    def adapt_project_scene_cards(self, project, cards=None):
        """v1.42 主AI按本项目正文AI基础文风（story_writer_prompt）适配项目库情景卡。

        一次把项目库卡全部交给主AI逐张改写（保持卡名/分类/情景内核不变、只调整写法表述
        契合本项目正文AI基础文风），写回 project.scene_cards 的 content——**只改项目库、
        不动全局总库**。cards=None 时用项目库全部卡（name+content 非空）。
        返回 {"ok": n, "failed": [卡名...]}；失败不阻断，逐卡记录。
        """
        if cards is None:
            cards = [c for c in (getattr(project, "scene_cards", None) or [])
                     if isinstance(c, dict) and str(c.get("name") or "").strip()
                     and str(c.get("content") or "").strip()]
        if not cards:
            self.log("warn", "项目库没有情景卡可适配（先到「情景提示词」页把卡加入本项目）。")
            return {"ok": 0, "failed": []}
        base_style = (getattr(project, "story_writer_prompt", None) or "").strip()
        if not base_style:
            self.log("warn", "尚未设置正文AI角色提示词（文风参考②）——适配以它为基准，先设置再适配。")
            return {"ok": 0, "failed": [str(c.get("name") or "") for c in cards]}
        self.log("info", "主AI按本项目正文文风适配 %d 张项目库情景卡（只改项目库、不动总库）…"
                 % len(cards))
        data = main_ai.adapt_project_scene_cards(project, cards)
        by_name = {}
        for item in (data.get("adapted") or []) if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            nm = str(item.get("name") or "").strip()
            ct = str(item.get("content") or "").strip()
            if nm and ct:
                by_name[nm] = ct
        ok_n, failed = 0, []
        for c in cards:
            nm = str(c.get("name") or "").strip()
            new_ct = by_name.get(nm)
            if new_ct:
                c["content"] = new_ct
                ok_n += 1
            else:
                failed.append(nm)
        try:
            self.store.save_project(project)
        except Exception:
            pass
        if ok_n:
            self.log("info", "已按项目正文文风适配 %d 张情景卡（只改项目库、总库未动）。" % ok_n)
        if failed:
            self.log("warn", "以下 %d 张卡适配无效（主AI未返回）：%s"
                     % (len(failed), "、".join(failed)))
        return {"ok": ok_n, "failed": failed}

    def _ensure_chapter_length(self, project, ch_no, target_chars, title, content, writer):
        """字数硬约束（双向，v1.17 循环重写直到达标）：超出上限或低于下限自动**重新生成**
        （不压缩、不截断任何内容）。

        上下限优先用设置页自设的 chapter_min_chars/chapter_max_chars（>0 生效），
        否则自动取 目标×1.15 / 目标×0.8。每轮重写带字数警示 feedback（当前字数 vs 目标区间），
        writer 接受该 feedback 参数（旧式无参回调自动降级）；连续不达标则循环重写
        直到落在区间内，或达到 LENGTH_RETRY_MAX 轮仍不达标才保留本版（完整内容优先，
        交由审查/用户把关，防死循环）。
        """
        cfg = config.load_config()
        _min_c = int(cfg.get("chapter_min_chars") or 0)
        _max_c = int(cfg.get("chapter_max_chars") or 0)
        if _min_c > 0 and _max_c > 0 and _max_c < _min_c:
            _min_c, _max_c = _max_c, _min_c
        hard_limit = _max_c if _max_c > 0 else int(target_chars * 1.15)
        low_limit = max(300, _min_c) if _min_c > 0 else max(300, int(target_chars * 0.8))
        n = len(content or "")
        if n <= hard_limit and n >= low_limit:
            return title, content
        ntitle, ncontent = title, content
        for _rnd in range(1, LENGTH_RETRY_MAX + 1):
            if n > hard_limit:
                self.log("warn", "本章 %d 字超出上限（%d），第 %d/%d 次自动重写（收紧铺陈，不压缩旧稿）…"
                         % (n, hard_limit, _rnd, LENGTH_RETRY_MAX))
                _fb = ("上版本文字数不符合目标（当前 %d 字 > 上限 %d 字），本次必须控制在 "
                       "%d～%d 字内完成全部剧情：只推进 2-3 个剧情点，每幕约 %d 字，"
                       "写完全章自查总字数，不注水不拖沓；仍超出上限会继续判定失败重写。"
                       % (n, hard_limit, low_limit, hard_limit, int(target_chars / 5)))
            else:
                self.log("warn", "本章 %d 字低于下限（%d），第 %d/%d 次自动重写（充实到 %d～%d 字）…"
                         % (n, low_limit, _rnd, LENGTH_RETRY_MAX, low_limit, hard_limit))
                _fb = ("上版本文字数不符合目标（当前 %d 字 < 下限 %d 字），本次必须控制在 "
                       "%d～%d 字内完成全部剧情：只推进 2-3 个剧情点，每幕约 %d 字，"
                       "写完全章自查总字数，不注水不拖沓；仍低于下限会继续判定失败重写。"
                       % (n, low_limit, low_limit, hard_limit, int(target_chars / 5)))
            try:
                ntitle, ncontent = writer(_fb)
            except TypeError:
                ntitle, ncontent = writer()
            n2 = len(ncontent or "")
            if n2 <= hard_limit and n2 >= low_limit:
                return ntitle, ncontent
            n = n2
        self.log("warn", "循环重写 %d 次后本章仍 %d 字（要求 %d～%d 字），保留本版内容，"
                 "可在审查环节人工把关。" % (LENGTH_RETRY_MAX, n, low_limit, hard_limit))
        return ntitle, ncontent

    def _proofread_once(self, project, chapter, target_chars):
        """④.3 写后校对：正文AI完稿后/主AI审查重写后调用（只改文本，不改剧情）。

        规则开放给用户在设置页编辑；返回本次修改说明 notes 列表；有改动时已更新
        chapter.content；环节失败/返回异常不阻断生成（保留原文继续）。
        """
        cfg = config.load_config()
        if not cfg.get("proofread_enabled", True):
            return []
        self.log("info", "④.3 写后校对：细读本章检查描写逻辑与字词修辞…")
        try:
            # v0.82 意外中断自动重试：LLM 调用失败（限流/超时/坏JSON）自动重跑 3 次，
            # 用户停止立即传播；仍失败才保留原文继续（不阻断本章生成）
            pr = None
            _last_err = None
            for _attempt in range(3):
                try:
                    pr = main_ai.proofread_chapter(
                        project, self.store, chapter,
                        rules=(cfg.get("proofread_rules") or "").strip(),
                        max_tokens=int(target_chars * 4) + 3000)
                    break
                except llm.StopRequested:
                    raise
                except Exception as _e:
                    _last_err = _e
                    if _attempt < 2:
                        self.log("warn", "写后校对调用失败（%s），自动重试第 %d 次…"
                                 % (_e, _attempt + 1))
                        llm._abort_sleep(2.0)
            if pr is None:
                self.log("warn", "写后校对失败（已自动重试 3 次仍失败，保留原文继续）：%s"
                         % _last_err)
                return []
            pr_content = (pr.get("content") or "").strip() if pr else ""
            if pr_content and len(pr_content) > len(chapter.content or "") * 0.3:
                notes = list(pr.get("notes") or [])
                if notes or pr_content != (chapter.content or ""):
                    chapter.content = pr_content
                    # v2.57：AI八股分级报告（命中处数/等级）入库与日志，供阅读时展示
                    hits = pr.get("ai_hits")
                    grade = pr.get("ai_grade")
                    if hits is not None or grade:
                        try:
                            report = {"grade": str(grade or "")[:4],
                                      "hits": int(hits or 0)}
                            chapter.reasoning["deai_report"] = report
                        except (TypeError, ValueError):
                            pass
                    extra = ""
                    if hits is not None or grade:
                        extra = "；AI八股命中 %s 处（%s）" % (
                            hits if hits is not None else "?",
                            "等级：" + str(grade) if grade else "—")
                    self.log("info", "写后校对完成：修改 %d 处%s（%s）"
                             % (len(notes), extra,
                                "；".join(str(x)[:50] for x in notes[:2])
                                if notes else "文本有改动"))
                    return notes
                self.log("info", "写后校对完成：未发现需要修改处。")
            else:
                self.log("warn", "写后校对返回异常（内容为空或过短），保留原文继续。")
        except llm.StopRequested:
            raise   # v0.87 用户停止必须立即传播：StopRequested 是 LLMError 子类，会被
                    # 下面 except Exception 吞掉导致「校准阶段点停止无效、本章照常归档」
        except Exception as e:
            self.log("warn", "写后校对失败（保留原文继续）：%s" % e)
        return []

    def apply_deai(self, project, chapter_no, polished):
        """把去AI味润色稿写回为正式章节正文（标题/角色/卷号不变）。

        写回前自动备份旧版到草稿箱（可恢复），并 git 存档。返回是否成功。
        """
        content = (polished or "").strip()
        if not content:
            return False
        ch = self.store.load_chapter(int(chapter_no))
        if ch is None:
            return False
        old = self.store.load_chapter(int(chapter_no))
        if old:
            self.store.backup_chapter_draft(old, "deai")
        ch.content = content
        self.store.save_chapter(ch)
        self.store.append_log("【去AI味】第%d章《%s》已应用润色稿（原稿备份在草稿箱）。"
                              % (ch.index, ch.title))
        git_tool.commit(_ROOT, "第%d章《%s》去AI味润色" % (ch.index, ch.title), self.log)
        self.log("info", "第 %d 章润色稿已写回（原稿见草稿箱，可恢复）。" % ch.index)
        return True

    def import_chapters(self, project, chapters):
        """把外部正文导入为项目正式章节（从当前进度 next_chapter 开始连续编号），并 git 存档。

        chapters: [{title, content}]；标题为空时自动补"第N章"。
        """
        chapters = [c for c in chapters if (c or {}).get("content", "").strip()]
        if not chapters:
            return 0
        nxt = int(project.state.get("next_chapter", 1))
        vol = int(project.state.get("volume", 1))
        for i, cd in enumerate(chapters):
            ch = Chapter(nxt + i, vol)
            ch.title = str(cd.get("title") or "").strip().lstrip("#* ").strip() \
                or "第%d章" % (nxt + i)
            ch.content = str(cd.get("content") or "").strip()
            ch.status = CHAPTER_STATUS_APPROVED
            self.store.save_chapter(ch)
        project.state["next_chapter"] = nxt + len(chapters)
        project.state["story_complete"] = False
        self.store.save_project(project)
        self.store.append_log("【导入】导入外部正文 %d 章（第 %d-%d 章）。"
                              % (len(chapters), nxt, nxt + len(chapters) - 1))
        git_tool.commit(_ROOT, "导入正文%d章" % len(chapters), self.log)
        self.log("info", "已导入 %d 章（第 %d-%d 章）。" % (len(chapters), nxt, nxt + len(chapters) - 1))
        return len(chapters)

    def delete_chapters_bulk(self, project, indices):
        """批量删除章节（删除前逐章备份到草稿箱，v0.54 起删除后角色卡按剩余最后章节回退）。

        删除后进度 = 现存最大章号 + 1（无现存章节则回到 1），并解除完结态。
        返回实际删除数量。
        """
        idxs = sorted({int(i) for i in indices if int(i) > 0})
        if not idxs:
            return 0
        for i in idxs:
            ch = self.store.load_chapter(i)
            if ch:
                self.store.backup_chapter_draft(ch, "delete")
            self.store.delete_chapter(i)
            snap = self.store.snapshot_path(i)
            if os.path.exists(snap):
                try:
                    os.remove(snap)
                except OSError:
                    pass
        remain = self.store.list_chapter_indices()
        nxt = max(remain) + 1 if remain else 1
        state = project.state
        state["next_chapter"] = nxt
        state["story_complete"] = False
        self.store.save_project(project)
        # v0.54 删除后重建角色卡：按分章状态轨迹回退到剩余最后章节
        self.store.rebuild_world_after_delete(max(remain) if remain else 0)
        self.store.append_log("【删除】批量删除章节：第 %s 章（进度回退到第 %d 章，角色卡已回退）。"
                              % ("、".join(str(i) for i in idxs), nxt))
        git_tool.commit(_ROOT, "批量删除%d章" % len(idxs), self.log)
        self.log("info", "已批量删除 %d 章，进度回退到第 %d 章。" % (len(idxs), nxt))
        return len(idxs)

    # ---------- 全自动模式 ----------
    def auto_run(self, project, stop_check=None, beats_confirm=None):
        """全自动连写：主AI审查通过后自动继续，直至卷目标完成或用户停止。

        v0.63：beats_confirm 参数——生成前剧情点确认关卡回调（生成页开关勾选后，全自动
        连写每章同样弹确认，与「生成下一章」一致；不传则不弹）。
        单章生成遇 API 报错（限流/超时/网络）会自动重试本章，连续失败
        MAX_AUTO_RETRY 次才停止，不需要用户每次手动点继续。
        """
        consec_fail = 0
        while not project.state.get("story_complete"):
            if stop_check and stop_check():
                self.log("info", "已收到停止指令，暂停自动生成。")
                break
            try:
                chapter = self.generate_draft(project, beats_confirm=beats_confirm)
            except llm.StopRequested:
                self.log("info", "已收到停止指令，立即中断生成。")
                break
            except llm.LLMError as e:
                self.log("error", "生成失败：%s" % e)
                consec_fail += 1
                if consec_fail >= MAX_AUTO_RETRY:
                    self.log("error", "连续 %d 次生成失败，自动停止（请检查 API 配置/限流后重新启动）。"
                             % MAX_AUTO_RETRY)
                    break
                self.log("info", "正在自动重试本章（第 %d/%d 次失败）…"
                         % (consec_fail, MAX_AUTO_RETRY))
                continue
            if chapter is None:
                self.log("warn", "本章未生成成功（草稿为空/已完结），自动停止。")
                break
            consec_fail = 0
            # generate_draft 内部已做主AI审查+自动重写（见 ④.5），这里直接取结果；
            # 手动重写/关闭自动审查时无 review，补一次参考审查（不影响归档）。
            review = chapter.reasoning.get("review") or {}
            if not review:
                try:
                    if chapter.index <= 1:
                        target = "开篇第 1 章，立足开局推进主线"
                    else:
                        target = "第 %d 章，延续第 %d 章结尾推进主线" % (
                            chapter.index, chapter.index - 1)
                    review = main_ai.review_chapter(
                        project, self.store, chapter, target,
                        beats=chapter.reasoning.get("beats") or [])
                except llm.StopRequested:
                    raise
                except llm.LLMError:
                    review = {}
            approved = str(review.get("approved")).strip().lower() == "true"
            self.log("info", "审查结论：%s；节奏评价：%s"
                     % ("通过" if approved else ("通过（有保留）"),
                        review.get("pacing", "—")))
            self.finalize_chapter(project, chapter, review)
            # 盖章：已写章节数统计
            self.log("progress", "%d/%d" % (self.written_count(project),
                                            self.total_planned(project)))
        self.log("info", "自动生成结束。")

    # ---------- 工具 ----------
    def _char_name(self, cid):
        card, _ = self.store.load_character(cid)
        return card.name if card else cid

    def _introduce_character(self, project, hint):
        """主AI按情节需要自动建档新角色（只立形象，不预设身世）。

        返回 (card, lib)；LLM 调用失败时记 warn 并返回 None，不阻塞本章。
        v0.98 防重复：先按名字查重，同名角色已存在则复用旧卡（补齐空缺字段），不新建。
        """
        try:
            data = main_ai.generate_character_ai(hint, project, self.store)
            card, lib, created = main_ai.save_generated_character(self.store, data)
            if not created:
                self.log("info", "角色池已有同名角色「%s」（%s），复用旧卡并补齐空缺设定，不重复建档。"
                         % (card.name, card.role))
            return card, lib
        except llm.StopRequested:
            raise
        except (llm.LLMError, ValueError) as e:
            self.log("warn", "按情节需要创建新角色失败：%s（本章继续用现有角色）" % e)
            return None

    def _apply_archive_suggestions(self, archive):
        """主AI建议归档的角色标记为 archived（软归档：不删文件、可恢复、不再默认出场）。"""
        for item in archive or []:
            cid = str((item or {}).get("id") or "").strip()
            if not cid:
                continue
            card, lib = self.store.load_character(cid)
            if card and card.status != CHAR_STATUS_ARCHIVED:
                card.status = CHAR_STATUS_ARCHIVED
                card.version += 1
                self.store.save_character(card, lib)
                self.log("info", "角色 %s 已归档（%s）"
                         % (card.name, (item.get("reason") or "剧情价值已收尾")))

    @staticmethod
    def written_count(project):
        return int(project.state.get("next_chapter", 1)) - 1

    @staticmethod
    def total_planned(project):
        return project.chapter_target() or 0

    def _has_appeared(self, cid):
        for i in self.store.list_chapter_indices():
            ch = self.store.load_chapter(i)
            if ch and ch.status == "approved" and cid in ch.characters:
                return True
        return False

    def _apply_world_updates(self, project, chapter, world):
        for item in (world.get("characters", []) or []):
            cid = item.get("id", "")
            card, lib = self.store.load_character(cid)
            if not card:
                continue
            updates = item.get("card_updates") or {}
            changed = False
            for key, val in updates.items():
                if not hasattr(card, key) or val is None:
                    continue
                # traits 是列表字段：模型可能返回 ["冷酷","缜密"]，逐项转字符串，避免被 str() 整成列表字面量
                if key == "traits":
                    if isinstance(val, list):
                        new_traits = [str(t).strip() for t in val if str(t).strip()]
                        if new_traits != card.traits:
                            card.traits = new_traits
                            changed = True
                    elif str(val).strip():
                        card.traits = [str(val).strip()]
                        changed = True
                elif str(val).strip():
                    setattr(card, key, str(val).strip())
                    changed = True
            status = item.get("status", "unchanged")
            if status in ("dead", "traveling") and card.status != status:
                card.status = status
                changed = True
                self.log("info", "角色 %s 状态变化：%s —— %s"
                         % (card.name, {"dead": "阵亡", "traveling": "外出游历"}.get(status, status),
                            item.get("status_reason", "") or "主AI判定"))
            if changed:
                card.version += 1
                card.updated_chapter = chapter.index
            lib_updates = item.get("library") or {}
            if lib_updates.get("scenario"):
                lib.scenario = str(lib_updates.get("scenario", "")).strip()
            new_events = [e for e in lib_updates.get("events", [])
                          if str(e.get("event", "")).strip()]
            for e in new_events:
                lib.events.append({"chapter": chapter.index,
                                   "event": str(e.get("event", "")),
                                   "impact": str(e.get("impact", "") or "")})
            new_know = [k for k in lib_updates.get("knowledge", [])
                        if str(k.get("info", "")).strip()]
            for k in new_know:
                lib.knowledge.append({"chapter": chapter.index,
                                      "info": str(k.get("info", ""))})
            for s in lib_updates.get("secrets", []) or []:
                s = str(s).strip()
                if s and s not in lib.secrets:
                    lib.secrets.append(s)
            if lib_updates.get("notes"):
                lib.notes = str(lib_updates.get("notes", "")).strip()
            lib.events = lib.events[-80:]
            lib.knowledge = lib.knowledge[-80:]
            # v0.54 分章状态轨迹：战后更新写入「本章完成后」的角色状态，
            # 供删除章节时按轨迹把角色卡回退到对应章节（小说导入成项目的回滚机制通用化：
            # 正常生成的流程同样写入，删除章节后角色卡也会随剩余章节回退/清理）
            if changed or lib_updates.get("scenario") or new_events or new_know:
                card.chapter_states.append({"ch": chapter.index,
                                            "scenario": lib.scenario or "",
                                            "status": card.status})
                card.chapter_states = card.chapter_states[-500:]
            self.store.save_character(card, lib)

    def _apply_foreshadows(self, project, chapter):
        fs = self.store.load_foreshadows()
        ch_no = chapter.index
        cons = chapter.reasoning.get("consolidation", {}) or {}
        want_plant = []
        for f in cons.get("foreshadows", []) or []:
            if isinstance(f, dict) and f.get("f_type") == "plant" and f.get("text"):
                want_plant.append(f)
        # 埋设新伏笔（同文本不重复埋）
        existing_texts = {x.text for x in fs}
        for f in want_plant:
            if f["text"] not in existing_texts:
                fs.append(Foreshadow(f["text"], "plant",
                                     str(f.get("target_character", "") or "")))
                fs[-1].planted_chapter = ch_no
        # 回收：consolidation 中的 payoff 匹配开放伏笔
        payoffs = [str(f.get("text", "")) for f in (cons.get("foreshadows", []) or [])
                   if isinstance(f, dict) and f.get("f_type") == "payoff" and f.get("text")]
        for f in fs:
            if f.status != "open":
                continue
            for pt in payoffs:
                if f.text in pt or pt in f.text:
                    if len(f.text) >= 4 or len(pt) >= 4:
                        f.status = "resolved"
                        f.resolved_chapter = ch_no
                        break
        self.store.save_foreshadows(fs)