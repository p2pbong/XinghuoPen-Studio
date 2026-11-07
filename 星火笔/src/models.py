# -*- coding: utf-8 -*-
"""数据模型：角色卡、信息库、卷规划、章节、伏笔。JSON 可序列化。"""
import re
import time
import uuid

CHAR_STATUS_ACTIVE = "active"
CHAR_STATUS_DEAD = "dead"
CHAR_STATUS_TRAVELING = "traveling"
CHAR_STATUS_ARCHIVED = "archived"   # 软归档：主AI判定已无剧情价值，不删除文件、可恢复
CHAR_STATUS_DISCARDED = "discarded"  # 废弃：删除章节/世界回滚后已不属于当前时间线，
                                     # 移入「废弃角色库」（同样不删文件，可查看原因、可恢复）

CHAPTER_STATUS_DRAFT = "draft"
CHAPTER_STATUS_APPROVED = "approved"


def uid():
    return uuid.uuid4().hex[:12]


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class CharacterCard:
    """角色卡：自我性质的内容（性格、目标、价值观等）。"""

    def __init__(self, name="", role="", card_id=None):
        self.id = card_id or uid()
        self.name = name
        self.role = role          # 身份/职业
        self.age = ""
        self.gender = ""
        self.personality = ""     # 立体性格描述
        self.traits = []          # 特征标签
        self.values = ""          # 价值观与底线
        self.goals = ""           # 目标与欲望
        self.fears = ""           # 恐惧与弱点
        self.speech_style = ""    # 说话风格
        self.backstory = ""       # 背景故事
        self.relationships = ""   # 与其他角色的关系
        self.appearance = ""      # 外貌
        # ---- 酒馆（SillyTavern）Persona 风格字段 ----
        self.description = ""     # 综合描述（外貌+性格+背景+言行特征；推理时优先使用）
        self.scenario = ""        # 当前场景/处境（会随剧情推进更新）
        self.first_mes = ""       # 开场白（角色首次登场的第一句话/动作）
        self.mes_example = ""     # 示例对话（教会模型该角色的说话风格）
        self.system_prompt = ""   # 附加系统提示（扮演该角色时的额外规则）
        self.post_history_instructions = ""   # 剧情后置提示（每轮后注入的额外指示）
        self.creator_notes = ""   # 作者备注/设计思路（酒馆 spec_v2；对模型不可见）
        self.tags = []            # 角色标签（酒馆 spec_v2：如 主角/配角/反派 等分类标签）
        self.character_version = ""   # 角色卡版本（酒馆 spec_v2：如 "main"/"1.0"）
        self.status = CHAR_STATUS_ACTIVE
        self.created_by = "user"  # user | ai
        self.category = ""        # 角色分类（""=未分类；如：主要角色/配角/NPC/反派…，AI 自动分类或手动设置）
        self.version = 1
        self.updated_chapter = 0
        self.discarded_reason = ""   # v1.79 废弃原因（删除章节/世界回滚时写入；恢复在籍即清空）
        self.discarded_chapter = 0   # v1.79 废弃时的章节号（回滚目标章 / 剩余最后章）
        self.chapter_states = []  # v0.54 分章状态轨迹：[{ch, scenario, status}]
                                   # （小说导入成项目写入；删除章节时按它把角色卡回退到对应章节）
        self.created_at = now()

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "role": self.role,
            "age": self.age, "gender": self.gender,
            "personality": self.personality, "traits": list(self.traits),
            "values": self.values, "goals": self.goals, "fears": self.fears,
            "speech_style": self.speech_style, "backstory": self.backstory,
            "relationships": self.relationships, "appearance": self.appearance,
            "description": self.description, "scenario": self.scenario,
            "first_mes": self.first_mes, "mes_example": self.mes_example,
            "system_prompt": self.system_prompt,
            "post_history_instructions": self.post_history_instructions,
            "creator_notes": self.creator_notes,
            "tags": list(self.tags),
            "character_version": self.character_version,
            "status": self.status, "created_by": self.created_by,
            "category": self.category,
            "version": self.version, "updated_chapter": self.updated_chapter,
            "discarded_reason": self.discarded_reason,
            "discarded_chapter": int(self.discarded_chapter or 0),
            "chapter_states": [{"ch": int(s.get("ch", 0) or 0),
                                "scenario": str(s.get("scenario", "") or ""),
                                "status": str(s.get("status", "") or "active")}
                               for s in (self.chapter_states or [])
                               if isinstance(s, dict)],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d):
        card = cls(card_id=d.get("id"))
        card.name = d.get("name", "") or ""
        card.role = d.get("role", "") or ""
        card.age = d.get("age", "") or ""
        card.gender = d.get("gender", "") or ""
        card.personality = d.get("personality", "") or ""
        # traits 必须是列表；若被写成字符串（旧数据/模型污染）按逗号/顿号拆开，
        # 避免 list("冷酷缜密") 拆成单字
        raw_traits = d.get("traits") or []
        if isinstance(raw_traits, str):
            raw_traits = re.split(r"[，,、;；\s]+", raw_traits)
        card.traits = [str(t).strip() for t in raw_traits if str(t).strip()]
        card.values = d.get("values", "") or ""
        card.goals = d.get("goals", "") or ""
        card.fears = d.get("fears", "") or ""
        card.speech_style = d.get("speech_style", "") or ""
        card.backstory = d.get("backstory", "") or ""
        card.relationships = d.get("relationships", "") or ""
        card.appearance = d.get("appearance", "") or ""
        card.description = d.get("description", "") or ""
        card.scenario = d.get("scenario", "") or ""
        card.first_mes = d.get("first_mes", "") or ""
        card.mes_example = d.get("mes_example", "") or ""
        card.system_prompt = d.get("system_prompt", "") or ""
        card.post_history_instructions = d.get("post_history_instructions", "") or ""
        card.creator_notes = d.get("creator_notes", "") or ""
        _raw_tags = d.get("tags") or []
        if isinstance(_raw_tags, str):
            _raw_tags = re.split(r"[，,、;；\s]+", _raw_tags)
        card.tags = [str(t).strip() for t in _raw_tags if str(t).strip()]
        card.character_version = d.get("character_version", "") or ""
        card.status = d.get("status", CHAR_STATUS_ACTIVE)
        card.created_by = d.get("created_by", "user")
        card.category = d.get("category", "") or ""
        card.version = d.get("version", 1) or 1
        card.updated_chapter = d.get("updated_chapter", 0) or 0
        card.discarded_reason = d.get("discarded_reason", "") or ""
        try:
            card.discarded_chapter = int(d.get("discarded_chapter", 0) or 0)
        except (TypeError, ValueError):
            card.discarded_chapter = 0
        _cs = d.get("chapter_states") or []
        card.chapter_states = [
            {"ch": int(s.get("ch", 0) or 0),
             "scenario": str(s.get("scenario", "") or ""),
             "status": str(s.get("status", "") or "active")}
            for s in _cs if isinstance(s, dict)]
        card.created_at = d.get("created_at", "") or ""
        return card


class InfoLibrary:
    """信息库：角色当前处境、经历的事件、已知信息等**外在影响判断**的内容。

    原则：角色卡只放「这个角色是怎么样」（人设等自我性质），
    一切外在信息（当前场景/处境、经历、情报、隐秘）都进信息库。
    """

    def __init__(self, character_id=""):
        self.character_id = character_id
        self.scenario = ""    # 当前场景/处境（会随剧情推进更新）
        self.events = []      # [{chapter, event, impact}]
        self.knowledge = []   # [{chapter, info}]
        self.secrets = []     # [str]
        self.notes = ""       # 其他备注

    def to_dict(self):
        return {
            "character_id": self.character_id,
            "scenario": self.scenario,
            "events": list(self.events),
            "knowledge": list(self.knowledge),
            "secrets": list(self.secrets),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d):
        lib = cls(d.get("character_id", ""))
        lib.scenario = d.get("scenario", "") or ""
        # events/knowledge 元素可能是字符串（模型输出污染）→ 丢弃非 dict 项，避免下游 .get() 崩溃
        lib.events = [dict(e) for e in (d.get("events") or []) if isinstance(e, dict)]
        lib.knowledge = [dict(k) for k in (d.get("knowledge") or []) if isinstance(k, dict)]
        lib.secrets = [str(s) for s in (d.get("secrets") or []) if str(s).strip()]
        lib.notes = d.get("notes", "") or ""
        return lib


class VolumePlan:
    """卷规划：由用户把控的大方向。"""

    def __init__(self, index=1):
        self.index = index
        self.title = ""
        self.total_chapters = 0
        self.main_events = []   # [str]
        self.ending = ""        # 本卷如何结束
        self.next_hook = ""     # 承接下一卷的内容
        self.notes = ""         # 其他约束/补充

    def to_dict(self):
        return {
            "index": self.index, "title": self.title,
            "total_chapters": self.total_chapters,
            "main_events": list(self.main_events),
            "ending": self.ending, "next_hook": self.next_hook,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d):
        v = cls(int(d.get("index", 1)))
        v.title = d.get("title", "")
        v.total_chapters = int(d.get("total_chapters", 0) or 0)
        v.main_events = list(d.get("main_events", []))
        v.ending = d.get("ending", "")
        v.next_hook = d.get("next_hook", "")
        v.notes = d.get("notes", "")
        return v


class Chapter:
    def __init__(self, index=1, volume=1):
        self.index = index
        self.volume = volume
        self.title = ""
        self.characters = []   # [char_id]
        self.scene = ""        # 本章场景焦点
        self.reasoning = {}    # 推理过程存档
        self.content = ""
        self.brief = ""        # 章节一句话摘要（供压缩上下文用）
        self.foreshadows = []  # 本章相关伏笔
        self.status = CHAPTER_STATUS_DRAFT
        self.created_at = now()
        self.updated_at = now()

    def to_dict(self):
        return {
            "index": self.index, "volume": self.volume, "title": self.title,
            "characters": list(self.characters), "scene": self.scene,
            "reasoning": self.reasoning, "content": self.content,
            "brief": self.brief, "foreshadows": list(self.foreshadows),
            "status": self.status,
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d):
        ch = cls(int(d.get("index", 1) or 1), int(d.get("volume", 1) or 1))
        ch.title = d.get("title", "") or ""
        ch.characters = [c for c in (d.get("characters") or []) if c]
        ch.scene = d.get("scene", "") or ""
        ch.reasoning = d.get("reasoning", {}) or {}
        ch.content = d.get("content", "") or ""
        ch.brief = d.get("brief", "") or ""
        ch.foreshadows = [f for f in (d.get("foreshadows") or []) if f]
        ch.status = d.get("status", CHAPTER_STATUS_DRAFT)
        ch.created_at = d.get("created_at", "") or ""
        ch.updated_at = d.get("updated_at", "") or ""
        return ch


class Foreshadow:
    """伏笔：埋设/回收记录。"""

    def __init__(self, text="", f_type="plant", target_char=""):
        self.id = uid()
        self.text = text
        self.f_type = f_type           # plant | payoff | echo
        self.target_char = target_char # 依托/回收角色 id
        self.status = "open"           # open | resolved
        self.planted_chapter = 0
        self.resolved_chapter = 0
        self.planted_note = ""  # v1.92 埋设要点：当时怎么埋的（借什么物件/场景/动作/台词露出）

    def to_dict(self):
        return {
            "id": self.id, "text": self.text, "f_type": self.f_type,
            "target_char": self.target_char, "status": self.status,
            "planted_chapter": self.planted_chapter,
            "resolved_chapter": self.resolved_chapter,
            "planted_note": self.planted_note,
        }

    @classmethod
    def from_dict(cls, d):
        f = cls(d.get("text", ""), d.get("f_type", "plant"), d.get("target_char", ""))
        f.id = d.get("id", f.id)
        f.status = d.get("status", "open")
        f.planted_chapter = d.get("planted_chapter", 0)
        f.resolved_chapter = d.get("resolved_chapter", 0)
        f.planted_note = d.get("planted_note", "")  # v1.92 兼容旧台账
        return f


class NovelProject:
    """一个小说项目：故事设定（自然语言）+ 本卷目标章数 + 全局状态。

    主线依据以 story_brief（用户用自然语言写给总AI的故事描述）为准；
    volume_target 为当前卷目标章数（0 = 由主AI把控节奏，无硬性上限）。
    opening/volumes 为旧版结构化字段，仅用于兼容旧项目与回退展示。
    """

    def __init__(self, dir_name="", title="无题"):
        self.dir_name = dir_name
        self.title = title
        self.opening = ""          # 旧版：开局设定（兼容）
        self.volumes = []          # 旧版：结构化卷规划（兼容）
        self.story_brief = ""      # 故事描述（剧情：开局/主线/结尾方向/下一卷）
        self.story_world = ""      # 世界观（背景/势力/地理/力量体系/大概念，与剧情分离）
        self.story_rules = ""      # 特殊规则/其他设定（禁忌/金手指/叙事偏好等杂项）
        self.story_style = ""      # 主AI风格设定（文风/基调/视角/节奏偏好等，自然语言描述）
        self.story_writer_prompt = ""  # 正文AI角色提示词（"你是一个擅长xx的xx…"式，只注入正文AI）
        self.story_main_prompt = ""    # 主AI全局提示词（"你是一个…"式或自然语言，只注入主AI，控制剧情把控）
        self.story_style_ref = ""  # 参考文风样本（用户粘贴的文风示例文本，仅注入正文AI，主AI不读）
        self.story_style_note = ""  # 风格要点（AI 从文风样本/前文归纳的可执行要点，写作与校对逐条体现）
        self.story_title_rules = ""  # v1.88 章节标题命名规则（用户自定义，最高优先；空=内置通用规则）
        self.story_tech_source = ""  # 写作技巧库·素材（用户粘贴的爆款章节片段，供 AI 拆解技巧）
        self.story_techniques = ""  # 写作技巧库（AI 从爆款素材拆解的可执行技巧清单，写作/审查参考运用）
        self.story_summary = ""    # 主AI管理笔记（剧情压缩卷，写作AI可读）
        self.story_knowledge = ""  # 主AI知识库（联网知识/重要伏笔/设定备忘等，仅主AI读，写作AI不读）
        self.story_characters = []  # 主AI笔记·重要角色档案：[{name, info}]（当前剧情前线角色动向，决断候选池来源）
        self.story_ideas = []      # 主AI笔记·后续剧情灵感：[str]（待展开方向/回归时机/伏笔引爆点等）
        self.story_break_style = ""  # v0.55 拆书风格名：选中的拆书风格（主AI读其「设计技法学习文本」，学剧情推动/伏笔设计，不抄情节）
        self.scene_cards_active = []  # v1.18 本项目启用的正文AI情景规则卡名列表（旧版：从全局卡库勾选；v1.21 起由 scene_cards 迁移而来）
        # v1.21 项目级主AI可用情景规则卡库（「当前主AI可选情景提示词卡」，与全局总库独立）：
        # [{name, content, source}]，source="user"（用户提供/从总库加入）| "ai"（主AI按需自做，
        # 只存本项目库；用户可在情景提示词页手动放入总库）。主AI每章从这里按正文类型选卡，
        # 无匹配时可自做一张（source="ai"）。
        self.scene_cards = []
        self.chapter_plans = []    # 章节写作计划：[{start, end, note}]（第 start~end 章自动生效的写作指示，用户预置）
        self.lore_entries = []     # 设定锚点（项目 Lorebook）：[{id, title, keys, content, always}]
                                   # always=True 常驻：每章必注入主AI与正文AI；否则关键词 keys 命中剧情文本时注入
                                   # （保证长篇里重要设定不被压缩笔记遗忘）
        self.volume_target = 0     # 本卷目标章数（0 = 由主AI把控）
        self.state = {
            "volume": 1,           # 当前卷
            "next_chapter": 1,     # 下一个待生成章节号（全书连续计数）
            "volume_override": False,
            "story_complete": False,
        }
        self.created_at = now()
        self.updated_at = now()

    def current_volume(self):
        if self.volumes:
            idx = max(0, min(self.state.get("volume", 1), len(self.volumes)) - 1)
            return self.volumes[idx]
        return None

    def chapter_target(self):
        """本卷目标章数：优先 volume_target，其次旧版 volumes。0 表示无硬性上限。"""
        if int(self.volume_target or 0) > 0:
            return int(self.volume_target)
        vol = self.current_volume()
        if vol and vol.total_chapters:
            return int(vol.total_chapters)
        return 0

    def written_chapters(self):
        return max(0, int(self.state.get("next_chapter", 1)) - 1)

    def current_volume_chapter_count(self):
        return min(self.written_chapters(), self.chapter_target()) \
            if self.chapter_target() else self.written_chapters()

    def volume_done(self):
        target = self.chapter_target()
        if target > 0:
            return self.written_chapters() >= target
        return False

    def to_dict(self):
        return {
            "title": self.title, "opening": self.opening,
            "volumes": [v.to_dict() for v in self.volumes],
            "story_brief": self.story_brief,
            "story_world": self.story_world,
            "story_rules": self.story_rules,
            "story_style": self.story_style,
            "story_writer_prompt": self.story_writer_prompt,
            "story_main_prompt": self.story_main_prompt,
            "story_style_ref": self.story_style_ref,
            "story_style_note": self.story_style_note,
            "story_title_rules": self.story_title_rules,  # v1.88 章节标题命名规则（用户自定义，最高优先）
            "story_tech_source": self.story_tech_source,
            "story_techniques": self.story_techniques,
            "story_summary": self.story_summary,
            "story_knowledge": self.story_knowledge,
            "story_characters": [dict(x) for x in self.story_characters],
            "story_ideas": [str(x) for x in self.story_ideas],
            "story_break_style": self.story_break_style,
            "scene_cards": [{"name": str(x.get("name") or "").strip(),
                             "content": str(x.get("content") or "").strip(),
                             "source": ("ai" if str(x.get("source") or "").strip() == "ai"
                                        else "user"),
                             "category": str(x.get("category") or "").strip()}
                            for x in self.scene_cards if isinstance(x, dict)
                            and str(x.get("name") or "").strip()
                            and str(x.get("content") or "").strip()],
            # v1.21 兼容导出：scene_cards_active = 项目库卡名（旧读端/旧版只认卡名列表）
            "scene_cards_active": [str(x.get("name") or "").strip()
                                   for x in self.scene_cards if isinstance(x, dict)
                                   and str(x.get("name") or "").strip()],
            "chapter_plans": [{"start": int(x.get("start", 0) or 0),
                               "end": int(x.get("end", 0) or 0),
                               "note": str(x.get("note", "") or "")}
                              for x in self.chapter_plans],
            "lore_entries": [{"id": str(x.get("id", "") or ""),
                              "title": str(x.get("title", "") or ""),
                              "keys": [str(k).strip() for k in (x.get("keys") or [])
                                       if str(k).strip()],
                              "content": str(x.get("content", "") or ""),
                              "always": bool(x.get("always", False))}
                             for x in self.lore_entries
                             if isinstance(x, dict)
                             and str(x.get("content", "") or "").strip()],
            "volume_target": int(self.volume_target or 0),
            "state": dict(self.state),
            "created_at": self.created_at, "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d, dir_name=""):
        p = cls(dir_name, d.get("title", "无题"))
        p.opening = d.get("opening", "")
        p.volumes = [VolumePlan.from_dict(v) for v in d.get("volumes", [])]
        p.story_brief = d.get("story_brief", "")
        p.story_world = d.get("story_world", "")
        p.story_rules = d.get("story_rules", "")
        p.story_style = d.get("story_style", "")
        p.story_writer_prompt = d.get("story_writer_prompt", "")
        p.story_main_prompt = d.get("story_main_prompt", "")
        p.story_style_ref = d.get("story_style_ref", "")
        p.story_style_note = d.get("story_style_note", "")
        p.story_title_rules = d.get("story_title_rules", "")  # v1.88 章节标题命名规则（空=内置通用规则）
        p.story_tech_source = d.get("story_tech_source", "")
        p.story_techniques = d.get("story_techniques", "")
        p.story_summary = d.get("story_summary", "")
        p.story_knowledge = d.get("story_knowledge", "")
        _kc = d.get("story_characters") or []
        p.story_characters = [
            {"name": str(x.get("name", "")), "info": str(x.get("info", ""))}
            for x in _kc if isinstance(x, dict)]
        _id = d.get("story_ideas") or []
        p.story_ideas = [str(x).strip() for x in _id if str(x).strip()]
        p.story_break_style = d.get("story_break_style", "")
        # v1.21 项目级主AI可用情景卡库：新字段 scene_cards（[{name,content,source}]）优先；
        # 旧项目只有 scene_cards_active（全局总库卡名列表）→ 从全局总库复制卡内容迁移
        # （source="user"，与 v1.18 勾选语义一致：这些卡视为用户提供）。
        _sc_d = d.get("scene_cards") or []
        _sc_ok = [x for x in _sc_d if isinstance(x, dict)
                  and str(x.get("name") or "").strip()
                  and str(x.get("content") or "").strip()]
        if _sc_ok:
            p.scene_cards = [{"name": str(x.get("name") or "").strip(),
                              "content": str(x.get("content") or "").strip(),
                              "source": ("ai" if str(x.get("source") or "").strip() == "ai"
                                         else "user"),
                              "category": str(x.get("category") or "").strip()}
                             for x in _sc_ok]
        else:
            _sca_names = [str(x).strip() for x in (d.get("scene_cards_active") or [])
                          if str(x).strip()]
            if _sca_names:
                try:
                    import config as _cfg_mdl
                    _all_sc = _cfg_mdl.load_config().get("writer_scene_cards") or []
                    _by_name = {str(c.get("name") or "").strip(): str(c.get("content") or "").strip()
                                for c in _all_sc if isinstance(c, dict)}
                    p.scene_cards = [{"name": nm, "content": _by_name.get(nm, ""),
                                      "source": "user"}
                                     for nm in _sca_names
                                     if _by_name.get(nm, "").strip()]
                except Exception:
                    p.scene_cards = []
        p.scene_cards_active = [str(x.get("name") or "").strip()
                                for x in p.scene_cards if isinstance(x, dict)]
        _pl = d.get("chapter_plans") or []
        p.chapter_plans = []
        for x in _pl:
            if not isinstance(x, dict):
                continue
            s = int(x.get("start", 0) or 0)
            if s <= 0:
                continue
            e = int(x.get("end", 0) or 0)
            if e < s:
                e = s
            p.chapter_plans.append({"start": s, "end": e,
                                    "note": str(x.get("note", "") or "")})
        _lo = d.get("lore_entries") or []
        p.lore_entries = []
        for x in _lo:
            if not isinstance(x, dict):
                continue
            content = str(x.get("content") or "").strip()
            if not content:
                continue
            p.lore_entries.append({
                "id": str(x.get("id") or "") or uid(),
                "title": str(x.get("title") or "").strip(),
                "keys": [str(k).strip() for k in (x.get("keys") or [])
                         if str(k).strip()],
                "content": content,
                "always": bool(x.get("always", False)),
            })
        p.volume_target = int(d.get("volume_target", 0) or 0)
        st = d.get("state") or {}
        p.state.update(st if isinstance(st, dict) else {})
        p.created_at = d.get("created_at", "") or ""
        p.updated_at = d.get("updated_at", "") or ""
        return p