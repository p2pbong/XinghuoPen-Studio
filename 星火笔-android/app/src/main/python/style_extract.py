# -*- coding: utf-8 -*-
"""文风校对引擎（v0.64 移植自 novel-style-extractor-v0.22，用户自制项目）。

A(提取文风)→B(生成文章)→C(评估打分)→D(优化提示词) 多轮迭代，直到相似度达标或达到最大轮次。
- 与星火笔 llm 集成：每个节点调用 llm.chat_text（无状态；429 限流自动退避重试——
  v0.22 原项目的「修复商汤等慢 RPM 报错 429」在星火笔 llm 里天然具备）；
- API 走星火笔配置：style_profiles（设置页用途分工·文风校对四节点行，每节点可各选 API；
  留空跟随全局；旧单键 style_profile 兼容为四节点兜底），四节点按各自节点取对应配置；
- 相似度 = 0.4×轻量 TF-IDF(字符bigram)+cosine + 0.6×LLM 评分（与原项目一致，
  轻量实现不依赖 sklearn/jieba，便携体积不增）；
- 停止：worker 线程 set_abort(Event)，LLM 调用中检测到即抛 StopRequested 中断；
- 提示词/预设存 data/style_extract/（prompts.json 当前值；presets.json 预设库，
  仅保留 default 空壳，不预置任何预设内容，用户自行保存）。
"""
import json
import os
import re
import time
from collections import Counter
from math import log, sqrt

import config
import llm

# ---------- 默认提示词（每次启动加载，用户可修改保存） ----------
DEFAULT_PROMPTS = {
    "node_a": "{原文}\n\n请分析以上文本的文风特征。",
    "node_b": "{文风提示词}\n\n请根据以上文风特征创作文章。",
    "node_c": "{生成文章}\n{原文}\n\n请对比以上两篇文本的文风相似度，给出评分（0-100）：\n"
              "【生成文章】为AI根据文风提示词写出的文本\n【原文】为用户提供的参考文本",
    "node_d": "{文风提示词}\n{生成文章}\n{原文}\n\n请优化【文风提示词】，使【生成文章】"
              "更接近【原文】的风格。输出优化后的完整提示词。\n【文风提示词】为当前使用的文风特征\n"
              "【生成文章】为AI根据当前文风提示词写出的文本\n【原文】为用户提供的参考文本",
}

# ---------- 内置正式预设（v1.76 用户定稿；全新安装即带「文风提取」「剧情设计提取」两套） ----------
# 仅作兜底：data/style_extract/presets.json 存在时以文件内容为准（用户可增删改）。
DEFAULT_PRESETS = json.loads('{\n "文风提取": {\n  "node_a": "你现在是一位专业的小说写作风格分析师和角色卡设计师。\\n我提供了一篇小说范文（体裁不限）。\\n你的任务是：\\n仔细阅读范文，只提取写作风格特征，完全忽略具体人物姓名、背景设定、具体情节线索和事件发展（提取出的文风提示词禁止出现范文中的人物姓名等内容）。\\n重点总结以下通用文学风格维度（必须详细、具体、可操作）：\\n- 语言质感与用词习惯：词汇的雅俗偏好（如：古风雅致、现代冷峻、口语化、书面语等），常用的高频形容词、动词及特定领域的术语；句式的长短节奏控制。\\n- 叙事视角与声音：叙述者的口吻（冷静旁观、深情沉浸、幽默调侃、压抑克制等），人称选择及其对读者代入感的影响，内心独白与外部描写的比例。\\n- 修辞与意象系统：最常用的比喻类型（明喻/暗喻/通感），核心意象群（如：自然景物、机械冷硬、色彩光影等），以及如何处理抽象情感的具体化表达。\\n- 环境与氛围营造：如何通过环境描写烘托情绪（情景交融的手法），对光线、声音、气味、温度等感官细节的侧重优先级及融合方式。\\n- **行文节奏与呼吸感**：长短句交错的阅读律动，标点符号对语速的精准牵引（如破折号制造悬停、句号切割张力、省略号延宕情绪），段落切分的视觉节奏，以及叙事推进中“慢镜头”铺陈与冲突爆发时“快切”处理之间的动态切换。\\n- 节奏与结构技巧：场景切换的方式（蒙太奇/线性推进），对话与动作描写的配比，高潮或转折点的情绪爆发力构建手法，留白与详述的艺术。\\n- 人物塑造风格：如何通过侧面描写、微表情、潜台词展现角色性格，而非直接陈述；角色互动的张力来源（权力关系、情感流动等）。\\n- 整体基调与美学风格：是华丽繁复、极简冷淡、荒诞黑色、还是温暖治愈？语调的情感浓度如何控制？\\n\\n将以上所有风格特征高度浓缩、系统化，整合成一个完整、详细、可直接复制的通用小说作者角色卡Prompt。\\n角色卡必须以“你是一位……”开头，包含明确的“写作指令”和“禁止事项”，确保AI在生成新内容时100%遵循提炼出的文风，而非模仿原文剧情。\\n***这是最终成果的范例：\\n你是一位极具辨识度、擅长心理现实主义与氛围感营造的现代小说家。你的专长是捕捉细微的情绪流动与环境的隐喻意义，文字冷冽而精准。\\n核心写作风格锚定（必须100%严格遵守）：\\n用词偏好：偏爱冷静、克制且具象化的动词与名词，少用过度修饰的形容词。常用“灰暗”、“潮湿”、“疏离”、“破碎”等带有情绪色彩的词汇，句式多为短句，节奏紧凑有力。\\n叙事视角：坚持第三人称有限视角，紧贴主角感知。叙述口吻保持一种近乎冷酷的客观观察感，但在内心独白中流露深层的不安或渴望。\\n修辞手法：大量使用通感和隐喻，将抽象情绪转化为具体的物理感受（例如：“焦虑像蚂蚁在皮肤下爬行”）。避免直白的心理陈述，倾向于通过动作细节和环境反射来暗示心理状态。\\n环境氛围：注重“情景交融”，环境不仅是背景，更是情绪的延伸。擅长描写阴雨天、昏暗灯光、嘈杂后的寂静等具有压迫感或孤独感的场景，调动视觉、听觉与触觉的多重感官体验。\\n行文节奏控制：严格复刻范文的句式呼吸感与段落切割节奏。平缓叙事期采用绵密长句营造沉浸式流淌感；情绪对峙或动作发生期使用短促断句制造紧迫感与顿挫力；标点使用需精准牵引阅读停顿（如用句号切断张力，用破折号延宕余韵）。\\n整体基调：疏离、深沉、略带忧郁的现代主义美学，语气克制但张力十足。\\n写作指令：\\n必须通过“展示而非告知（Show, Don\'t Tell）”的手法展现人物性格与内心波动。\\n每段描写需融合至少两种感官细节，并服务于当前场景的情绪基调。\\n**行文节奏执行**：生成内容时必须严格遵循提炼出的长短句交替律动与段落切分习惯，避免平铺直叙的单一语速；在情绪蓄势阶段拉长句式与段落密度，在爆发节点使用短句与留白制造冲击力。\\n禁止：直接说明角色的心情形容词（如“他很悲伤”），禁止冗长的背景介绍插入当前叙事流中，禁止使用陈词滥调的比喻，禁止破坏已提炼的行文呼吸感。\\n现在开始，根据用户给出的角色和场景要求，直接以最高水准的文风写作。\\n***现在，请开始分析我给你的范文，直接给出人设prompt，不要给我看分析过程，不要废话。\\n\\n\\n{原文}",\n  "node_b": "{文风提示词}\\n\\n请只依据【文风提示词】自由创作一篇小说正文片段（约3500字左右）：题材、人物、场景、情节全部由你自主构思，不要模仿任何已知作品。只输出正文本身，不要标题、大纲或任何解释说明。创作的核心是让【文风提示词】中的语言质感自然流露。",\n  "node_c": "你是一个专业的非常严格的文本对比评估专家。请评估【生成文章】对比【原文】文风相似度。\\n评分唯一依据是文风质感维度：用词雅俗/密度、句式长短与节奏、修辞手法与密度、叙事视角与口吻、环境氛围营造等——只评「怎么写」，完全无视题材、情节、人物、主题等与写作技巧无关内容。\\n给出0-100的相似度评分。只输出数字分数，不要其他解释。\\n\\n【生成文章】：\\n{生成文章}\\n\\n【原文】：\\n{原文}",\n  "node_d": "我用ai根据【文风提示词】生成了【生成文章】，对比【生成文章】和原作者写的【原文】的文风的差别（忽视剧情、人物等文风无关内容的差异），争对这些文风上的差异帮我优化一下【文风提示词】让ai生成的文风能更像【原文】，只要给出修改后的提示词（文风提示词禁止出现范文中的人物姓名等内容，严禁出现行为逻辑指导如男主经常怎么做，女主经常怎么做等），我要的是文风提示词而非复制原文，禁止改变文风提示词格式，不要解释说明：\\n\\n\\n【文风提示词】：\\n{文风提示词}\\n\\n【生成文章】：\\n{生成文章}\\n\\n【原文】：\\n{原文}"\n },\n "剧情设计提取": {\n  "node_a": "你现在是一位专业的小说章节大纲分析师和角色卡设计师。\\n我提供了一篇小说的章节大纲。\\n你的任务是：\\n仔细阅读大纲，只提取章节结构设计、事件编排与节奏控制的技巧，完全忽略具体人物姓名、背景设定、具体情节线索和表层文风。\\n重点总结以下通用章节大纲设计维度（必须详细、具体、可操作）：\\n章节名设计技巧：如何通过标题制造吸引力（如：悬念反转式、核心冲突式、人物吐槽/互动式），提炼章节核心爽点或钩子的手法。\\n事件拆解与合并律动（重点提取颗粒度量化标准）：\\n单章容量控制：单章内包含的场景或冲突数量上限（是否限定在1个核心场景或1个具体冲突），明确单章事件推进的边界。\\n大事件拆解单位（含逐章微案例提取）：大事件如何按“阶段”、“情绪节点”或“回合”精细拆分，单章内具体推进到哪一步。不仅限于动作交锋，还需关注情绪与氛围的拆分。必须从提供的范文中提取1个有始有终、能用一段话说明白的“具体小事”（如“跟某人赴约”、“探索某个小山洞”，严禁提取“宗门大比”这类宏大故事线），且必须是作者大量着墨、跨越多章（至少5章以上）精细描写的长线小事件（以此展示如何把小事写长且不无聊），严禁自行编造！采用“第一章：xxx（含冲突/情绪/断章点）；第二章：xxx...”的逐章格式列出。【极度警告】：此微案例仅用于学习节奏排布与拉长技巧，AI在生成新大纲时绝对不可抄袭其中的具体剧情、人物设定等！\\n过渡事件快进处理：耗时长的修炼升级、长途跋涉、日常采买等事件在单章内占据的字句比例（如压缩至开头1-2句话），以及如何直接呈现结果并引出新冲突。\\n章节衔接与悬念钩子设计：章节开头如何承接上一章危机，章节结尾如何设置悬念（如物品丢失、强敌降临、听到心声、看到意外画面）来吸引追读。\\n场景过渡与视角切换：单章内不同场景如何通过人物行动自然过渡，章节间或章末如何切入反派/配角视角来补充信息和制造全局压迫感。\\n情绪起伏与冲突配比：单章内的情绪曲线设计（如日常起手-中段反转-高潮切断），对话、动作与日常描写的配比。\\n宏观节奏与长线架构设计：\\n大卷/大阶段划分节点：如何判断当前阶段结束，何时触发地图转换或势力阶层升级，以保持长篇新鲜感。\\n目标拆解与事件树逻辑（含完整事件中事件序列范例提取）：大目标如何拆解为中事件（跨越数十章），中事件如何拆解为单章微观动作。必须从提供的范文中提取1个与上述微案例不同的、同样符合“具体小事但跨多章精细描写”条件的事件，作为中事件跨度序列范例，严禁自行编造！采用“第n-m章：xxx”的跨度格式表达，且xxx部分必须拆解出具体动作步骤（例如：“第1-3章：主角入赘受辱并暗中蛰伏；第4-5章：努力修行遭遇瓶颈；第6-7章：意外找到突破契机...”），严禁使用“扬长避短发展优势”这类模糊的主题性总结。【极度警告】：此范例仅用于学习结构、阶段划分与转折排布，AI在生成新大纲时绝对不可抄袭范例中的具体剧情、人物设定、物品名称等任何表层内容！\\n长线悬念与套娃式钩子：跨数十章的长线悬念如何布置，何时回收旧谜团并引出更大危机/世界观，形成“套娃式”吸引力。\\n资源与修为的阶梯式升级：主角的修为、财富、势力扩张节奏如何把控，防止战力过早崩坏或长期停滞。\\n将以上所有结构特征高度浓缩、系统化，整合成一个完整、详细、可直接复用的通用小说大纲设计师Prompt。\\n角色卡必须以“你是一位……”开头，包含明确的“写作指令”和“禁止事项”，确保AI在生成新大纲时100%遵循提炼出的结构技巧，而非模仿原文剧情。\\n这是最终成果的范例：\\n你是一位极具网感、擅长情节拆解与悬念钩子设计的网文章节大纲架构师。你的专长是精准把控叙事节奏，通过“大事件拆解、水事件快进”的技巧编织高粘性的章节链条，结构紧凑且极具追读吸引力。\\n核心结构技巧锚定（必须100%严格遵守）：\\n章节名设计：采用极具网感的“悬念反转式”、“核心冲突式”短句命名。提炼本章最具冲击力的反转或核心悬念，拒绝平铺直叙的流水账命名。\\n事件拆解与合并律动（含颗粒度量化标准）：\\n单章容量控制：单章严格限定在“1个核心场景”或“1个具体冲突/情绪节点”的体量，明确事件推进的边界，禁止将跨越多日或多地的复杂事件塞入一章。\\n大事件拆解颗粒度（含逐章微案例）：大事件必须按“阶段”、“情绪节点”或“回合”精细拆分。不仅限于动作交锋，需参考从原文提取的“逐章拆解微案例”对标排布（例如：第一章：主角进入酒楼赴约，发现气氛不对（断章点：暗杀者出现）；第二章：利用地形周旋，试探对方底细；第三章：引爆炸药同归于尽（实则假死脱身）...）。【极度警告】：微案例必须提取自原文有始有终、能用一段话说明白的具体小事，且必须是跨多章（至少5章）精细描写的长线小事件，严禁瞎编！仅供学习节奏排布与拉长技巧，生成新大纲时绝对禁止抄袭其中的剧情、人物！\\n过渡事件快进处理：耗时长的修炼、赶路必须压缩至单章开头1-2句话内，直接呈现结果并引出新冲突，绝不为过渡单独成章。\\n悬念管理与钩子设计：每章结尾必须设置强悬念钩子。常用手法包括关键物品离奇丢失、突发强敌降临等，钩子必须直接指向下一章开篇。\\n场景衔接与多线交织：以主角行动轨迹作为章节内场景切换线索。章节间通过“上一章末尾危机的即时响应”进行硬切衔接。适时在章末切入反派视角，补充信息并制造危机感。\\n宏观节奏与长线架构设计：\\n大卷/大阶段划分节点：当当前地图的资源/仇恨清算完毕或修为达到瓶颈时，果断触发地图或势力阶层的转换。\\n目标拆解与事件树逻辑：遵循“大目标→中事件（数十章）→单章动作”的树状拆解。大事件不可空泛规划，必须参考从原文提取的“中事件跨度序列范例”，对标其阶段划分与转折频率，且跨度内必须包含具体的动作步骤（例如：第1-3章：主角入赘受辱并暗中蛰伏；第4-5章：努力修行遭遇瓶颈；第6-7章：意外找到突破契机与试错；第8-10章：成功突破并展露部分锋芒...）。【极度警告】：范例必须提取自原文符合上述条件的具体小事（跨多章精细描写），严禁瞎编，严禁只写主题性总结！仅供学习阶段排布，生成新大纲时绝对禁止抄袭其中的剧情、人物或任何原文内容！\\n长线悬念与套娃式钩子：每个大卷/阶段必须埋设贯穿数十章的长线悬念，在阶段高潮时解答旧谜团并引出更大危机。\\n资源与修为的阶梯式升级：严格控制修为、财富、势力的获取节奏，与当前地图的难度曲线匹配，防止战力过早崩坏或长期停滞。\\n写作指令：\\n必须以冲突或核心动作直接切入章节开头，禁止用大段背景介绍开篇。\\n处理大事件时，必须按“阶段/情绪节点”拆解出至少3章的链条，单章聚焦单次交锋、单一试探或单一氛围铺垫；处理升级等过渡事件时，必须压缩至单章内1-2句话概述。\\n规划大纲时，必须先给出该大事件的“宏观拆解链条（含中事件分配及具体推进序列）”，再细化到每章的具体动作。\\n禁止：在单章大纲中罗列平淡流水账；禁止用“经过三个月苦修”单独成章；禁止章节结尾情绪回落至平淡；禁止一章内塞入多个不相关的复杂场景；禁止抄袭两个范例中的具体剧情、人物和情绪推进原文；禁止在结构拆解时使用模糊的主题总结代替具体动作。\\n现在开始，根据用户给出的故事核心设定和总章节数要求，直接以最高水准的结构技巧输出完整章节大纲。\\n**现在，请开始分析我给你的范文，直接给出人设prompt，不要给我看分析过程，不要废话。\\n\\n\\n{原文}",\n  "node_b": "{文风提示词}\\n\\n请只依据【文风提示词】中的剧情设计技法，自主构思一个全新的故事（题材、人物、世界观完全由你决定，不要套用任何已知作品或预设情节），然后输出**前20章**的章节大纲——每一章都要写出具体的剧情设计：推进什么事件、冲突/转折怎么安排、节奏定位（铺垫/推进/高潮/余波）、章内情感节拍、章末钩子落在哪。\\n关键要求：这些设计必须是【文风提示词】中技法的**自然体现**——如果换掉题材、人物、场景，这些技法规则仍然成立；不要在章节里堆砌设定或复述技法原文，而是让技法体现在事件编排与节奏安排本身。只输出大纲，不要解释不要说明。",\n  "node_c": "你是一个专业的非常严格的**剧情设计手法**评估专家。请评估【生成文章】对比【原文】剧情设计手法确实与原作者的设计风格相似度。\\n评分唯一依据是设计手法维度：事件编排与推进方式、转折设计（误导/反转的落点）、章节节奏把控（单章容量/钩子/情绪曲线/积累-爆发循环）、冲突层级递进、悬念与回收（setup/payoff）——不评情节内容、人物、设定是否一样。\\n注意：【生成文章】是在**自由发挥**下设计的（题材/情节由AI自主构思），它必须**不依赖任何预设情节或结构模板**、仅凭剧情设计技法的规则就能独立成立；若生成大纲需要对照原文情节才能看出“手法像”，或剧情设计提示词里混入了具体题材/人物/情节设定，则给低分。\\n给出0-100的相似度评分。只输出数字分数，不要其他解释。\\n\\n{生成文章}\\n\\n{原文}",\n  "node_d": "我用ai根据【文风提示词】生成了【生成文章】，对比【生成文章】和原作者写的【原文】在**剧情设计手法**上的差异（事件编排/转折设计/节奏把控/爽点钩子布置），针对这些**手法层面的差异**优化【文风提示词】让ai的剧情设计手法更像【原文】。要求：①只优化剧情设计手法本身，**严禁把具体情节、人物、设定内容写进提示词**；②禁止删改“大事件拆解单位（含逐章微案例提取）”和“目标拆解与事件树逻辑”中的微案例；③保持提示词通用可迁移，确保不同剧情、情景、故事类型都可以适用。只要给出修改后的提示词，不要解释说明：\\n\\n当前使用的剧情设计技巧提示词：\\n{文风提示词}\\n\\nAI根据当前剧情设计技巧提示词写出的章节大纲：\\n{生成文章}\\n\\n用户提供的参考大纲：\\n{原文}"\n }\n}')

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _data_dir():
    """data/style_extract（延迟求值：安卓 bootstrap 会重定位 config.DATA_DIR）。"""
    return os.path.join(config.DATA_DIR, "style_extract")


def _safe_format(text, **values):
    """安全替换 {变量}；未识别的 {} 保持原样（提示词里可能有 JSON 花括号）。"""

    def _rep(m):
        key = m.group(1)
        return str(values[key]) if key in values else m.group(0)

    return _PLACEHOLDER_RE.sub(_rep, text)


def style_settings():
    """文风校对专用 API：设置页用途分工·文风校对四节点行（style_profiles dict，
    每节点留空跟随全局；旧单键 style_profile 兼容为四节点兜底）。"""
    cfg = config.load_config()
    sp = cfg.get("style_profiles") or {}
    if not isinstance(sp, dict):
        sp = {}
    base = str(cfg.get("style_profile") or "").strip()
    return {"profiles": {
        "node_a": str(sp.get("node_a") or base or "").strip(),
        "node_b": str(sp.get("node_b") or base or "").strip(),
        "node_c": str(sp.get("node_c") or base or "").strip(),
        "node_d": str(sp.get("node_d") or base or "").strip()}}


# ---------- 轻量相似度（字符 bigram TF-IDF + cosine，与原项目 sklearn 版趋势一致） ----------
_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+")


def _tokens(text):
    seq = []
    for m in _TOKEN_RE.finditer(text or ""):
        s = m.group(0)
        if len(s) >= 2 and "\u4e00" <= s[0] <= "\u9fff":
            for i in range(len(s) - 1):
                seq.append(s[i:i + 2])
        else:
            seq.append(s)
    return seq


class SimilarityEvaluator:
    def tfidf_cosine(self, t1, t2):
        c1, c2 = Counter(_tokens(t1)), Counter(_tokens(t2))
        if not c1 or not c2:
            return 0.0
        vocab = set(c1) | set(c2)
        idf = {w: log((2.0 + 1.0) / (1.0 + (w in c1) + (w in c2))) + 1.0 for w in vocab}
        v1 = {w: c1[w] * idf[w] for w in vocab}
        v2 = {w: c2[w] * idf[w] for w in vocab}
        dot = sum(v1[w] * v2[w] for w in vocab)
        n1 = sqrt(sum(x * x for x in v1.values()))
        n2 = sqrt(sum(x * x for x in v2.values()))
        return dot / (n1 * n2 + 1e-9)

    def evaluate(self, text1, text2, llm_score=None):
        tfidf_score = self.tfidf_cosine(text1, text2) * 100
        if llm_score is not None:
            final = 0.4 * tfidf_score + 0.6 * llm_score
        else:
            final = tfidf_score
        return {"final_score": round(final, 2), "tfidf_score": round(tfidf_score, 2),
                "llm_score": llm_score}


# ---------- 工作流 ----------
class StyleExtractorWorkflow:
    def __init__(self):
        self.prompts = self.load_prompts()
        self.similarity_evaluator = SimilarityEvaluator()

    # ---- 提示词存取 ----
    def load_prompts(self):
        p = os.path.join(_data_dir(), "prompts.json")
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data:
                    return data
        except Exception:
            pass
        return DEFAULT_PROMPTS.copy()

    def save_prompts(self, prompts):
        os.makedirs(_data_dir(), exist_ok=True)
        with open(os.path.join(_data_dir(), "prompts.json"), "w", encoding="utf-8") as f:
            json.dump(prompts, f, ensure_ascii=False, indent=1)
        self.prompts = prompts

    # ---- 预设存取 ----
    def _presets_file(self):
        return os.path.join(_data_dir(), "presets.json")

    def load_presets(self):
        try:
            with open(self._presets_file(), encoding="utf-8") as f:
                presets = (json.load(f) or {}).get("presets", {})
        except Exception:
            presets = {}
        # v1.76 内置正式版：全新安装（无 presets.json）直接带「文风提取」「剧情设计提取」两套；
        # 不落盘，保存/删除仍以用户实际存的内容为准；已有文件则完全以文件为准。
        if not presets:
            presets = {k: dict(v) for k, v in DEFAULT_PRESETS.items()}
        if "default" not in presets:
            presets = dict(presets)
            presets["default"] = {k: "" for k in ("node_a", "node_b", "node_c", "node_d")}
        return presets

    def save_preset(self, name, prompts):
        presets = self.load_presets()
        presets[name] = prompts
        os.makedirs(_data_dir(), exist_ok=True)
        with open(self._presets_file(), "w", encoding="utf-8") as f:
            json.dump({"presets": presets}, f, ensure_ascii=False, indent=1)

    def delete_preset(self, name):
        if name == "default":
            return
        presets = self.load_presets()
        presets.pop(name, None)
        os.makedirs(_data_dir(), exist_ok=True)
        with open(self._presets_file(), "w", encoding="utf-8") as f:
            json.dump({"presets": presets}, f, ensure_ascii=False, indent=1)

    def apply_preset(self, name):
        presets = self.load_presets()
        data = presets.get(name, {})
        merged = dict(self.prompts)
        for node in ("node_a", "node_b", "node_c", "node_d"):
            v = str(data.get(node, "") or "").strip()
            if v:
                merged[node] = v
        self.save_prompts(merged)
        return merged

    # ---- 主流程（yield 阶段供 UI 实时显示） ----
    def run_workflow_stream(self, original_text, max_rounds=5, threshold=80.0,
                            custom_prompts=None, stop_check=None, pause_check=None,
                            retry_evt=None):
        """v1.63 失败续跑：节点 LLM 报错（含 Response ended prematurely）不再整体终止——
        捕获后 yield ("error", {...}) 挂起，等 UI 点「继续」（retry_evt set）重试该节点，
        已跑轮次与 Top3 全部保留；停止在挂起中也立即生效（StopRequested 优先传播）。
        且每次节点调用前现读 style_settings()：暂停/报错后换 API，继续即用新配置。"""
        prompts = custom_prompts if custom_prompts else self.prompts

        # v0.83 暂停：轮次间隙挂起（不打断当前节点请求），点「继续」恢复。
        # v0.87 补停止判断：暂停期间点「停止」也会立即退出挂起（与 book_break 一致），
        # 否则停在暂停里点停止无效、必须「继续」才退出。
        def _wait_pause():
            while (pause_check is not None and pause_check()
                   and not (stop_check and stop_check())):
                time.sleep(0.2)

        # v1.63 失败续跑等待：报错后挂起，等 retry_evt 被 set（UI 点「继续」）或停止；
        # 进入先 clear（消费上次残留信号），每次报错都重新等待，不会自动跳过。
        # retry_evt 为 None 时不挂起（保持旧行为：异常直接抛给调用方）。
        def _wait_retry():
            if retry_evt is not None:
                retry_evt.clear()
            while (retry_evt is not None and not retry_evt.is_set()
                   and not (stop_check and stop_check())):
                time.sleep(0.2)
            if stop_check and stop_check():
                raise llm.StopRequested("已停止")

        def _chat_node(node, *args, **kwargs):
            """文风节点 LLM 调用：失败 yield("error") 等待「继续」重试；
            每次调用前现读该节点 API 配置（暂停后换 API 立即生效）。
            StopRequested 必须优先于 Exception 重新抛出（否则停止会被吞）。"""
            while True:
                profile = (style_settings()["profiles"].get(node) or None)
                try:
                    return llm.chat_text(*args, role="all", profile=profile, **kwargs)
                except llm.StopRequested:
                    raise
                except Exception as e:
                    if retry_evt is None:
                        raise
                    yield ("error", {"node": node, "message": str(e)})
                    _wait_retry()

        top_style_prompts = []
        all_results = []

        yield ("status", "节点A：正在分析原文文风...")
        if stop_check and stop_check():
            raise llm.StopRequested("已停止")
        user_a = _safe_format(prompts.get("node_a"), 原文=original_text)
        style_prompt = yield from _chat_node("node_a", "", user_a,
                                             think_role="style_a")
        yield ("a_done", {"文风提示词": style_prompt})

        for round_num in range(1, max_rounds + 1):
            _wait_pause()
            if stop_check and stop_check():
                raise llm.StopRequested("已停止")
            yield ("b_start", {"文风提示词": style_prompt, "round": round_num})

            user_b = _safe_format(prompts.get("node_b"), 文风提示词=style_prompt)
            generated_text = yield from _chat_node(
                "node_b", "", user_b, max_tokens=16000, think_role="style_b")
            yield ("b_done", {"生成文章": generated_text})

            if stop_check and stop_check():
                raise llm.StopRequested("已停止")
            user_c = _safe_format(prompts.get("node_c"),
                                  原文=original_text[:2000], 生成文章=generated_text[:2000])
            # v1.64：C 节点也纳入 _chat_node 统一挂起重试（任何节点报错都可点「继续」重试）；
            # 仅 LLM 调用失败才挂起，正常响应但解析不到数字仍按 50 分兜底
            llm_out = yield from _chat_node("node_c", "", user_c,
                                            max_tokens=8000, think_role="style_c")
            m = re.search(r"(\d+(?:\.\d+)?)", llm_out or "")
            llm_score = max(0.0, min(100.0, float(m.group(1)))) if m else 50.0

            ev = self.similarity_evaluator.evaluate(original_text[:2000],
                                                    generated_text[:2000], llm_score)
            score = ev["final_score"]
            yield ("c_done", {"score": score})

            result = {"round": round_num, "style_prompt": style_prompt,
                      "generated_text": generated_text, "score": score}
            all_results.append(result)

            top_style_prompts.append((score, style_prompt, generated_text))
            top_style_prompts.sort(reverse=True, key=lambda x: x[0])
            top_style_prompts = top_style_prompts[:3]

            yield ("round_end", {
                "round": round_num, "score": score,
                "top_scores": [s[0] for s in top_style_prompts],
                "top_style_prompts": [
                    {"score": s[0], "prompt": s[1], "sample_text": s[2]}
                    for s in top_style_prompts]})

            if score >= threshold:
                yield ("status", "✅ 达到阈值 %s，提前结束！" % threshold)
                break

            if round_num < max_rounds:
                if stop_check and stop_check():
                    raise llm.StopRequested("已停止")
                user_d = _safe_format(
                    prompts.get("node_d"), 文风提示词=style_prompt,
                    原文=original_text[:2000], 生成文章=generated_text[:2000])
                # v1.48 可选开关（style_d_see_top3）：允许 D 看到排名前三的提示词与分数，
                # 并在分数最高的提示词基础上改进——让 D 线性进步而不是赌哪次能做出更好的。
                if config.load_config().get("style_d_see_top3") and top_style_prompts:
                    _top_lines = ["%d. [%s分] %s" % (i + 1, s[0], s[1])
                                  for i, s in enumerate(top_style_prompts)]
                    user_d += ("\n\n【排名前三的提示词与对应分数（参考）】\n" +
                               "\n".join(_top_lines) +
                               "\n以【排名第一（分数最高）的提示词】为基线进行改进，"
                               "输出改进后的【完整提示词】（整份，包含原有全部要点与本次改进），"
                               "严禁只输出增量条目、修改建议或“在…基础上增加以下内容”式的补丁。")
                style_prompt = yield from _chat_node(
                    "node_d", "", user_d, max_tokens=16000, think_role="style_d")
                yield ("d_done", {"文风提示词": style_prompt})

        yield ("final", {
            "top_style_prompts": [
                {"score": s[0], "prompt": s[1], "sample_text": s[2]}
                for s in top_style_prompts],
            "all_rounds": all_results,
            "best_score": top_style_prompts[0][0] if top_style_prompts else 0,
            "reached_threshold": any(s[0] >= threshold for s in top_style_prompts)})
