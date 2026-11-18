# -*- coding: utf-8 -*-
"""情景卡拆书引擎（v1.26）：从整本小说 txt 自动拆出全部「正文AI情景规则卡」草稿。

用户需求：拆书页做一个「自动把我导入的小说拆出所有情景卡」——不同的打斗、小说开篇、
不同的矛盾引爆、男女朋友分手、绝境描写等诸多情景都得拆分（拆得越详细越好，省得用户
自己摸索捣鼓）；拆完把**相似度很高的情景卡合并**（同类合并），产出的卡可直接存进总库
（config.writer_scene_cards）供本项目/一键成书选用。

管线（应对超长文，全程可分片、可停止）：
  阶段1 逐片抽取候选：把正文按字符预算切成若干片（每片含完整章节），每片 LLM 列出
        该片出现的正文情景候选 [{type, brief, example}]（type=具体情景类型名，
        example=代表性原文片段 ≤100 字）；
  阶段2 全书合并去重：全部候选按**语义相似度合并**（街斗/群殴/围攻→同一个类型），
        候选过多时按批合并再合，输出 [{category, type, examples}]（category=大类，
        type=合并后的具体情景卡名）；
  阶段3 每类生成卡草稿：每个 type 按范例结构（核心定位+分节细则+写作执行自检清单）
        参考 examples 提炼一张可执行规则卡（不照抄原句）→ [(name, content, category)]。

LLM 全部走「用途分工·情景提示词制作」配置（role="scene_card"；未单独指定跟随通用），
与情景提示词页 AI 生成/从文本提取同一 API 通道。
"""
import json

import llm
import book_break

# 单片正文预算（字符）：太大超出上下文、太小调用次数多；按完整章节切片
SCENE_BATCH_CHARS = 12000
# 阶段2 候选过多时的分批合并粒度
MERGE_BATCH = 60
# 阶段3 单卡草稿输出预算
CARD_MAX_TOKENS = 2500

_SYS_CANDIDATE = (
    "你是一位资深拆书家兼网文情景分类专家，深谙小说里各种「正文情景」的写法差异。"
    "你的任务是从给出的**章节正文**里，把这次出现的、值得单独做一张写作规则卡的"
    "「正文情景」全部列出来——不同的打斗（兵刃近身/群殴围攻/远程对轰/师徒喂招等）、"
    "小说开篇、不同的矛盾引爆、分手、绝境描写、装逼打脸、群像宴会、审讯逼供、"
    "大婚、葬礼、逃亡、低谷自省、氛围酝酿等。"
    "**v1.32 泛化要求（必须遵守）**：候选 type 必须抽象为**可迁移到其他故事的通用写法类型**"
    "（如「日常嬉闹互动」「亲密关系打闹」），**禁止绑定具体人物/关系/场景细节**"
    "（如「哥哥和妹妹边打闹边做饭」应泛化为「亲密家人日常嬉闹做饭」这类写法类型；"
    "「张伟在巷子里被堵」→「小巷被围堵」）；写法差异大的同类拆成不同候选。"
    "**v1.33 怎么写/怎么做边界（必须遵守）**：本清单只提炼**「怎么写」的写法类型**"
    "——这段文字的节奏、感官、氛围、情绪渐变等写法特征；**不要按「怎么做」（情节/行为/"
    "事件）分类**（如「主角被追杀逃进巷子」是情节不是写法类型，应泛化为「短巷奔逃的"
    "急迫节奏写法」）。候选必须是『任何故事遇到同类写法需求都能照做』的写法类型。"
    "只输出 JSON 数组，不要解释："
    '[{"type":"写法类型名（泛化可迁移，强调怎么写而非剧情怎么做，如：夜战夺镖·兵刃近身的节奏与感官）","brief":"该类写法在这批正文里的要点/出现位置（一句话）","example":"代表性原文片段（原样引用，不超过100字）"}]'
    "每批最多列 8 个候选，按重要性/出现频率排序；本批没有足够价值的情景时可少于 3 个。"
)

_SYS_MERGE = (
    "你是一位情景规则卡库管理专家。下面是从一本小说各批正文里抽取的**全部候选情景**"
    "（type=候选名，example=代表性原文片段）。"
    "请把**写法相似度高、没有本质区别**的候选合并为同一张卡："
    "（如『街巷斗殴』『群殴围攻』『多人混战』可并入同一个武打类卡；『男主初登场』"
    "『女主第一次出场』『开篇引入主角』可并入『主要角色登场』类）。"
    "写法差异足够大的同类（如『兵刃近身死斗』vs『远程法器对轰』）保持分开。"
    "**v1.32 泛化要求**：合并后的 type/category 必须是**可迁移的通用写法类型**"
    "（写法层面：动作节奏/心理攻防/氛围营造等），禁止绑定具体人物/关系/场景/剧情细节。"
    "**v1.33 怎么写/怎么做边界**：只按**写法特征**合并（节奏、感官、氛围、悬念度等），"
    "不按剧情内容合并——『主人公被追杀』和『车队被劫』若写法同属『奔逃的急迫节奏』可并，"
    "若写法差异大（一个写心理、一个写血腥场面）则分。"
    "合并后给每个**具体卡**定一个清晰泛化的名字（type），并归一个**大类**（category，"
    "如：武打/情感/日常对话/开篇登场/矛盾引爆/绝境困境/悬疑惊悚/装逼打脸/群像场面/收尾/氛围酝酿，"
    "自由把握不必凑齐），examples 合并保留各候选的代表片段（每条仍 ≤100 字，最多 4 条）。"
    "只输出 JSON 数组，不要解释："
    '[{"category":"大类","type":"合并后的泛化写法卡名","examples":["片段1","片段2"]}]'
    "输出数量控制在合并后真正有差异的卡片数，别硬凑。"
)

_SYS_CARD = (
    "你是一位资深网文写作规则设计师，擅长把具体书里的写法提炼成可迁移的写作规则。"
    "下面给你一个情景类型 + 该书里这类情景的代表性原文片段。"
    "请按范例「情景写作提示词」的结构，为这类情景写一张正文AI可直接照做的**写法规则卡**："
    "第一行一句「你是一位……的……，擅长……」角色定位；然后「**核心定位：**」一两句"
    "点明这类情景的底层写法逻辑；再按写法拆若干「**一、……：**」「**二、……：**」分节"
    "（节奏与起伏/感官与细节/氛围与情绪/对白与留白/段落与长短句等按需取舍），每节内用"
    "「- 」短句给具体可执行的规则（怎么写、必须出现什么、禁止什么）；最后一节"
    "「**写作执行与自检清单：**」逐条编号收敛全部硬性要求。"
    "规则必须从示例片段的**实际写法**提炼（有据可依、可迁移）；"
    "**v1.32 泛化要求**：规则面向**同类情景**而非具体人物/事件——禁止出现本书人名、具体地名、"
    "具体事件、具体身份关系（如「哥哥」「妹妹」「做饭」这类绑定细节），"
    "必须是『任何故事里遇到这类情景都能照做』的写法规则；"
    "**v1.33 怎么写/怎么做边界（最重要，必须遵守）**：这张卡**只讲『怎么写』，"
    "严禁写『怎么做』**——只给写法技法（节奏铺陈、感官细节密度、氛围用词、对白与留白的"
    "比例、段落长短变化、情绪渐变的语言手法等），**禁止出现任何行为/事件/情节指令**"
    "（如『主角先拔刀再冲向对方』『反派说出真相后翻脸』这类让人照着做的剧情内容）；"
    "示例片段中的行为/事件只许用来提炼写法，绝不可原样抄进规则；"
    "这样卡才不会与主AI的剧情判断冲突、才不会让不同书的同类情景写法雷同抄袭、"
    "才能适用于所有同写法需求的故事。"
    "字数不做要求（宁可写足也不要压缩成干条），不要写『本书/这段』这类只对单段有效的套话。"
)


def _iter_chapters(parsed):
    """把 parse_novel_full 的结果平铺成章节列表 [(no, title, content)]。"""
    out = []
    n = 0
    for v in parsed.get("volumes") or []:
        for ch in v.get("chapters") or []:
            n += 1
            ct = str(ch.get("content") or "").strip()
            if ct:
                out.append((n, str(ch.get("title") or "").strip(), ct))
    return out


def _chunks(chapters):
    """按字符预算把章节拼成片（每片含完整章节），返回 [{"title","text"}]。"""
    chunks = []
    cur_title = []
    cur_text = []
    cur_len = 0
    for no, title, ct in chapters:
        cur_title.append("第%d章 %s" % (no, title))
        cur_text.append(ct)
        cur_len += len(ct)
        if cur_len >= SCENE_BATCH_CHARS:
            chunks.append({"title": " · ".join(cur_title) if len(cur_title) <= 3
                           else "……".join([cur_title[0], cur_title[-1]]),
                           "text": "\n\n".join(cur_text)})
            cur_title, cur_text, cur_len = [], [], 0
    if cur_text:
        chunks.append({"title": " · ".join(cur_title) if len(cur_title) <= 3
                       else "……".join([cur_title[0], cur_title[-1]]),
                       "text": "\n\n".join(cur_text)})
    return chunks


def _candidate_batch(chunk, prompt="", tag="gen_scene_batch"):
    """阶段1：对一片正文列出候选情景，返回 [{type,brief,example}]。

    prompt：用户给的控制性提示词（v1.27，可选）——指定重点拆哪些情景/跳过哪些/
    注意哪些写法差异，注入候选抽取让 AI 按方向拆。
    """
    text = chunk.get("text") or ""
    lines = ["【本片章节】%s" % (chunk.get("title") or ""),
             "【正文】",
             text[:SCENE_BATCH_CHARS]]
    if prompt and str(prompt).strip():
        lines.append("【用户指定关注方向（必须遵守；本片尽量按这个方向拆）】%s"
                     % str(prompt).strip())
    lines.append("【输出】按批次 JSON 数组列出本片值得单独做规则卡的正文情景候选。")
    user = "\n".join(lines)
    raw = llm.chat_json(_SYS_CANDIDATE, user, tag=tag, role="scene_card",
                        max_tokens=4000)
    out = []
    for x in (raw or []):
        if not isinstance(x, dict):
            continue
        t = str(x.get("type") or "").strip()
        if not t:
            continue
        out.append({"type": t,
                    "brief": str(x.get("brief") or "").strip()[:200],
                    "example": str(x.get("example") or "").strip()[:120]})
    return out


def _merge_once(cands, tag="gen_scene_merge"):
    """阶段2 单次合并：候选清单 → [{category,type,examples}]（相似度高合并）。"""
    lines = []
    for i, c in enumerate(cands, 1):
        # v1.29：分批二次合并时输入结构是 {category,type,examples[]}（无 example/brief），
        # 从 examples 取代表片段兜底，否则大书（候选>60）二次合并只凭类型名判断、示例全丢
        ex = str(c.get("example") or "").strip() or str(c.get("brief") or "").strip()
        if not ex:
            for _e in (c.get("examples") or []):
                if str(_e or "").strip():
                    ex = str(_e).strip()
                    break
        lines.append("%d. %s｜%s" % (i, str(c.get("type") or "").strip(), ex[:120]))
    user = "【全部候选情景】\n%s\n\n【输出】合并后的 JSON 数组。" % "\n".join(lines)
    raw = llm.chat_json(_SYS_MERGE, user, tag=tag, role="scene_card", max_tokens=5000)
    out = []
    for x in (raw or []):
        if not isinstance(x, dict):
            continue
        t = str(x.get("type") or "").strip()
        if not t:
            continue
        exs = []
        for e in (x.get("examples") or []):
            s = str(e or "").strip()
            if s:
                exs.append(s[:120])
        out.append({"category": str(x.get("category") or "").strip(),
                    "type": t, "examples": exs})
    return out


def _merge_all(cands, stop_check=None):
    """阶段2 全书合并去重：候选过多时按批合并再合。"""
    cands = [c for c in cands if (c.get("type") or "").strip()]
    if not cands:
        return []
    if len(cands) <= MERGE_BATCH:
        return _merge_once(cands, "gen_scene_merge")
    merged = []
    for i in range(0, len(cands), MERGE_BATCH):
        if stop_check and stop_check():
            raise llm.StopRequested("用户停止")
        part = _merge_once(cands[i:i + MERGE_BATCH], "gen_scene_merge")
        merged.extend(part or [])
    if len(merged) > MERGE_BATCH:
        return _merge_once(merged, "gen_scene_merge2")
    return merged


def _build_card(item, tag="gen_scene_card_book"):
    """阶段3：按类别生成卡草稿，返回 {"name","content","category"}。"""
    t = str(item.get("type") or "").strip()
    cat = str(item.get("category") or "").strip()
    exs = [e for e in (item.get("examples") or []) if str(e or "").strip()]
    ex_text = "\n".join("■ %s" % str(e).strip()[:120] for e in exs) or "（无示例片段）"
    user = "【情景类型】%s\n【归属分类】%s\n【本书示例片段】\n%s\n\n【输出】规则卡全文。" % (
        t, cat or "（未分类）", ex_text)
    text = llm.chat_text(_SYS_CARD, user, tag=tag, role="scene_card",
                         max_tokens=CARD_MAX_TOKENS)
    if not (text or "").strip():
        raise llm.LLMError("生成情景卡「%s」返回空内容" % t)
    return {"name": t, "content": (text or "").strip(), "category": cat}


def extract_scene_cards_from_novel(text, prompt=None, sink=None, stop_check=None,
                                   on_card=None):
    """主入口：从小说全文拆出全部情景卡草稿。

    prompt：用户控制性提示词（v1.27，可选）——指定重点拆哪些情景/跳过哪些/注意哪些
    写法差异，注入每一片的候选抽取；留空按通用思路拆。
    返回 [{"name","content","category"}]（name=卡名/情景类型，content=卡草稿范例结构，
    category=大类，可空）。sink(kind, msg) 收进度日志；stop_check() 返回 True 时抛
    StopRequested 中止（LLM 调用本身也响应 llm.set_abort）。
    on_card（v1.36，可选）：每生成一张卡草稿立即回调 on_card(card)——长小说逐张拆出
    时 GUI 可边拆边列，停止/失败后已回调的卡不丢。
    """
    def log(kind, msg):
        if sink:
            try:
                sink(kind, msg)
            except Exception:
                pass

    parsed = book_break.parse_novel_full(text)
    chapters = _iter_chapters(parsed)
    total_chars = parsed.get("total_chars") or sum(len(c) for _, _, c in chapters)
    log("info", "情景卡拆书：全书 %d 章、约 %d 字。" % (len(chapters), total_chars))
    if prompt and str(prompt).strip():
        log("info", "控制性提示词：%s" % str(prompt).strip())
    if not chapters:
        log("warn", "没解析出章节正文，无法拆情景卡。")
        return []

    chunks = _chunks(chapters)
    log("info", "分片：%d 片（每片约 %d 字，含完整章节）。开始逐片抽取候选情景…"
        % (len(chunks), SCENE_BATCH_CHARS))

    # 阶段1：逐片抽取候选
    candidates = []
    for i, chk in enumerate(chunks, 1):
        if stop_check and stop_check():
            raise llm.StopRequested("用户停止")
        try:
            got = _candidate_batch(chk, prompt or "", "gen_scene_batch_%d" % i)
        except llm.StopRequested:
            raise
        except Exception as e:
            log("warn", "第 %d 片抽取失败（%s），跳过该片。" % (i, e))
            got = []
        if got:
            candidates.extend(got)
            log("info", "第 %d/%d 片：抽到 %d 个候选情景（累计 %d）。"
                % (i, len(chunks), len(got), len(candidates)))
        else:
            log("warn", "第 %d/%d 片：没有抽到候选情景。" % (i, len(chunks)))
    log("info", "候选情景共 %d 个。开始按相似度合并去重…" % len(candidates))

    # 阶段2：合并去重
    merged = _merge_all(candidates, stop_check)
    log("info", "合并后剩 %d 个情景类型。开始逐类生成卡草稿…" % len(merged))

    # 阶段3：逐类生成卡草稿
    cards = []
    for i, item in enumerate(merged, 1):
        if stop_check and stop_check():
            raise llm.StopRequested("用户停止")
        try:
            card = _build_card(item, "gen_scene_card_book_%d" % i)
        except llm.StopRequested:
            raise
        except Exception as e:
            log("warn", "为「%s」生成卡失败（%s），跳过。" % (item.get("type") or "?", e))
            continue
        cards.append(card)
        if on_card:
            try:
                on_card(card)
            except Exception:
                pass
        log("info", "卡草稿 %d/%d：「%s」（%d 字）。"
            % (i, len(merged), card["name"], len(card["content"])))
    log("info", "情景卡拆书完成：共 %d 张卡草稿（可勾选后存进总库，分类已保留，可再编辑）。"
        % len(cards))
    return cards