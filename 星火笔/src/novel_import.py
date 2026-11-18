# -*- coding: utf-8 -*-
"""小说导入成项目（v0.55 双端：PC/安卓复用）：把一本 txt 小说「还原」成一个星火笔项目。

核心思路（应对超长小说 + 维系整体性 + 还原后可正常续写）：
  ① 解析：分卷分章，保留每章**完整正文**（book_break.parse_novel_full）；
  ② 拆书：复用 book_break 四阶段管线（L1 骨架 → L2 逐卷细纲 → L3 汇总），
     取回中间结果（骨架/卷细纲/标题流摘要）——拆书风格（learning 设计技法）保存进风格库
     并挂到项目 story_break_style，主AI自动学习「怎么推动剧情/设计伏笔」，不抄情节；
  ③ 设定合成：由骨架+细纲+拆书文档+文风样本合成 剧情/世界观/特殊规则/文风描述/
     风格要点/设定锚点/伏笔池/管理笔记/重要角色档案；
  ④ 逐块人物抽取：每块（按拆书 token 预算切分）让 AI 报「新角色 + 分章状态 + 状态转变」，
     得到全书角色名册；随后**全名匹配**确定每章出场角色（无需逐章调 LLM）；
  ⑤ 角色卡生成：出场最多的角色由 LLM 批量立卡（人设/目标/说话风格/关系…），
     其余配角建轻量卡；每张卡写入「分章状态轨迹 chapter_states」；
  ⑥ 管理笔记：按卷/块梳理剧情推进与人物动向（story_summary），从事件细纲生成章节写作计划；
  ⑦ 落库：项目设定/角色卡（含轨迹与信息库）/章节（原样 approved 入库）/伏笔台账；
  ⑧ 回滚：删除章节后按 chapter_states 轨迹把角色卡回退到剩余最后章节
     （storage.rebuild_world_after_delete；正常生成的流程也会在战后更新时写入轨迹，通用）。

v0.55 断点续传：run 传入 job_dir 时，拆书/设定合成/逐块人物/角色卡各环节结果即时落盘；
API 出错、用户停止或软件退出后，对同一文本+同一设置再启动会自动跳过已完成环节，
不需要整本重来。完成/放弃时由调用方决定删不删 job 目录。
"""
import json
import os

import book_break
import llm
import main_ai
import storage
from models import (CHAPTER_STATUS_APPROVED, CharacterCard, Chapter,
                    Foreshadow, InfoLibrary, uid)

DETAIL_CARDS_MAX = 60   # LLM 详立卡的角色数上限（按出场频率取前 N）
BATCH_CARDS = 10        # 每次批量立卡的角色数
LORE_MAX = 40           # 设定锚点上限
STYLE_REF_MAX = 3000    # 参考文风样本总长上限
SUMMARY_MAX = 2000      # 管理笔记上限
CARD_SAMPLE_CHARS = 300  # 每角色立卡时单章样本字数


# ---------- 文本样本 ----------
def _samples(parsed, cap=STYLE_REF_MAX):
    """取全书代表性文风样本：首章开头 + 1/3、2/3 处、末章开头。"""
    vols = parsed["volumes"] or []
    chs = [c for v in vols for c in (v.get("chapters") or [])]
    if not chs:
        return ""
    picks = []
    for i in (0, len(chs) // 3, len(chs) * 2 // 3, len(chs) - 1):
        if 0 <= i < len(chs) and chs[i] not in picks:
            picks.append(chs[i])
    out = []
    for c in picks:
        head = (c.get("content") or "").strip()[:400]
        if head:
            out.append("（%s）\n%s" % (c.get("title") or "第%d章" % c.get("no", 0), head))
    return "\n\n".join(out)[:cap]


def _chunks(parsed, settings):
    """按「生效的每部分 token」把全书切成若干「块」（与拆书管线同一套切分，保证体量可控）。

    v0.58：高级模式开启重叠（overlap_token）时，相邻块重叠若干章——人物抽取覆盖部分边界，
    防止正好卡在状态转变处的角色被漏掉（状态按章去重，重叠不产生重复）。
    v0.59：智能模式下与拆书管线一致，按模型上下文×档位自动定每部分章数（effective_token）。
    """
    per_c = book_break.chapters_per_part(
        dict(settings, token_per_part=book_break.effective_token(settings)))
    ovl_c = min(book_break.overlap_chapters(settings), per_c - 1)
    step = max(1, per_c - ovl_c)
    chunks = []
    for v in (parsed["volumes"] or []):
        chs = v.get("chapters") or []
        for s in range(0, len(chs), step):
            chunks.append({"vol_no": v.get("no", 1), "vol_title": v.get("title", ""),
                           "chapters": chs[s:s + per_c], "part": len(chunks)})
    return chunks


def _chunk_payload(c, known_names):
    return {
        "vol_no": c["vol_no"], "vol_title": c["vol_title"],
        "known": sorted(known_names),
        "chapters": [{"no": ch.get("no", 0), "title": ch.get("title", ""),
                      "head": (ch.get("content") or "")[:400]}
                     for ch in c["chapters"]],
    }


# ---------- LLM 环节（mock 友好：测试只替换这三个函数） ----------
def synthesize_settings(payload, profile=None, user_prompt=""):
    """设定合成：骨架+卷细纲+拆书文档+文风样本 → 项目设定 JSON。"""
    sys = ("你是一位资深小说编辑兼项目架构师。现在要把一本小说「还原」成一个 AI 写作项目的"
           "设定。基于给定的拆书骨架、逐卷细纲、拆书文档与文风样本，输出 JSON：\n"
           "{\n"
           " \"brief\": \"剧情发展（开局/主线/关键事件/结尾方向），250-500字，自然语言分段\";\n"
           " \"world\": \"世界观（时代背景/地理/势力格局/力量体系/种族文明），200-400字\";\n"
           " \"rules\": \"特殊规则/其他设定（金手指/禁忌/叙事偏好等），100-200字\";\n"
           " \"style\": \"文风描述（基调/视角/节奏/语言风格），80-150字\";\n"
           " \"style_note\": [\"可执行风格要点（每条≤30字，如：短句推进动作先行）\", ...3-6条];\n"
           " \"lore\": [{\"title\": \"设定名\", \"content\": \"该设定要点30-80字\"}], 最多40条，"
           "覆盖重要地点/势力/组织/力量规则/关键物品等硬性设定;\n"
           " \"foreshadows\": [{\"text\": \"伏笔描述\", \"chapter\": 最早出现章号, "
           "\"type\": \"日常/物件/对话/事件/设定\"}];\n"
           " \"summary\": \"主AI管理笔记（全书剧情压缩，≤1500字）\";\n"
           " \"key_characters\": [{\"name\": \"角色名\", \"info\": \"定位与当前动向20-40字\"}]\n"
           "}\n"
           "只写小说里实际出现的信息，不臆造、不照抄大段原文。")
    user = json.dumps(payload, ensure_ascii=False)
    if user_prompt:
        user += "\n\n【用户指定的大方向与小说整体规划（导入前填写的小说剧情设计/方向/主题/未完成部分等信息；设定合成时优先参考并体现，防止因情节缺失被带偏、跑题）】\n%s" % user_prompt
    data = llm.chat_json(sys, user, tag="import_settings", role="decide", profile=profile,
                         think_role="import")
    return data if isinstance(data, dict) else {}


def analyze_chunk_people(payload, profile=None, user_prompt=""):
    """逐块人物抽取：一「块」连续章节 → 新角色 + 分章状态 + 状态转变。"""
    sys = ("你是小说拆书师。下面是某部长篇小说一「块」（连续若干章）的章节标题与每章开头节选，"
           "以及当前已知的角色名册。请输出 JSON：\n"
           "{\n"
           " \"new_chars\": [{\"name\": \"角色名\", \"role\": \"身份/定位(≤10字)\", "
           "\"first_ch\": 首次出场章号, \"persona\": \"读者印象/人设关键词(15-30字)\"}]"
           " —— 只列本块**新出现**、不在已知名册里的角色（含重要配角）；\n"
           " \"states\": [{\"ch\": 章号, \"char\": \"角色名\", \"scenario\": \"该角色此刻处境(10-30字)\", "
           "\"status\": \"active/dead/traveling\"}] —— 给本块**主要角色**的处境（每角色一条，"
           "建议取块末章号）；\n"
           " \"transitions\": [{\"ch\": 章号, \"char\": \"角色名\", \"status\": \"dead/traveling/active\", "
           "\"reason\": \"原因(10-20字)\"}] —— 本块内角色**状态发生转变**（如死亡/离场）的章节\n"
           "}\n"
           "角色名要与原文一致（全名，不含称号前缀）；状态/处境未知的角色不列入 states。")
    user = json.dumps(payload, ensure_ascii=False)
    if user_prompt:
        user += "\n\n【用户指定的大方向与小说整体规划（导入前填写的小说剧情设计/方向/主题/未完成部分等；本块人物抽取时优先参考，防止因情节缺失被带偏、跑题）】\n%s" % user_prompt
    data = llm.chat_json(sys, user, tag="import_chunk", role="decide", profile=profile,
                         think_role="import")
    return data if isinstance(data, dict) else {}


def build_character_cards(batch, samples, profile=None, user_prompt=""):
    """批量立角色卡：一次给 BATCH_CARDS 个角色 + 各自的出场样本 → 角色卡 JSON 数组。"""
    sys = ("你是小说人设师。根据给定角色的出场文本样本，为每个角色建立完整角色卡，输出 JSON 数组：\n"
           "[{\"name\": \"角色名\", \"role\": \"身份/职业\", \"age\": \"\", \"gender\": \"\",\n"
           "  \"personality\": \"立体性格40-80字\", \"traits\": [\"特征标签3-5个\"],\n"
           "  \"values\": \"价值观/底线\", \"goals\": \"目标/欲望\", \"fears\": \"恐惧/弱点\",\n"
           "  \"speech_style\": \"说话风格（含口头禅示例）\", \"backstory\": \"背景故事\",\n"
           "  \"relationships\": \"与其他角色的关系\", \"appearance\": \"外貌\",\n"
           "  \"description\": \"综合描述80-150字\",\n"
           "  \"first_mes\": \"开场白：角色首次登场的第一句话/动作\",\n"
           "  \"mes_example\": \"示例对话2-3句\", \"scenario\": \"当前处境\"}]\n"
           "只依据样本里实际出现的事实，不臆造；样本不足的字段留空。")
    user = json.dumps({"characters": batch, "samples": samples}, ensure_ascii=False)
    if user_prompt:
        user += "\n\n【用户指定的大方向与小说整体规划（导入前填写的小说剧情设计/方向/主题/未完成部分等；立卡时优先参考，防止因情节缺失被带偏、跑题）】\n%s" % user_prompt
    data = llm.chat_json(sys, user, tag="import_cards", role="decide", profile=profile,
                         think_role="import")
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict) and isinstance(data.get("characters"), list):
        return [d for d in data["characters"] if isinstance(d, dict)]
    return []


def synthesize_summary(payload, profile=None, user_prompt=""):
    """主AI管理笔记：按卷/块梳理剧情推进与人物动向（v0.55 导入内容补全）。"""
    sys = ("你是资深小说编辑。下面是某部长篇小说的【卷事件细纲】与【分块人物动向】，"
           "请按卷/时间段梳理成主AI管理笔记（剧情压缩卷）：主线推进脉络 + 关键转折 + "
           "各时间段主要人物的动向/状态变化（按章节梳理人物）。输出 JSON：\n"
           "{\"summary\": \"≤2000字的剧情·人物梳理（按卷分节，体现人物随章节的动向与处境变化）\",\n"
           " \"ideas\": [\"后续可展开方向/伏笔引爆点/角色回归时机 3-6条\"]}\n"
           "只写实际出现的信息，不臆造。")
    user = json.dumps(payload, ensure_ascii=False)
    if user_prompt:
        user += "\n\n【用户指定的大方向与小说整体规划（导入前填写的小说剧情设计/方向/主题/未完成部分等；梳理时优先参考，防止因情节缺失被带偏、跑题）】\n%s" % user_prompt
    data = llm.chat_json(sys, user, tag="import_summary", role="decide", profile=profile,
                         think_role="import")
    return data if isinstance(data, dict) else {}


# ---------- 结果吸收 ----------
def _absorb_chunk(r, roster, chunk_states, transitions):
    """把一块的人物抽取结果并入名册/状态/转变集合。"""
    for nc in (r.get("new_chars") or []):
        if not isinstance(nc, dict):
            continue
        nm = str(nc.get("name") or "").strip()
        if not nm:
            continue
        meta = roster.setdefault(nm, {"role": "", "first_ch": 1, "persona": "", "freq": 0})
        if not meta["role"]:
            meta["role"] = str(nc.get("role") or "")
        if not meta["persona"]:
            meta["persona"] = str(nc.get("persona") or "")
        try:
            fc = max(1, int(nc.get("first_ch") or 1))
        except (TypeError, ValueError):
            fc = 1
        meta["first_ch"] = min(meta.get("first_ch", 1), fc)
    for s in (r.get("states") or []):
        if isinstance(s, dict) and str(s.get("char") or "").strip():
            chunk_states.append({"ch": int(s.get("ch") or 0),
                                 "char": str(s["char"]).strip(),
                                 "scenario": str(s.get("scenario") or ""),
                                 "status": str(s.get("status") or "active")})
    for tr in (r.get("transitions") or []):
        if isinstance(tr, dict) and str(tr.get("char") or "").strip():
            transitions.append({"ch": int(tr.get("ch") or 0),
                                "char": str(tr["char"]).strip(),
                                "status": str(tr.get("status") or "active"),
                                "reason": str(tr.get("reason") or "")})


def _assemble_trails(chunk_states, transitions, roster, vols, cards):
    """合并状态/转变 → 每角色按章排序的分章状态轨迹（含首次出场锚点）。

    锚点保证回退语义精确：删除章节到第 N 章后——
      该角色只要在第 N 章及之前出过场 → 卡保留，状态取 ≤N 的最近一条；
      否则（首次出场在第 N 章之后）→ 删除角色卡。
    """
    trails = {}
    for s in chunk_states:
        nm = str(s.get("char") or "").strip()
        if not nm:
            continue
        trails.setdefault(nm, []).append(
            {"ch": int(s.get("ch") or 0), "scenario": str(s.get("scenario") or ""),
             "status": str(s.get("status") or "active")})
    for tr in transitions:
        nm = str(tr.get("char") or "").strip()
        if not nm:
            continue
        trails.setdefault(nm, []).append(
            {"ch": int(tr.get("ch") or 0), "scenario": "",
             "status": str(tr.get("status") or "active")})
    # 同章合并去重（后写覆盖）
    for nm in trails:
        d = {}
        for e in sorted(trails[nm], key=lambda x: int(x.get("ch", 0) or 0)):
            d[int(e.get("ch", 0) or 0)] = e
        trails[nm] = [d[k] for k in sorted(d)]
    # 首次出场锚点（无状态上报的角色也有锚点；有上报但首条晚于首次出场的补锚点）
    for nm, meta in roster.items():
        if int(meta.get("freq", 0) or 0) <= 0:
            continue
        first = None
        for v in vols:
            for c in (v.get("chapters") or []):
                if nm in (c.get("names") or []):
                    first = int(c.get("no", 0) or 0)
                    break
            if first:
                break
        if not first:
            continue
        t = trails.setdefault(nm, [])
        if not any(int(e.get("ch", 0) or 0) == first for e in t):
            earliest_sc = next((e.get("scenario", "") for e in t if e.get("scenario")), "")
            t.append({"ch": first, "scenario": earliest_sc, "status": "active"})
            t.sort(key=lambda x: int(x.get("ch", 0) or 0))
    return trails


class NovelImporter:
    """小说导入成项目执行器：解析 → 拆书 → 设定合成 → 逐块人物 → 角色卡 → 落库。"""

    def __init__(self, log=None, stop_check=None, settings=None):
        self.log = log or (lambda kind, msg: None)
        self.stop_check = stop_check or (lambda: False)
        self.settings = settings or book_break.break_settings()

    def _profile(self):
        # v0.56 小说导入成项目可单独选 API（设置页用途分工「小说导入成项目」行）；
        # 未单独指定时跟随拆书工坊配置（导入先拆书，默认共用）
        return (self.settings.get("import_profile")
                or self.settings.get("profile") or None)

    def _user_prompt(self):
        # 拆书总体提示词（大方向）+ 小说整体规划（剧情设计/方向/主题/未完成部分）合并注入
        parts = []
        bp = book_break._user_break_prompt(self.settings)
        if bp:
            parts.append(bp)
        intro = str(self.settings.get("import_intro") or "").strip()
        if intro:
            parts.append(intro)
        return "\n".join(parts)

    def run(self, text, title="", options=None, progress_cb=None, job_dir=None):
        """完整导入。options: {"save_break":bool, "characters":bool, "chapters":bool}（缺省全开）。

        v0.55 断点续传：job_dir 给定（目录）时，拆书/设定合成/逐块人物/角色卡/管理笔记各环节
        结果即时落盘；API 出错/停止/软件退出后对同一文本再启动会自动跳过已完成环节，
        只补跑缺失部分，最后统一落库（落库幂等：续传时复用已建项目目录，不重复新建）。
        完成/放弃时由调用方决定删不删 job 目录。
        返回 {"ok", "dir", "title", "stats"} 或 {"ok":False, "error"}。
        """
        import concurrent.futures

        def _jload(*rel):
            if not job_dir:
                return None
            p = os.path.join(job_dir, *rel)
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None

        def _jsave(data, *rel):
            if not job_dir:
                return
            p = os.path.join(job_dir, *rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)

        opts = options or {}
        save_break = bool(opts.get("save_break", True))
        want_chars = bool(opts.get("characters", True))
        want_chapters = bool(opts.get("chapters", True))
        title = (title or "").strip() or "导入小说"

        # ① 解析（快，每次重算）
        self.log("info", "① 解析小说（分卷分章）…")
        parsed = book_break.parse_novel_full(text)
        vols = parsed["volumes"] or []
        total_ch = parsed["total_chapters"]
        if not vols or total_ch == 0:
            return {"ok": False, "error": "未能解析出任何章节（请确认是带章节标题的 txt 小说）"}
        if progress_cb:
            progress_cb("parse", 1, 1)
        self.log("info", "解析完成：%d 卷 / %d 章 / %.1f 万字。"
                 % (len(vols), total_ch, parsed["total_chars"] / 10000))

        # ② 拆书（四阶段管线，断点续传：已完成阶段自动跳过）
        self.log("info", "② 拆书分析（L1 骨架 → L2 逐卷细纲 → L3 汇总文档）…")
        breaker = book_break.NovelBreaker(log=self.log, stop_check=self.stop_check,
                                          settings=self.settings)
        br = breaker.run(text, title, progress_cb=progress_cb,
                         job_dir=os.path.join(job_dir, "break") if job_dir else None)
        if not br.get("ok"):
            return {"ok": False, "error": br.get("error") or "拆书失败"}
        doc = br.get("doc") or ""
        learning = br.get("learning") or ""
        inter = br.get("intermediate") or {}
        skeleton = inter.get("skeleton") or {}
        vol_notes = [v for v in (inter.get("vol_notes") or []) if v]
        title_summ = [v for v in (inter.get("title_summaries") or []) if v]
        if self.stop_check():
            return {"ok": False, "error": "已停止"}
        # 拆书风格入库（learning = 设计技法学习文本，主AI提示词自动注入学习）
        break_name = ""
        if save_break:
            break_name = "《%s》拆书" % title
            book_break.save_break(break_name, doc, learning)
            self.log("info", "拆书风格已保存：%s（主AI将学习其剧情推动/伏笔设计技法）" % break_name)

        # ③ 设定合成（断点续传：已有结果直接复用）
        synth = _jload("settings.json")
        if not isinstance(synth, dict):
            self.log("info", "③ 设定合成（剧情 / 世界观 / 特殊规则 / 文风 / 设定锚点 / 伏笔）…")
            def _call():
                r = synthesize_settings(
                    {"title": title, "skeleton": skeleton, "volumes": vol_notes,
                     "doc": doc[:12000], "samples": _samples(parsed, 2500)},
                    profile=self._profile(), user_prompt=self._user_prompt())
                if not isinstance(r, dict) or not r:
                    raise llm.LLMError("返回空结果")
                return r

            try:
                synth = book_break._retry_llm(_call, log=self.log, label="设定合成")
            except llm.StopRequested:
                raise
            except llm.LLMError as e:
                self.log("warn", "设定合成失败（已自动重试 %d 次仍失败）：%s"
                         % (book_break.RETRY_TIMES, str(e)[:120]))
                return {"ok": False,
                        "error": "设定合成失败（已自动重试 %d 次仍失败）：%s。"
                                 "中间结果已保留，可重试。"
                                 % (book_break.RETRY_TIMES, str(e)[:120])}
            if self.stop_check():
                return {"ok": False, "error": "已停止"}
            if not isinstance(synth, dict):
                synth = {}
            _jsave(synth, "settings.json")
        if progress_cb:
            progress_cb("settings", 1, 1)

        # ④ 逐块人物抽取（名册 + 分章状态 + 状态转变；支持并行；断点续传）
        self.log("info", "④ 逐块人物抽取（新角色名单 + 分章状态轨迹）…")
        chunks = _chunks(parsed, self.settings)
        roster = {}
        for c in (skeleton.get("characters") or []):
            if isinstance(c, dict) and str(c.get("name") or "").strip():
                roster.setdefault(str(c["name"]).strip(),
                                  {"role": str(c.get("role") or ""), "first_ch": 1,
                                   "persona": str(c.get("arc") or c.get("info") or ""),
                                   "freq": 0})
        for ts in title_summ:
            for p in (ts.get("people") or []):
                nm = str(p or "").strip()
                if nm:
                    roster.setdefault(nm, {"role": "", "first_ch": 1,
                                           "persona": "", "freq": 0})
        chunk_states = []
        transitions = []
        n_done = 0
        total_chunks = len(chunks)
        # 断点续传：加载已完成的块结果
        _cached_parts = {}
        if job_dir:
            for i in range(total_chunks):
                d = _jload("chunks", "part_%d.json" % i)
                if isinstance(d, dict) and d:
                    _cached_parts[i] = d
                    n_done += 1

        # v0.69 失败环节清单：LLM 出错/返回空的块不落盘、不视为完成（重试只补跑失败块）
        _failed = []

        def _absorb_result(r):
            if isinstance(r, dict) and r:
                _absorb_chunk(r, roster, chunk_states, transitions)

        if total_chunks:
            _todo = [i for i in range(total_chunks) if i not in _cached_parts]
            if _todo:
                if self.settings.get("parallel") and len(_todo) > 1:
                    import threading as _th
                    _plock = _th.Lock()
                    n_par = max(1, min(8, int(self.settings.get("parallel_n") or 2)))

                    def _do(i):
                        c = chunks[i]

                        def _call():
                            r = analyze_chunk_people(
                                _chunk_payload(c, roster.keys()),
                                profile=self._profile(),
                                user_prompt=self._user_prompt())
                            if not isinstance(r, dict) or not r:
                                raise llm.LLMError("返回空结果")
                            return r

                        try:
                            r = book_break._retry_llm(_call, log=self.log,
                                                      label="第 %d 块人物抽取" % (c["part"] + 1))
                        except llm.StopRequested:
                            raise
                        except llm.LLMError as e:
                            self.log("warn", "第 %d 块人物抽取失败（已自动重试 %d 次仍失败）：%s"
                                     % (c["part"] + 1, book_break.RETRY_TIMES, e))
                            _failed.append("人物抽取第 %d 块" % (c["part"] + 1))
                            r = {}
                        if r:
                            with _plock:
                                _jsave(r, "chunks", "part_%d.json" % i)
                        return i, r

                    with concurrent.futures.ThreadPoolExecutor(max_workers=n_par) as ex:
                        # v0.79.1 并行子线程继承停止事件（同拆书 _bound_title 说明）
                        def _bound_do(i):
                            _cur = llm.current_abort()
                            if _cur is not None:
                                llm.set_abort(_cur)
                            try:
                                return _do(i)
                            finally:
                                llm.set_abort(None)
                        futs = {ex.submit(_bound_do, i): i for i in _todo}
                        for fut in concurrent.futures.as_completed(futs):
                            i, r = fut.result()
                            _absorb_result(r)
                            n_done += 1
                            if progress_cb:
                                progress_cb("chunks", n_done, total_chunks)
                else:
                    for i in _todo:
                        if self.stop_check():
                            return {"ok": False, "error": "已停止"}
                        c = chunks[i]

                        def _call():
                            r = analyze_chunk_people(
                                _chunk_payload(c, roster.keys()),
                                profile=self._profile(),
                                user_prompt=self._user_prompt())
                            if not isinstance(r, dict) or not r:
                                raise llm.LLMError("返回空结果")
                            return r

                        try:
                            r = book_break._retry_llm(_call, log=self.log,
                                                      label="第 %d 块人物抽取" % (c["part"] + 1))
                        except llm.StopRequested:
                            raise
                        except llm.LLMError as e:
                            self.log("warn", "第 %d 块人物抽取失败（已自动重试 %d 次仍失败）：%s"
                                     % (c["part"] + 1, book_break.RETRY_TIMES, e))
                            _failed.append("人物抽取第 %d 块" % (c["part"] + 1))
                            r = {}
                        if r:
                            _jsave(r, "chunks", "part_%d.json" % i)
                            _absorb_result(r)
                        n_done += 1
                        if progress_cb:
                            progress_cb("chunks", n_done, total_chunks)
            else:
                for i in _cached_parts:
                    _absorb_result(_cached_parts[i])
        if _failed:
            return {"ok": False,
                    "error": "%d 个环节未完成（失败）：%s。每个环节已自动重试 %d 次仍失败，"
                             "中间结果已保留——重试只补跑失败环节。"
                             % (len(_failed), "；".join(_failed[:8])
                                + ("…" if len(_failed) > 8 else ""),
                                book_break.RETRY_TIMES)}
        if self.stop_check():
            return {"ok": False, "error": "已停止"}

        # ⑤ 按章全名匹配出场角色（长名优先，避免短名误配前缀；确定性，每次重算）
        self.log("info", "⑤ 按章匹配出场角色（名册全名匹配）…")
        name_list = sorted(roster.keys(), key=lambda n: len(n), reverse=True)
        for v in vols:
            for c in (v.get("chapters") or []):
                content = c.get("content") or ""
                seen = []
                for nm in name_list:
                    if len(nm) < 2:
                        continue
                    try:
                        first_ch = int(roster[nm].get("first_ch", 1) or 1)
                    except (TypeError, ValueError):
                        first_ch = 1
                    if int(c.get("no", 0) or 0) < first_ch:
                        continue
                    if content.count(nm) > 0:
                        seen.append(nm)
                        roster[nm]["freq"] = roster[nm].get("freq", 0) + 1
                c["names"] = seen
        if self.stop_check():
            return {"ok": False, "error": "已停止"}

        # ⑥ 角色卡生成：出场频率高的 LLM 批量详立卡，其余建轻量卡（断点续传）
        cards_meta = {}   # name -> 卡 dict / None（轻量）
        if want_chars:
            detail_names = [nm for nm, m in sorted(
                roster.items(),
                key=lambda kv: (int(kv[1].get("freq", 0) or 0), len(kv[0])),
                reverse=True)
                if int(m.get("freq", 0) or 0) > 0][:DETAIL_CARDS_MAX]
            self.log("info", "⑥ 生成角色卡（详立 %d 个主要角色，其余建轻量卡）…" % len(detail_names))
            total_batches = (len(detail_names) + BATCH_CARDS - 1) // BATCH_CARDS
            for bi in range(total_batches):
                if self.stop_check():
                    return {"ok": False, "error": "已停止"}
                batch = detail_names[bi * BATCH_CARDS:(bi + 1) * BATCH_CARDS]
                cached_cards = _jload("cards", "batch_%d.json") if job_dir else None
                if isinstance(cached_cards, list):
                    cards = [d for d in cached_cards if isinstance(d, dict)]
                else:
                    samples = []
                    for nm in batch:
                        got = []
                        for v in vols:
                            for c in (v.get("chapters") or []):
                                if nm in (c.get("names") or []) and len(got) < 3:
                                    got.append("（%s）%s" % (
                                        c.get("title") or "第%d章" % c.get("no", 0),
                                        (c.get("content") or "")[:CARD_SAMPLE_CHARS]))
                        if got:
                            samples.append("【%s】\n%s" % (nm, "\n".join(got)))
                    def _call():
                        r = build_character_cards(
                            [{"name": nm, "role": roster[nm].get("role", ""),
                              "persona": roster[nm].get("persona", "")} for nm in batch],
                            samples, profile=self._profile(),
                            user_prompt=self._user_prompt())
                        if not isinstance(r, list) or not r:
                            raise llm.LLMError("返回空结果")
                        return r

                    try:
                        cards = book_break._retry_llm(
                            _call, log=self.log,
                            label="角色卡批量生成（第 %d 批）" % (bi + 1))
                    except llm.StopRequested:
                        raise
                    except llm.LLMError as e:
                        self.log("warn", "角色卡批量生成失败（已自动重试 %d 次仍失败）：%s"
                                 % (book_break.RETRY_TIMES, e))
                        _failed.append("角色卡第 %d 批" % (bi + 1))
                        cards = []
                    if cards:
                        _jsave(cards, "cards", "batch_%d.json" % bi)
                for cd in cards:
                    nm = str(cd.get("name") or "").strip()
                    if nm and nm in roster:
                        cards_meta[nm] = cd
                if progress_cb:
                    progress_cb("cards", min((bi + 1) * BATCH_CARDS, len(detail_names)),
                                max(1, len(detail_names)))
        if _failed:
            return {"ok": False,
                    "error": "%d 个环节未完成（失败）：%s。每个环节已自动重试 %d 次仍失败，"
                             "中间结果已保留——重试只补跑失败环节。"
                             % (len(_failed), "；".join(_failed[:8])
                                + ("…" if len(_failed) > 8 else ""),
                                book_break.RETRY_TIMES)}
        # 轻量卡（未详立但有出场的配角）
        for nm, meta in roster.items():
            if int(meta.get("freq", 0) or 0) > 0 and nm not in cards_meta:
                cards_meta[nm] = None
        if self.stop_check():
            return {"ok": False, "error": "已停止"}

        # 分章状态轨迹（删除章节回滚角色卡用；全量写入不截断）
        trails = _assemble_trails(chunk_states, transitions, roster, vols, cards_meta)

        # ⑥.5 主AI管理笔记：按卷/块梳理剧情推进与人物动向（断点续传）
        summary_data = _jload("summary.json")
        if not isinstance(summary_data, dict) or not summary_data.get("summary"):
            self.log("info", "⑥.5 管理笔记梳理（按卷梳理剧情推进 / 人物动向）…")
            try:
                summary_data = book_break._retry_llm(
                    lambda: synthesize_summary(
                        {"title": title,
                         "volumes": [{"vol": v.get("vol"), "title": v.get("title", ""),
                                      "events": v.get("events") or [],
                                      "foreshadow_seed": v.get("foreshadow_seed") or [],
                                      "foreshadow_payoff": v.get("foreshadow_payoff") or []}
                                     for v in vol_notes],
                         "chunks": [{"part": i, "new_chars": (r.get("new_chars") or []),
                                     "states": (r.get("states") or []),
                                     "transitions": (r.get("transitions") or [])}
                                    for i, r in sorted(_cached_parts.items())]},
                        profile=self._profile(), user_prompt=self._user_prompt()),
                    log=self.log, label="管理笔记梳理")
            except llm.StopRequested:
                raise
            except llm.LLMError as e:
                self.log("warn", "管理笔记梳理失败（已自动重试 %d 次仍失败）：%s"
                         % (book_break.RETRY_TIMES, str(e)[:120]))
                return {"ok": False,
                        "error": "管理笔记梳理失败（已自动重试 %d 次仍失败）：%s。"
                                 "中间结果已保留，可重试。"
                                 % (book_break.RETRY_TIMES, str(e)[:120])}
            if self.stop_check():
                return {"ok": False, "error": "已停止"}
            if not isinstance(summary_data, dict):
                summary_data = {}
            _jsave(summary_data, "summary.json")
        if progress_cb:
            progress_cb("summary", 1, 1)

        # ⑦ 落库（幂等：续传时复用已建项目目录，不重复新建）
        self.log("info", "⑦ 落库：写入设定 / 角色卡 / 章节 / 伏笔台账 / 写作计划…")
        meta = _jload("meta.json") or {}
        project_dir = meta.get("project_dir") or ""
        if project_dir and os.path.isdir(os.path.join(storage.PROJECTS_DIR, project_dir)):
            store = storage.ProjectStore(project_dir)
            project = store.load_project()
            if project is None:
                project_dir = ""
        if not project_dir:
            project = storage.create_project(title)
            project_dir = project.dir_name
            store = storage.ProjectStore(project_dir)
            _jsave({"title": title, "project_dir": project_dir}, "meta.json")
        project.title = title
        project.story_brief = str(synth.get("brief") or "").strip()
        project.story_world = str(synth.get("world") or "").strip()
        project.story_rules = str(synth.get("rules") or "").strip()
        project.story_style = str(synth.get("style") or "").strip()
        note = synth.get("style_note") or []
        if isinstance(note, list):
            project.story_style_note = "\n".join(
                str(x).strip()[:30] for x in note if str(x).strip())[:600]
        elif isinstance(note, str):
            project.story_style_note = note.strip()[:600]
        project.story_style_ref = _samples(parsed, STYLE_REF_MAX)
        project.story_break_style = break_name
        project.story_summary = str(summary_data.get("summary") or synth.get("summary")
                                    or doc or "")[:SUMMARY_MAX]
        kcs = synth.get("key_characters") or []
        if isinstance(kcs, list):
            project.story_characters = [
                {"name": str(x.get("name", "")).strip(), "info": str(x.get("info", "")).strip()}
                for x in kcs if isinstance(x, dict) and str(x.get("name", "")).strip()]
        pool = skeleton.get("foreshadow_pool") or []
        if isinstance(pool, list):
            project.story_ideas = [str(x).strip() for x in pool if str(x).strip()]
        _ideas = summary_data.get("ideas") or []
        if isinstance(_ideas, list):
            for it in _ideas:
                s = str(it).strip()
                if s and s not in project.story_ideas:
                    project.story_ideas.append(s)
        lore = synth.get("lore") or []
        if isinstance(lore, list):
            for x in lore[:LORE_MAX]:
                if not isinstance(x, dict):
                    continue
                lt = str(x.get("title") or "").strip()
                lc = str(x.get("content") or "").strip()
                if lt and lc:
                    project.lore_entries.append({"id": uid(), "title": lt,
                                                 "keys": [lt], "content": lc,
                                                 "always": False})
        # 章节写作计划：卷细纲事件 → [{start, end, note}]（与正常项目一致，写作时自动生效）
        _plans = []
        for v in vol_notes:
            for e in (v.get("events") or []):
                if not isinstance(e, dict):
                    continue
                try:
                    s = int(e.get("start_ch") or 0)
                    en = int(e.get("end_ch") or 0)
                except (TypeError, ValueError):
                    continue
                if s > 0 and en >= s:
                    _plans.append({"start": s, "end": en,
                                   "note": "【%s】%s（推动：%s；冲突：%s；高潮：%s）" % (
                                       str(e.get("title") or "事件"),
                                       str(e.get("drive") or ""),
                                       str(e.get("drive") or ""),
                                       str(e.get("conflict") or ""),
                                       str(e.get("climax") or ""))})
        _seen_plans = set()
        for p in _plans:
            key = (p["start"], p["end"])
            if key not in _seen_plans:
                _seen_plans.add(key)
                project.chapter_plans.append(p)
        project.volume_target = total_ch
        project.state["volume_plan"] = {
            "target_chapters": total_ch,
            "description": "小说导入成项目：全书 %d 章原样入库，可继续续写" % total_ch}
        project.state["next_chapter"] = total_ch + 1
        project.state["story_complete"] = False
        store.save_project(project)

        # 角色卡 + 信息库（状态转变记为事件；卡面状态取轨迹末条；按名复用 id 保证幂等）
        char_by_name = {}
        _existing = {}
        for cid, nm, _s in store.list_characters():
            _existing[nm] = cid
        if want_chars:
            for nm, cd in cards_meta.items():
                cid = _existing.get(nm)
                if cd is None:
                    if cid:
                        card, lib = store.load_character(cid)
                        if card is None:
                            continue
                    else:
                        card = CharacterCard(nm)
                        card.role = roster[nm].get("role", "")
                        card.category = "NPC"
                        card.created_by = "ai"
                        card.description = roster[nm].get("persona", "")
                        lib = InfoLibrary(card.id)
                else:
                    try:
                        card = main_ai.character_from_data(cd, created_by="ai")
                    except ValueError:
                        continue
                    if cid:
                        card.id = cid   # 复用已建卡 id（续传落库幂等）
                        card.name = nm
                        lib = InfoLibrary(cid)
                    else:
                        lib = InfoLibrary(card.id)
                trail = trails.get(nm) or []
                card.chapter_states = [dict(e) for e in trail]
                for tr in transitions:
                    if str(tr.get("char") or "").strip() == nm:
                        lib.events.append({
                            "chapter": int(tr.get("ch") or 0),
                            "event": str(tr.get("reason") or "状态变化"),
                            "impact": "状态：%s" % str(tr.get("status") or "")})
                if card.chapter_states:
                    last = card.chapter_states[-1]
                    card.scenario = last.get("scenario", "")
                    card.status = last.get("status", "active")
                    lib.scenario = last.get("scenario", "")
                store.save_character(card, lib)
                char_by_name[nm] = card.id
        self.log("info", "角色卡建立：%d 个。" % len(char_by_name))

        # 章节（原样 approved 入库；出场角色/一句话梗概/卷归属）
        if want_chapters:
            for v in vols:
                for c in (v.get("chapters") or []):
                    ch = Chapter(int(c.get("no", 0) or 0), int(v.get("no", 1) or 1))
                    ch.title = c.get("title") or "第%d章" % ch.index
                    ch.content = (c.get("content") or "").strip()
                    ch.status = CHAPTER_STATUS_APPROVED
                    first_para = next((p.strip() for p in ch.content.split("\n") if p.strip()),
                                      ch.content)
                    ch.brief = first_para[:120]
                    if want_chars:
                        ch.characters = [char_by_name[nm] for nm in (c.get("names") or [])
                                         if nm in char_by_name]
                    store.save_chapter(ch)

        # 伏笔台账：先种（卷细纲种子 + 设定合成伏笔池）后收（卷细纲 payoff）
        # v1.102 双账本登记：分类（event/character）、线名（storyline，若拆书给了）、
        # 干系人/依托角色（target_character，拆书没给时按文本子串匹配角色名）
        fs = []

        def _plant_fs(raw, chapter):
            text = str(raw.get("text") or "").strip()
            if not text:
                return
            if text in {x.text for x in fs}:
                return
            target = str(raw.get("target_character") or "").strip()
            storyline = str(raw.get("storyline") or "").strip()
            related = raw.get("related_chars") or []
            if isinstance(related, str):
                related = [x.strip() for x in related.replace("，", ",").replace("、", ",").split(",")
                           if x.strip()]
            if not target and char_by_name:
                for nm in char_by_name:
                    if len(nm) >= 2 and nm in text:
                        target = nm
                        break
            f = Foreshadow(text, "plant", target)
            f.planted_chapter = int(chapter or 0)
            f.storyline = storyline
            f.f_category = ("character" if (target and not storyline) else "event")
            f.related_chars = [str(x).strip() for x in related if str(x).strip()]
            fs.append(f)

        for v in vol_notes:
            for f in (v.get("foreshadow_seed") or []):
                if isinstance(f, dict):
                    _plant_fs(f, f.get("chapter"))
        for f in (synth.get("foreshadows") or []):
            if isinstance(f, dict):
                _plant_fs(f, f.get("chapter"))
        for v in vol_notes:
            for f in (v.get("foreshadow_payoff") or []):
                if isinstance(f, dict) and str(f.get("text") or "").strip():
                    text = str(f["text"]).strip()
                    chf = int(f.get("chapter") or 0)
                    for x in fs:
                        if x.status == "open" and (text in x.text or x.text in text):
                            if len(text) >= 4 or len(x.text) >= 4:
                                x.status = "resolved"
                                x.resolved_chapter = chf
                                break
        store.save_foreshadows(fs)
        store.append_log("【小说导入成项目】《%s》已还原为项目：%d 卷 / %d 章 / 角色 %d 个。"
                         % (title, len(vols), total_ch, len(char_by_name)))
        if job_dir:
            _jsave({"ok": True}, "done.json")
        self.log("info", "导入完成：《%s》已还原为项目（%d 卷 / %d 章 / 角色 %d 个），"
                 "可在书架继续编辑/续写；删除章节后角色卡会自动回退到对应章节。"
                 % (title, len(vols), total_ch, len(char_by_name)))
        return {"ok": True, "dir": project_dir, "title": title,
                "stats": {"volumes": len(vols), "chapters": total_ch,
                          "chars": parsed["total_chars"],
                          "characters": len(char_by_name)}}
