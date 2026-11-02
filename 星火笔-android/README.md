# 星火笔 · 安卓版（v0.53 文风校对暂停·删写作技巧库·引擎同步）

把桌面端（PySide6）的 **RP 自推理小说引擎**整体复用进 Android：Chaquopy 在 App 内嵌 Python，
启动一个本机 `127.0.0.1` 本地 API 服务，WebView 加载打包的移动端前端。

- **v1.26 版本同步（与桌面 v1.54 对齐；versionCode 127）**：
  - PC **文风校对停止按钮即时反馈修复**（用户：文风校对的停止按键又不生效了；用这一版预设会触发提取的提示词有奇怪的免责声明？免责声明后面又跟着请忽视这段话——查一下；找到原因了吗？没问题就解决一下停止失效问题打包得了）：**免责声明确认为非预设问题**——全量结构扫描 presets.json/prompts.json 无任何「免责/声明/请忽视/请忽略」字样（只有正常措辞），是模型自身输出行为，无需改预设；**停止失效修复（gui_style_extract._stop）**——此前只 set 停止事件、无即时 UI 反馈，若 LLM 调用卡在网关响应按钮无任何变化、体感"不生效"；修复为点停止立即禁用按钮+提示「⏹ 正在停止…」，worker 抛 StopRequested 后 done→cleanup 正常复位；
  - 本轮为 **PC GUI 修复（gui_style_extract.py）**，安卓引擎无改动，**仅版本号同步重建 APK**（versionCode 127，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.26 条目；gitlink → 内层（见 PC 提交）。
- **v1.27 引擎同步（与桌面 v1.55 对齐；versionCode 128）**：
  - PC **提取预设防污染·D节点强制完整提示词**（用户：还是不行，预设肯定有问题，提取结果完全就是乱罗列，还带莫名其妙的话）：**根因①** config `style_d_see_top3` 被开启成 True（默认关、防发散）→ 源码给 node_d 追加「在排名第一基础上改进、而不是重写」→ 剧情设计提取 top1/top2 变成「在第二十七节末尾增加以下内容」的增量补丁而非完整提示词；**根因②** node_d 缺【产出严禁】防污染条款 → 文风提取 top2/top3 混入「你好，我无法给到相关内容。」拒绝语；**修复**=style_extract.py see_top3 追加措辞改为强制输出改进后的**完整提示词**（严禁增量补丁）+ presets/prompts 的 node_d 补【产出严禁·输出形态】条款（禁开场白/拒绝语/补丁式）+ config 开关关回默认 False；verify_v155.py **ALL_OK 26 项全过**；
  - 本轮 **style_extract.py 整文件同源同步**（see_top3 措辞改动），重建正式签名 APK（versionCode 128，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.27 条目；gitlink → 内层（见 PC 提交）。
- **v1.28 版本同步（与桌面 v1.56 对齐；versionCode 129）**：
  - PC **提取预设·回归心动可乐满意版格式**（用户：心动可乐里是我最满意的一版预设，唯独剧情设计会有剧情污染和文风校对会有情绪描写场景固化问题，但其他基本上都很不错，但你这一版格式也乱了、效果也很一般，最好参考之前的版本。得格式化输出！！如果有补充内容也有专门的格式名目来写）：以用户放回 `心动可乐/预设（最满意但剧情污染）/` 两份 json 为唯一基底重建 node_a——**恢复心动可乐版格式化名目**（【什么是技法/风格】【提炼维度】【情绪浓度适配】【产出要求】【严禁】，找回 setup/payoff/情感节拍/冲突层级递进，v1.52 版丢这些名目即"格式乱了"）；**剧情污染修复=源头强化**（技法必须脱离本小说独立成立 + 严禁把原文桥段/微案例摘入产出 + node_b 防复述 + node_d 防新增原文桥段）；**文风情绪场景固化修复=【情绪场景防固化】专门名目**；量化节奏细节以【量化节奏参考】名目保留；node_d 保留 v1.55 防补丁条款；verify_v156.py **ALL_OK 40 项全过**；
  - 本轮为 **PC 预设数据文件优化（data/style_extract 随 PC zip）**，安卓引擎无改动，**仅版本号同步重建 APK**（versionCode 129，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.28 条目；gitlink → 内层（见 PC 提交）。
- **v1.29 版本同步（与桌面 v1.57 对齐；versionCode 130）**：
  - PC **提取预设精简·回归原文形态**（用户：哈？我怎么感觉就是你在提取文风的提示词里加了一大堆用中括号括起来的说明才搞得ai提取的时候也爱搞说明啊，原本的提示词哪有这样搞的）：**根因确认**=预设里堆多少【】名目和说明，模型提取时就越爱模仿"说明文"结构（v1.56 新增【情绪场景防固化】【量化节奏参考】大段名目教坏了模型输出形态）；**精简**=node_a 回归心动可乐版原文——文风一字不差（935 字，已有情绪浓度适配防固化）、剧情原文+三处半句（防污染「技法必须能脱离本小说」+量化「10~15%/50~60%/25~40%」+防微案例「严禁把原文桥段摘入产出」），node_d 保留 v1.55 防补丁条款；verify_v157.py **ALL_OK 23 项全过**；
  - 本轮为 **PC 预设数据文件优化（data/style_extract 随 PC zip）**，安卓引擎无改动，**仅版本号同步重建 APK**（versionCode 130，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.29 条目；gitlink → 内层（见 PC 提交）。
- **v1.30 版本同步（与桌面 v1.58 对齐；versionCode 131）**：
  - PC **提取预设·详细度与迭代稳定性**（用户：确定迭代也没有问题吗？很多问题是D迭代产生的，而且越迭代越严重；还有，文风提取这么短嘛？479字？认真的？）：**质疑②成立**——文风 node_a 没要求每个维度展开写，商汤提取仅 479 字（满意版 1300+ 字）；修复=node_a 内嵌「每个维度必须展开写具体、完整角色卡形式输出、务必详细丰富」，**商汤复测 479→2043 字**（你是一位…开头/零污染/零说明文/含情绪浓度适配）；**质疑①成立且抓到实锤**——`style_d_see_top3` 又被开启成 True（D 每轮拿第一名+分数叠加改进、越叠越偏）+ node_d 无防收缩条款；修复=开关关回默认 False + node_d 补【防越改越短】条款（篇幅不得短于当前提示词、不得删减成提纲）；verify_v158b.py **ALL_OK**、商汤实测文风 2043/剧情 2682 字；
  - 本轮为 **PC 预设数据文件优化（data/style_extract 随 PC zip）**，安卓引擎无改动，**仅版本号同步重建 APK**（versionCode 131，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.30 条目；gitlink → 内层（见 PC 提交）。
- **v1.31 引擎同步（与桌面 v1.59 对齐；versionCode 132）**：
  - PC **文风停止立即断开 + 主AI笔记详细化**（用户：文风校对的停止按键又变成要等当前节点生成结束才能停了，我不是说了立即发送停止指令停止嘛；还有主AI笔记太简略，我要归纳概括前面写过的内容、各项信息，至少我看了主AI笔记要知道前面发生了一些什么事吧）：**①停止立即断开**（llm.py 引擎双端同源）——之前只修 UI 即时反馈，llm 请求阻塞等流式首包时 `_abort_check` 要等下一分片 → 停止仍等当前节点生成完；修复=llm 新增活跃响应注册表 `_register_resp/_unregister_resp` + `abort_active_resps()`（点停止立即 close 全部在途连接，阻塞读立刻抛异常）+ 读取主体 try/finally 配平 + ChunkedEncodingError/ConnectionError 若 abort 置位直接转 StopRequested，GUI `_stop` set 事件后调 `abort_active_resps`；**②主AI笔记详细化**（prompts.py 双端同源）——compress_summary 从「压缩400-600字、必须更短要点更密」改为「按剧情脉络归纳概括 800~1500 字：起因→经过→结果、涉及谁、对关系/局势影响、当前各角色处境、伏笔已埋/待回收、未兑现承诺，旧笔记有效前情必须完整保留」，GUI 摘要弹窗文案同步；verify_v159.py **ALL_OK 23 项全过**（双端同源 MD5 一致）；
  - 本轮 **llm.py + prompts.py 整文件同源同步**（停止立即断开 + 笔记详细化引擎能力安卓随之具备），重建正式签名 APK（versionCode 132，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.31 条目；gitlink → 内层（见 PC 提交）。
- **v1.32 引擎同步（与桌面 v1.60 对齐；versionCode 133）**：
  - PC **角色推理引导补强**（用户：主AI会不会参考运用角色推理的人物逻辑并引导人物行为逻辑啊？怎么感觉更新迭代到目前版本后主AI好像都不在乎角色推理的结果？角色推理保证人物行为逻辑和故事逻辑，主AI在知道剧情走势的情况下通过改变小事件的引导/细节来导向内容不偏离主纲，这一套逻辑怎么感觉被淡化了）：链路逐段确认**完整在位未删除**（char_ai 推理引擎→engine ③ 传 inferences 给 consolidate→【各角色推理结果】注入主AI→verdict=adjust 改小事件并重推全体角色→write_chapter【各角色行为指导】+【遵循要求】强制落地）；**"被淡化"实锤**=prompts.consolidate 任务1 原文只有「判断合力方向是否符合主线」一句，没要求主AI逐条消化每个角色的推理结果来引导本章小事件/细节；修复=任务1 改为「**逐条消化【各角色推理结果】**…**本章的 chapter_beats、approved_direction 与小事件/细节引导必须以这些推理结果为基础**——人物在正文中的行为逻辑来自角色推理，主AI负责用事件引导让剧情沿主线走、同时不违背人物行为逻辑」；verify_v160.py **ALL_OK 12 项全过**（编译 + 新措辞 3 + 推理链路锚点 5 + 双端 prompts 同源 MD5 一致）；
  - 本轮 **prompts.py 整文件同源同步**（consolidate 任务1 消化推理引导），重建正式签名 APK（versionCode 133，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.32 条目；gitlink → 内层（见 PC 提交）。
- **v1.33 引擎同步（与桌面 v1.61 对齐；versionCode 134）**：
  - PC **停止彻底修复·except 顺序严重 bug**（用户：有做bug检查吗？简单检查一下这两次改动是否留下bug）：**bug 专项检查**（verify_bugcheck_v160.py）抓到 v1.59 引入的严重问题——`llm._do_post` 外层 try 的 handlers 顺序曾是 `['Exception', 'ChunkedEncodingError', 'ConnectionError']`，`except Exception` 排第一位会**吞掉 StopRequested 与 abort close 连接异常**，把点停止当成成功空响应返回（用户反复反馈的"停止要等当前节点/完全失效"深层根因，v1.54/v1.59 修复叠加后才彻底闭合）；修复=外层 handlers 重排为 `['StopRequested', 'ChunkedEncodingError', 'ConnectionError']` + finally `_unregister_resp`（AST 复验通过）+ 清理 v1.59 拼接残留的重复 return；verify_bugcheck_v160.py **ALL_OK 24 项全过**（编译/双端同源/AST handlers 顺序/gui _stop 链路/笔记与推理措辞）；
  - 本轮 **llm.py 整文件同源同步**，重建正式签名 APK（versionCode 134，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.33 条目；gitlink → 内层（见 PC 提交）。
- **v1.47 AI 对话补齐（与桌面 v1.75 对齐；versionCode 148——用户：蛮好看的，安卓版好像还缺了个ai对话，补一下）**：安卓端新增 **AI 对话** 页，与桌面 `gui_chat` 全功能对齐（后台**复用 PC 同源** `chat_lib.py` + `web_search.py`，MD5 校验一致）：
  - **后端（android_server 新增 13 个 `/api/chat_*` 路由）**：话题 CRUD（`chat_topics`/`chat_create`/`chat_open`/`chat_rename`/`chat_delete`）+ 发送 `chat_send`（无话题自动兜底创建，用户消息先落库，流式分片写任务日志 kind=**chunk**/think，完成时 `chat_lib.append_message` 写回 assistant 消息含思考，失败/停止不写回）+ `chat_continue`/`chat_regen`/`chat_edit_last`/`chat_delete_last`（语义同桌面 LM Studio 式消息操作：重生成=删最后一条 AI 回复用其前一条用户消息重发；编辑用户消息后前端自动重生成）+ `chat_stop`（v1.43 停止红线：置停止事件 + `llm.abort_active_resps()` 立即断流）+ `chat_export`（导出 md + 弹系统分享）；系统提示组装同桌面 `_chat_system()`（**读当前项目不含正文** / 🌐 联网搜索注入结果 / 已压缩摘要）；
  - **前端（WebView）**：底部导航新增「AI对话」入口（`.ic-chat` 内联 SVG 图标）+ 对话页（话题列表+搜索 / 气泡左右布局 / 🧠 思考折叠块 / 流式打字机 400ms 轮询任务日志 / 消息操作四键 / ⏹ 停止 / 导出）+ 设置页「**AI 对话 API 配置**」下拉（config `chat_profile`，留空跟随全局——`llm.chat(role="chat", profile=...)`）；全部新样式走主题变量（三套配色自动适配）；
  - **验证**：服务端路由冒烟 **ALL_OK 20 项**（话题 CRUD + 发送链路轮询 done + 无 API Key 失败路径不触网 + 停止幂等 + 导出/设置错误路径）+ `py_compile` ALL_OK（android_server/chat_lib/web_search）+ `node --check app.js` + 前端接线核对 ALL_OK（9 个 chat-* id / onclick / window 导出全对位）+ 换肤自检 39 项 ALL_OK（对话样式无硬编码色）；按用户要求代码级验证、未跑实例；
  - 重建正式签名 APK（versionCode 148，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 78 文件（新增 chat_lib.py，web_search.py 既有在本工程、本轮同源 MD5 核对一致；APK 单独成对）；README 加 v1.47 条目；gitlink → 内层（见 PC 提交）。
- **v1.49 版本同步（与桌面 v1.77 对齐；versionCode 150）**：本轮功能在 PC 端（用户：能不能在start.bat启动后不显示命令行，直接启动ui？——`start.bat` 改用 `pythonw.exe` 无控制台启动，双击直接出 UI；`main.py` 加启动异常兜底写 `data/launcher_error.log` + 弹窗）。安卓端无功能改动，仅版本号同步对齐（versionCode 150 / 1.49）；重建正式签名 APK（CN=XinghuoPen 同签名可覆盖安装）+ zip 归档（APK 单独成对）；README 加 v1.49 条目；gitlink → 内层（见 PC 提交）。
- **v1.48 教程全盘更新 + 正式版预设内置（与桌面 v1.76 对齐；versionCode 149——用户：把这个写进教程里，另外就是项目教程好像很久没有更新了吧，你全盘更新一下教程吧。还有就是从这次更新的版本开始我打算发GitHub了，除了更新的我自用的安卓和pc版本外，加一个源码压缩包和无项目痕迹的pc和安卓版本，用独立的文件夹存放）**：PC **教程全盘更新 + 正式版预设内置 + 首版 GitHub 发布包**（PC 9 分页 / 安卓 8 分页覆盖全部功能；文风/剧情设计两套正式版提取预设以 `DEFAULT_PRESETS` 内置进 `style_extract.py`；`GitHub发布/` 独立文件夹 5 件——源码包/无痕电脑端/无痕安卓 APK/无痕安卓工程/发布 README）。**安卓端同步**：①`index.html` 教程段全盘重写为 **8 个分页**（快速上手/写作/角色/项目/AI对话/文风·模板/拆书/设置）——新增 AI 对话、文风·模板两页；「文风·模板」页内置**两套正式版提示词 node_a 全文**（文风提取/剧情设计提取）与**配套的文风/剧情设计泛化提示词模板**（去题材/去时代/防照抄，可整段复制）；写作/项目等页更新写后校对、一键成书-AI自动判断章节数、界面风格等描述；②`style.css` 新增教程页样式（`h4/.step/.tut-preset/.tut-code`，全走主题变量，三套配色自动适配）；③`app.js` `tutShow` 分页数组扩为 8 项；④`style_extract.py` 与 PC **同源同步 MD5 一致**（内置两套正式预设，全新安装即有，用户数据文件存在时仍以文件为准）。**验证**：教程专项 **ALL_OK 11 项**（PC 9 分页 / 安卓 8 分页 / 片段 4 块 / 泛化模板在位 / `node --check app.js`）+ 换肤自检 39 项 ALL_OK（教程新样式无硬编码色）+ 内置预设行为验证 ALL_OK（无 presets.json 兜底出两套）+ APK 产物级校验（app.imy 含 style_extract.pyc、教程 8 分页与提示词片段在位、aapt2 versionCode 149 / 1.48、验签 CN=XinghuoPen）；代码级验证未跑实例；重建正式签名 APK（versionCode 149，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 78 文件（APK 单独成对）；`GitHub发布/` 无痕安卓 APK 与工程 zip（剔签名/本地配置/构建产物）；README 加 v1.48 条目；gitlink → 内层（见 PC 提交）。
- **v1.46 界面美化·三套配色可切换（与桌面 v1.74 对齐；versionCode 147）**：PC **界面美化**（用户：帮我美化一下ui界面，不要改动任何功能，只美化ui，往可爱风、二次元风方向修改；可以都做，到时候给个切换选择就行了；别忘了安卓和pc都得美化哦）——三套配色 🌸 樱粉软萌（浅，默认）/ 🌿 薄荷奶油（浅）/ 🌙 二次元夜（深）：PC `gui_theme.py` 提炼 85 语义色槽 × 3 主题 + QSS 全 `%(角色)s` 模板 + 界面历史硬编码色统一经 `T()` 调用时换算（138 处包装，幂等可跨主题重映射）+ 语气/角色高亮器 `retint_all()` 随 `recolor()` 重着色 + 设置页顶部「界面风格」单选即时生效并持久化（config `ui_theme`）；`verify_theme_v174.py` **ALL_OK 38 项** + 20 文件 `py_compile` ALL_OK。**安卓端同步换肤（WebView 前端，零功能改动）**：①`style.css` 全面变量化——文件头三主题变量块（`:root, html[data-theme="sakura"]` / `html[data-theme="mint"]` / `html[data-theme="night"]`，各 47 个变量：底色/光晕/文字阶/强调色/卡片/描边/输入/按钮/状态色等），散落的 87 处 hex + 18 处 rgba 全部换 `var()`（半透明走 `rgba(var(--xxx-rgb), a)`），变量块之外无硬编码色残留（头像描边也改用 `--ring`）；②`index.html` 设置页新增「界面风格（只换配色，不改功能）」三段按钮卡片 + `meta name=theme-color`（随主题改状态栏色），三处内联色改 `var()`；③`app.js` 新增界面风格模块——`getUiTheme/applyUiTheme/setUiTheme/initUiTheme`（写 `document.documentElement.dataset.theme`、切按钮选中态、`localStorage('xinghuo_theme_v1')` 记忆、默认即樱粉避免首帧闪烁），启动即应用并暴露 `window.setUiTheme`；**只换皮肤不改功能**，API 接口/路由零改动。**验证**：安卓侧专项自检 **ALL_OK 39 项**（三主题变量集合完全一致 + 无未定义变量引用 + 无残留字面量色值 + 花括号配平 + HTML 接线 + JS 主题逻辑/持久化/启动顺序 + `node --check app.js` 通过）+ **打包产物级验证**（APK 内 `assets/www/{style.css,app.js,index.html}` 三主题块/`setUiTheme`/风格卡片实测在位，`aapt2 dump badging` 确认 versionCode 147 / versionName 1.46）+ APK 验签 `CN=XinghuoPen`；顺带 `main_ai.py` 与 PC 同源（`plan_chapters` 的 StopRequested 兜底，MD5 校验一致）；重建正式签名 APK（versionCode 147，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.46 条目；gitlink → 内层（见 PC 提交）。
- **v1.45 引擎同步（与桌面 v1.73 对齐；versionCode 146，一键成书「AI 自动判断章节数」）**：PC **一键成书「AI 自动判断章节数」**（用户：把ai一键成书的功能里的目标章节数，加一个让ai自动判断章节数，对应的写到多少章同样适应性修改一下）：`prompts.plan_chapters_ai()`（按剧情量/卷划分定篇幅，用户已给数字直接遵循，只输出 `{"chapters": N}`）+ `main_ai.plan_chapters()`（chat_json + clamp [1,3000]，失败回退手填值再默认 30）；`BookPanel` 加「AI 自动判断章节数」勾选（禁用两个 spin），`_BookWorker.run` 三栏设定后调 plan_chapters 让 chapters 跟随判断值；**安卓 `android_server.book_start` 读 `auto_chapters` 参数、三栏设定后调 `main_ai.plan_chapters` 替换 total/chapters**（WebView 前端加勾选由前端层跟进，接口已支持）；verify_v173.py **ALL_OK 32/32**（双端编译 + 提示词四要素 + clamp/回退/chat_json + GUI 勾选/禁用/传参 + 引擎调用 + 安卓同步 + 版本号 + 双端 MD5）+ `_smoke.py` 全量 ALL_OK 回归通过（期间修复 gui_book 缺 QCheckBox 导入）；本轮 **prompts.py + main_ai.py 整文件同源同步**（MD5 校验一致）；重建正式签名 APK（versionCode 146，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.45 条目；gitlink → 内层（见 PC 提交）。
- **v1.44 引擎同步（与桌面 v1.72 对齐；versionCode 145，码字任务上下文补故事设定）**：PC **码字任务上下文补故事设定**（用户质疑：码字页面的ai你不能看到世界观、剧情规划这些主ai能看到的内容，应该不会只能看到主ai笔记吧——核实确认 v1.68 真漏了：续写/段落工具只注入主AI笔记四件套，主AI 通过 fmt_story 注入的【剧情发展】【世界观】【特殊规则】没给码字任务）：`prompts.writing_ctx_blocks()` ctx_notes 开关下新增 `_story_setting_blocks()`——注入剧情发展（story_brief，旧版项目自动走 opening+卷规划拼接）/世界观（story_world）/特殊规则（story_rules），与主AI fmt_story 三栏语义一致"任务须贴合不得违背"，每栏限长截断防 token 爆炸；三处开关文案改名「故事设定+主AI笔记」；verify_v172.py **ALL_OK 24/24** + 行为测试 verify_v172_ctx.py ALL_OK + `_smoke.py` 全量 ALL_OK 回归通过；本轮 **prompts.py 整文件同源同步**（MD5 校验一致），重建正式签名 APK（versionCode 145，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.44 条目；gitlink → 内层（见 PC 提交）。
- **v1.43 停止立即生效（与桌面 v1.71 对齐；versionCode 144——用户澄清：停止按钮要的是直接停止，从没说过要等本章完成）**：PC 全部 7 个 LLM 任务停止入口统一为「置停止事件 + `llm.abort_active_resps()` 立即断流」（主动 close 在途请求连接，流式读取立刻抛 StopRequested 传播回 UI），不再等当前章/轮/节点结束；删除全部延迟停止文案；AST 精确扫描确认传播链路 0 处异常；`_smoke.py` 全量 ALL_OK 回归通过。**安卓端同步**：`android_server` 四个停止路由（`_do_book_stop`/`_do_break_stop`/`_do_stylecheck_stop`/`_do_import_stop`）此前只置 `stop_ev`（等当前任务环节自然结束），补 `llm.abort_active_resps()` 立即断流；verify_v171.py **ALL_OK 19/19**（含安卓端编译）；重建正式签名 APK（versionCode 144，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.43 条目；gitlink → 内层（见 PC 提交）。
- **v1.42 安卓功能修复（与桌面 v1.70 对齐；versionCode 143——模拟器真机实测驱动的致命修复，用户：安卓版我用起来全是bug很多功能完全没法用，太抽象了）**：
  - **验证环境**：安装 Android emulator + android-34 x86_64 系统镜像 + AEHD 硬件加速驱动（UAC 提权），创建 AVD xhb_test 无窗口启动，安装 APK 实测；
  - **致命 bug①：API 全被 CORS 拦截（"所有功能没法用"根因）**——WebView file:// 页面（origin=null）fetch `http://127.0.0.1:<port>/api/*`，`android_server._send` 无 CORS 头 → 浏览器策略拦截全部 API 请求（logcat 实测 `No 'Access-Control-Allow-Origin' header` 刷屏）。修复：`_Handler._cors_headers()`（Allow-Origin/Methods/Headers）+ 全部响应附带 + `do_OPTIONS` 预检放行；**实测 adb forward 后 API 12 项全通**（state/settings/建项目/角色/草稿/日志/时间线/统计/404）；
  - **致命 bug②：导航/按钮 SVG 图标全空白**——`style.css` 的 `url(icons/*.svg)` 被 file:// CORS 拦截；Android 12+ 对 targetSdk≥30 release **强制禁用** WebView file 跨源（Java 设置无效）→ 33 处图标**全部内联 data:image/svg+xml;base64**；Java 侧仍补 `setAllowUniversalAccessFromFileURLs/setAllowFileAccessFromFileURLs(true)` 双保险；截图+像素分析确认底部导航 8 图标全部渲染、页面切换生效；
  - **顺带修复**：`_android_check.py` 段落工具 mock 未同步 v1.68 的 `store=` 参数 → 补齐 `**kwargs`（此前 v020 段落润色/扩写 2 项 FAIL）；
  - **实测**：`_android_check.py` **235 项全过**；WebView console 零 CORS 错误；重建正式签名 APK（versionCode 143，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.42 条目；gitlink → 内层（见 PC 提交）。
- **v1.41 引擎同步（与桌面 v1.69 对齐；versionCode 142，码字 AI 上下文补齐：用途分工「码字AI」+ 三开关可见）**：PC **码字 AI 任务上下文补齐**（用户：没看到api设置界面设置码字api用哪个的地方啊，而且码字界面也没看到你说的三开关配置任务上下文啊）：①**用途分工新增「码字AI（续写/段落工具）」行**（role=write_tool，未指定跟随正文写作）——`main_ai.polish_paragraph()` 每次调用前现读 `role_profiles["write_tool"]` 显式传 `profile=`（未配置走正文写作），安卓 polish 路由随之受益（安卓 webview 选配置仍走 role_profiles）；②**码字页「任务上下文」三开关可见可调**（正文AI文风/主AI笔记/人物读取推理，与设置页同键 tool_ctx_*，改动即存，旁有「设置页…」跳转）；③**段落工具对话框内同款三开关**（打开回填、改动即存）；verify_v168b.py **ALL_OK 23 项全过**（双端编译 + write_tool 行/label + main_ai 读 write_tool 传 profile + 码字页三开关/回填/保存/跳转 + WriteWorker 读 write_tool + 对话框三开关 + main_ai 双端 MD5 同源），代码级验证未跑实例；本轮 **main_ai.py 整文件同源同步**（MD5 校验一致）；重建正式签名 APK（versionCode 142，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.41 条目；gitlink → 内层（见 PC 提交）。
- **v1.40 引擎同步（与桌面 v1.68 对齐；versionCode 141，码字 AI 任务上下文可配置 + 章节快照）**：PC **码字 AI 任务上下文可配置**（用户：ai在进行续写、缩写、改写等工作的时候是否应用正文ai的提示词和文风要求，以及ai是否读取主ai笔记，是否会对续写等涉及到的人物进行读取推理等都得要能设置啊，不然ai段落处理、续写就没有灵魂了啊。而且这些要求得是选择性是否开启的，毕竟有时候为了省一些token，没必要什么任务都开。自动角色卡和主ai笔记必须自动完成，万一api出问题了还得有对应章节重新更新角色卡和主ai笔记的功能，另外别忘了章节快照）：①**三开关可配置任务上下文（默认全开省 token 可关）**——config 新增 `tool_ctx_style`（正文AI提示词与文风要求：story_writer_prompt + 文风参考/风格要点）/`tool_ctx_notes`（主AI笔记：管理笔记+重要角色档案+灵感+知识库）/`tool_ctx_rp`（涉及人物读取推理：按近几章出场+笔记点名角色卡读取并推理行为/语言/情绪）；设置页「常用」新增「码字 AI 任务上下文」三复选框（防抖自动保存+回填）；②**段落工具接入**——`prompts.polish_paragraph()` 新增 `ctx_style/ctx_notes/ctx_rp/store` 参数并抽出 `writing_ctx_blocks()` 公共组装，`main_ai.polish_paragraph()` 现读 config 透传，`_PolishWorker` 持 store 开启人物读取推理；③**续写接入**——`gui_write._continue_prompt()` 新增 store 并读三开关，注入「【任务上下文】」段，`WriteWorker.run`/`_continue` 透传 store；④**手动重跑角色卡/主AI笔记**——码字页章节目录新增「⟳ 重跑本章角色卡/笔记」按钮（API 出错补救，后台复用 `_bg_auto_work` 防并发排队）；⑤**章节快照**——`_bg_auto_work` 完成后 `save_world_snapshot(chapter.index)`（与 finalize_chapter 存档节奏一致，供重写/回滚）；verify_v168.py **ALL_OK 52 项全过**（11 文件编译 + 三开关 + writing_ctx_blocks 四段 + polish 链路 + 续写注入 + rerun/防并发 + 快照 + 设置页存取 + 版本号 + 双端 MD5），代码级验证未跑实例；本轮 **prompts.py + main_ai.py + config.py 整文件同源同步**（MD5 校验一致），**安卓 polish 路由改传 store**（安卓无设置页按 tool_ctx_* 默认全开）；重建正式签名 APK（versionCode 141，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.40 条目；gitlink → 内层（见 PC 提交）。
- **v1.39 引擎同步（与桌面 v1.67 对齐；versionCode 140，码字页三连）**：PC **码字页三连**（用户：ai段落工具那里为什么不支持输入提示词来控制缩写或者去ai味之类的效果要求呢？续写也是，我总得告诉ai续写什么内容吧？纯靠抽奖也太坐牢了。还有我自己写的章节，角色卡和主AI笔记这两个功能做了自动化处理没有？比如我保存后自动做这两方面处理，但不能影响我写下一章）：①**段落工具附加要求**——`prompts.polish_paragraph()` 新增 `directive=""` 参数（非空注入「【用户附加要求（优先级最高，必须在结果中落实）】」，位于待处理段落之后 style_note 之前），`main_ai.polish_paragraph()` 透传，`PolishParagraphDialog` 加「附加要求（可选）」输入框 + `_run()`/`_PolishWorker.run` 4 参签名透传；②**AI 续写提示词**——码字页续写行新增「想写什么（可选）」输入框（placeholder：男主与师妹重逢，引出误会…），`_continue_prompt()` 非空注入「【用户指定方向（优先级最高，必须满足）】」，`WriteWorker.run`/`_continue` kwargs 透传；③**保存后自动角色卡/主AI笔记后台异步**——保存成功后 daemon 线程 `_bg_auto_work` 仿 engine.finalize_chapter 战后更新（`main_ai.update_world`→`engine._apply_world_updates` + `main_ai.compress_summary`→写回 story_summary/story_characters/story_ideas/story_knowledge + `_apply_archive_suggestions` + `save_project`），**不阻塞写下一章**（「已保存。后台更新角色卡/主AI笔记中…（可继续码字）」），`_bg_busy` 防并发 + `_bg_pending` 排队补处理，任一步 LLM 失败只记日志不影响另一项；verify_v167.py **ALL_OK 43 项全过**（编译 + directive 四层链路 + 续写透传 + 异步/防并发/写回五处 + 版本号 + 双端 MD5 同源），代码级验证未跑实例；本轮 **prompts.py + main_ai.py 整文件同源同步**（MD5 校验一致），重建正式签名 APK（versionCode 140，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.39 条目；gitlink → 内层（见 PC 提交）。
- **v1.38 版本同步（与桌面 v1.66 对齐；versionCode 139，新增「码字」页——安卓为 WebView 前端无对应 GUI，仅版本号同步）**：PC 新增码字页（用户：帮我做一个单独的码字的页面，要包含ai续写等ai写小说码字界面该有的功能都得有，放在从上到下第二个功能页）：导航第二位新增「码字」页（gui_write.py，index=1，项目之后角色之前）；章节目录/标题+正文大编辑区/字数统计/「＋新建下一章」/「💾保存」（复用引擎 edit_chapter，旧稿备份草稿箱+git 归档）/「自动保存30秒」；「✍ AI 续写」（光标衔接续写 100–2000 字，后台 llm，可停止，StopRequested 优先）/「✨ AI 段落工具」（复用 PolishParagraphDialog：润色/扩写/缩写/去AI味）；页面索引整体 +1（情景提示词 10→11，依次后移）；verify_v166.py **ALL_OK 29 项全过**；安卓端仅重建正式签名 APK（versionCode 139，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.38 条目；gitlink → 内层（见 PC 提交）。
- **v1.37 版本同步（与桌面 v1.65 对齐；versionCode 138，移除 Agent 功能——安卓本无 Agent，仅版本号同步）**：PC 删除 Agent 功能（用户：帮我把 agent 功能直接删了吧，这玩意好像不太用得到）：删 `src/gui_agent.py` 整页 + 导航/设置页用途分工「Agent」行 + `chat_lib.py` Agent 会话与 Qwen 工作区区（保留对话页用的 export_topic_md/build_project_context/context_window）+ `_smoke.py` 相关断言段；页面索引重排（情景提示词 11→10，gui_book/gui_project switch_page 同步）；安卓端无 Agent 功能（app.js/android_server.py 无引用、无 chat_lib.py），仅重建正式签名 APK（versionCode 138，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；verify_v165.py **ALL_OK 13 项全过**；README 加 v1.37 条目；gitlink → 内层（见 PC 提交）。
- **v1.36 引擎同步（与桌面 v1.64 对齐；versionCode 137）**：
  - PC **文风校对四节点续跑统一 + 拆书工坊 txt 显示/清除**（用户：①现在出任何报错都可以直接点继续来重试继续工作了吗？②暂停截断调整的设置得生效——比如暂停后换了 API、思考强度调整、是否 D 助手优化参考 top3 提示词，继续时要用新的 ③拆书工坊导入 txt 文件后去掉已导入的 txt、更换 txt 文件显示不明显，我只能再点导入，容易产生歧义，显示也没区别）：①**C（评分）节点也纳入 `_chat_node` 统一挂起**——A/B/C/D 四节点任何 LLM 报错都挂起、点「继续」重试同一节点（已跑轮次与 Top3 全保留），不再被静默按 50 分跳过；②API/思考强度/D 参考 Top3 每处**每次调用前现读**，暂停/报错期间改设置保存 → 继续 → 立即用新值；③拆书工坊导入按钮旁新增**当前文件标签**+「✕ 清除已导入」按钮（回到未导入状态可重选），更换 txt 一眼可辨；verify_v164.py **ALL_OK 18 项全过**（双端 style_extract.py 同源 MD5 一致）；
  - 本轮 **style_extract.py 整文件同源同步**（四节点续跑/每次现读引擎能力安卓随之具备），重建正式签名 APK（versionCode 137，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.36 条目；gitlink → 内层（见 PC 提交）。
- **v1.35 引擎同步（与桌面 v1.63 对齐；versionCode 136）**：
  - PC **文风校对报错续跑 + 换 API 即时生效**（用户：文风校对有时候会报错「X 请求异常： Response ended prematurely」——报错后只能重新开始，之前跑的成果白跑，只能导出当前的前三，没法继续迭代；就不能出了报错后直接继续就能继续重试吗？另外暂停后更改设置能生效吗？比如暂停后换了 API 然后继续，是用新的 api 吗？）：**根因①（报错白跑）**=run_workflow_stream **无续跑机制**——任一节点 LLM 调用报错（`Response ended prematurely`=流式读取中连接被网关掐断、llm 层重试耗尽后抛 LLMError）直接冒泡终止整个生成器，all_results/top_style_prompts 全丢只能重来；**根因②（暂停后换 API 不生效）**=`profiles = style_settings()["profiles"]` 流程开始时**只读一次**，A/B/C/D 全程用旧配置快照，暂停/继续不重读换 API 无效；**修复（style_extract.py 引擎双端同源）**=①`run_workflow_stream` 新增 `retry_evt` 参数，节点调用包进 `_chat_node`——失败不再整体终止，改 `yield ("error", {node,message})` 挂起等 UI 点「继续」（set retry_evt）**重试同一节点**，已跑轮次与 Top3 全保留；挂起期间点「停止」立即生效（`_wait_retry` 内 StopRequested 优先、retry_evt=None 时保持旧行为直接抛）；②`style_settings()` 改**每次节点调用前现读**（A/B/C/D 全现读 profile）——暂停/报错后换 API 继续即用新配置；verify_v163.py **ALL_OK 21 项全过**（编译 + retry 机制 7 项 + 配置现读 5 项 + GUI 4 项 + 双端 style_extract.py 同源 MD5 一致）；
  - 本轮 **style_extract.py 整文件同源同步**（报错续跑/换API生效引擎能力安卓随之具备），重建正式签名 APK（versionCode 136，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.35 条目；gitlink → 内层（见 PC 提交）。
- **v1.25 版本同步（与桌面 v1.53 对齐；versionCode 126）**：
  - PC **提取预设·修复混搭**（v1.52 最终核对发现两处问题后升版重打——①prompts.json 当前生效值 node_b/c/d 仍是剧情设计提取版、与 node_a 文风版混搭，文风校对工坊 A 用文风、B/C/D 用剧情会错乱；②文风 node_a 缺【严禁】出现具体内容的硬性防污染条款）：修复①prompts.json 四节点全部同步为 presets 文风提取整套（消除混搭）；修复②文风 node_a 补【产出严禁】条款（与剧情 node_a 的【严禁】对齐）；确认基于旧版增量未推翻——剧情 node_a 四段式章数配比/单章容量/长线≥5章/过渡快进/第n-m章跨度量化细节全在，文风 node_a 旧版八维度+情绪浓度适配在，node_b/c/d 自由发挥配套未动，污染词 15 词零命中；最终核对 final_confirm_v152b.py **ALL_OK 32 项全过**；
  - 本轮为 **PC 预设数据文件优化（data/style_extract 随 PC zip）**，安卓引擎无改动，**仅版本号同步重建 APK**（versionCode 126，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.25 条目；gitlink → 内层（见 PC 提交）。
- **v1.24 版本同步（与桌面 v1.52 对齐；versionCode 125）**：
  - PC **提取预设·基于旧版增量重写**（用户：剧情节奏方面还是有问题——AI 不是不知道安排什么东西，是不知道安排"用多少章编排开篇、发展、高潮、结尾"，之前的提示词就很好但现在提取出的提示词完全没有这方面的细节、太含糊；之前的预设 txt 放工作文件夹了（文风校对预设-剧情设计提取.json/文风提取.json），在原本的提示词基础上改，不要每次大改推翻）：以用户放回的旧版导出 json 为基底增量重写 node_a——**剧情设计提取恢复四段式章数配比（开篇/发展/高潮/结尾各占约 10~15%/50~60%/20~30%/5~10%）+ 单章容量控制（一章1个核心场景/1个具体冲突）+ 长线事件跨度（至少5章逐章推进、防无聊靠因果不靠巧合）+ 过渡事件快进（修炼/赶路压缩至单章开头1-2句话）+ 中事件第n-m章跨度排布 + 任务树状拆解 + 信息差转折 + 套娃钩子 + 冲突层级递进 + 情绪曲线**，同时保留 v1.51 防污染源头抽象（产出【严禁】具体人名/事件/物品/场景/题材标签、例子零信息泛称）；**文风提取**恢复旧版八维度（语言质感/叙事视角/修辞意象/环境氛围/行文节奏呼吸感/结构技巧/人物塑造/整体基调+范例+方向限定）+ 补 v1.51 情绪浓度适配；node_b/c/d 保持 v1.51 自由发挥配套不动；
  - 验证：本地 gemma-4-12b 实测——剧情提取 1720 字含四段式章数配比/单章容量/长线事件/过渡快进/中事件跨度量化细节，文风提取 1276 字八维度+情绪浓度适配在场，污染词（原书人名+假钞/验钞机/押手机/宗门/入赘/酒楼赴约等 11 词）零命中；结构断言 REBASE_OK（11 项全过）；
  - 本轮为 **PC 预设数据文件优化（data/style_extract 随 PC zip）**，安卓引擎无改动，**仅版本号同步重建 APK**（versionCode 125，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.24 条目；gitlink → 内层（见 PC 提交）。
- **v1.23 版本同步（与桌面 v1.51 对齐；versionCode 124）**：
  - PC **文风/剧情设计提取预设·源头抽象 + 交叉验证优化 + B/C/D 自由发挥配套**（用户：确认预设有没有遗漏、搜一下网上 AI 剧情/文风把控经验、没问题就打包——B 提示词要尽量自由发挥才能验证真的学到了技巧而不是表象，C 检验的配套标准也要同步调整）：**node_a 只产出跨题材抽象技法**（剧情六维度含节奏/情感节拍/冲突层级递进/setup-payoff 强制回收，文风六维度含情绪浓度适配——文风是语言质感、情绪张力随章节剧情起伏，禁止把高张力写成固定基调），产出【严禁】具体人名/事件/物品/场景/题材标签；**node_b 改尽量自由发挥**（剧情设计自主构思新故事+前6章细纲、文风自由创作正文——自由发挥才能验证提取技法真被学到而非靠预置题材表象）；**node_c 配套标准**（评分须确认生成内容"不依赖任何预设情节/结构模板、仅凭技法规则独立成立"才算高分）；**node_d 配套**（优化目标=自由发挥下稳定驱动、不越改越具体贴原文）；交叉验证吸收 Outliner 五级冲突递进/Save the Cat 节拍表/SillyTavern 正向指令/spec-kit setup-payoff；
  - 本轮为 **PC 预设数据文件优化（data/style_extract 随 PC zip）**，安卓引擎无改动，**仅版本号同步重建 APK**（versionCode 124，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.23 条目；gitlink → 内层（见 PC 提交）。
- **v1.22 版本同步 + 引擎同步（与桌面 v1.50 对齐；versionCode 123）**：
  - PC **拆书 L3 汇总防压缩**（用户：拆书文档从约 5w 缩到 1.5w 字——v1.43 加的「六、代表性章节细纲与逐章提示词」要求挑约 20 章逐章写详细章节提示词，单次 L3 汇总里第六节抢走模型输出预算、压缩了第一~五节（尤其第三节卷内细纲主体）；高级模式 l3_batch=5 分批汇总时 final 合并拿到的已是"摘要的摘要"会二次压缩）：**修复=第六节限幅（附录级辅助参考，整节约 1500~3000 字、每章提示词 80~150 字，严禁挤占一~五节）+ final 合并且输入 partials 时明确「合并≠删减、内容量不得低于各分卷之和」**；
  - 本轮 **book_break.py 整文件同源同步**；PC 代码级验证（verify_v150.py V150_SPECIAL_OK + py_compile COMPILE_OK，按用户要求不跑全量实例）+ _smoke 新增 [9u10] 防回归段；构建正式签名 APK（versionCode 123，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.22 条目；gitlink → 内层（见 PC 提交）。
- **v1.21 版本同步 + 引擎同步（与桌面 v1.49 对齐；versionCode 122）**：
  - PC **拆书章节识别通用兜底**（用户：《都市猎人（心动可乐）.txt》还是只识别出一章——万一作者乱取章节名或直接换行不取章节名，不能每次来找）：**book_break.py 三层通用方案**——①行首装饰符号通用化（`☆、第一章`/`※第1章` 等网站导出格式，实测《都市猎人》813 章全识别）②乱取名短标题兜底（装饰符短行标题扫描重切分）③完全不取章节名兜底（固定行数自动分块 FALLBACK_BLOCK_LINES=800）；
  - 本轮 **book_break.py 整文件同源同步**；PC smoke 全量 ALL_OK（[9u9] 段）+ 安卓 `_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 122，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.21 条目；gitlink → 内层（见 PC 提交）。
- **v1.20 版本同步 + 引擎同步（与桌面 v1.48 对齐；versionCode 121）**：
  - PC **拆书章节解析多格式放宽 + 文风校对 D 节点参考 Top3 开关**（用户：正常拆书丢一整本书进去只识别出一章、几十万字其他章节全被吞；文风校对加是否允许 D 看到排名前三提示词与分数并在最高分基础上改，可选开启）：本轮 **book_break.py（章节识别支持【第X章】/（第X章）/第X话/数字标题/裸第一章等常见导出格式，修复整本吞成一章）+ style_extract.py（D 节点可选注入 Top3 提示词与分数、要求在最高分基础上改进）整文件同源同步**；PC smoke 全量 ALL_OK（[9u8] 段）+ 安卓 `_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 121，CN=XinghuoPen 同签名可覆盖安装）+ zip 归档 77 文件（APK 单独成对）；README 加 v1.20 条目；gitlink → 内层（见 PC 提交）。
- **v1.19 版本号同步（与桌面 v1.47 对齐；versionCode 120）**：
  - PC **思考内容持久化**（用户：思考泡泡怎么显示一下，然后完成思考后就消失了）：v1.46 修好气泡显示后，思考内容仍只存在临时气泡里、`_render_all()` 重绘就没了——本轮聊天与 Agent 消息落库 think 字段、重绘渲染折叠思考气泡（完成后/重启软件仍可展开回顾）；
  - 本轮为 **PC GUI + 桌面 chat_lib 数据层功能**，安卓 WebView 前端无对应思考气泡组件且消息存储独立，**仅版本号同步重建 APK**（versionCode 120，CN=XinghuoPen 同签名可覆盖安装），zip/APK 成对归档历史版本-安卓端（77 文件）。
- **v1.18 版本号同步（与桌面 v1.46 对齐；versionCode 119）**：
  - PC **思考气泡显示修复**（用户：ai 对话那里还是没显示模型的思考——显卡占用证明思考强度生效但内容没显示）：v1.43 思考气泡交付时 `gui_chat.py`/`gui_agent.py` import 漏 `ThinkingBubble` → 思考分片一到 `_on_think` 就 NameError、气泡从不创建；本轮修复 import + smoke 新增真实执行链路断言（[9u6]）；
  - 本轮为 **PC GUI 功能**（PySide6 消息气泡组件），安卓 WebView 前端无对应组件，**仅版本号同步重建 APK**（versionCode 119，CN=XinghuoPen 同签名可覆盖安装），zip/APK 成对归档历史版本-安卓端（77 文件）。
- **v1.17 版本号同步（与桌面 v1.45 对齐；versionCode 118）**：
  - PC **文风校对页预设导入导出**（用户：加一个拆书工坊的预设导入导出——实际是文风校对页那套「提示词预设」）：`StyleExtractPage` 新增「导出预设（json）/导入预设（json）」——把选中的四节点提示词预设（如「文风提取」「剧情设计提取」）导出 json 备份/迁移/分享，或从 json 导入入库；
  - 本轮为 **PC GUI 功能**（QFileDialog 文件对话框），安卓文风校对预设另有应用/保存/删除控件但无文件对话框入口，**仅版本号同步重建 APK**（versionCode 118，CN=XinghuoPen 同签名可覆盖安装），zip/APK 成对归档历史版本-安卓端（77 文件）。
- **v1.16 版本号同步（与桌面 v1.44 对齐；versionCode 117）**：
  - PC **拆书工坊参数预设导入导出**（用户：加一个拆书工坊的预设导入导出）：`BreakSettingsBox` 新增「导出预设（json）/导入预设（json）」——整套拆书参数（三档模式/档位/模型上下文/token/重叠/并行/L3/总体提示词）导出 json 文件备份/迁移/分享，或从 json 导入并立即生效；
  - 本轮为 **PC GUI 功能**（BreakSettingsBox 是 PySide6 组件），安卓拆书参数设置样式一致但无 QFileDialog 入口，**仅版本号同步重建 APK**（versionCode 117，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.15 版本同步 + 引擎同步（与桌面 v1.43 对齐；versionCode 116）**：
  - PC **思考气泡 + 文风/剧情设计提取预设微调 + 拆书代表性章节细纲 + 打包保留用户数据**（详见 PC README v1.43 条目）：本轮引擎改动为 `llm.py`（`chat` 新增 `on_think` 回调——SSE `delta.reasoning_content` 与非 SSE `message.reasoning_content` 均触发，安卓底层同步具备、后续前端可接）+ `book_break.py`（拆书文档新增「六、代表性章节细纲与逐章提示词」——约 20 章代表性故事段逐章章节提示词，供学习参考）；
  - **实测**：PC smoke 全量 ALL_OK（新增 [9u3] 段）；本轮 **book_break.py + llm.py 整文件同源同步**（sync_check 16 个共享模块全 SAME）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 116，CN=XinghuoPen 同签名可覆盖安装）；zip 归档 77 文件（APK 单独成对）。
- **v1.14 prompts 同步补齐（用户追问完整审查结论后补跑引擎同源校验发现；versionCode 115）**：
  - **发现**：此前全面审查（拉取模型等 7 处修复）后补跑 PC↔安卓引擎同源校验（规范化行尾 md5 比 16 个共享模块），15 个全 SAME，唯独 **prompts.py DIFF**——v1.42 的 consolidate 注入段「自制新卡同样必须契合该基础文风」一句安卓同步落后一步（当时先同步安卓、后补 PC 措辞并重跑 smoke，漏了再同步）；功能主体（基础文风注入）在，缺的是这句自制卡硬约束；
  - **修复**：PC prompts.py 整文件重新同步到安卓 → sync_check 16 模块全部 SAME；重建 APK（versionCode 115）、验签 CN=XinghuoPen、zip 归档；
  - **教训（记录）**：引擎改动交付前先跑 sync_check 而不是信"手动 copy 过"；逐文件 md5 校验（规范化行尾）是唯一可靠判定。
- **v1.13 安卓专属 bug 修复（用户：安卓的 api 拉取模型点了根本没用，完整检查一下安卓版的 bug；versionCode 114）**：
  - **①WebView 补 WebChromeClient（MainActivity.java）——"点了没反应"的直接元凶**：此前 `setWebViewClient` 但**没设 `setWebChromeClient`**，WebView 里 JS 的 `alert()/confirm()` 默认被静默吞掉——拉取模型失败提示、删除确认等全部"点按钮无任何反馈"；本轮补 `onJsAlert/onJsConfirm` 用系统 AlertDialog 显示（确定/取消回传 JsResult），所有前端提示恢复可见；
  - **②拉取模型链路三处**：前端 `fetchModels()` 此前传空对象 `{}`（后端拿不到输入框的 base_url/api_key，未保存过配置时必报"未填写 API 地址"且 alert 被吞）→ 改为传当前输入框值；后端 `_do_fetch_models` 去掉 20s 硬编码超时（跟随设置页 request_timeout，与 PC 一致）；`_dispatch` 对 fetch_models **网络请求不持全局锁**（此前拉取几十秒会堵死 task_status 等全部 API 轮询）；
  - **③写作技巧库死链清理**：后端 v0.83 已删 `tech_extract` 路由，但安卓前端残留卡片/按钮/函数/字段（点了 404）→ 删除 "AI 拆解写作技巧" 卡片、`extractTech` 函数与挂载、load/save/newProject 的 p-tech-source/p-techniques 引用；
  - **④补挂漏挂的 window 函数**：`bookContinue`（一键成书"继续写"）、`breakImportDoc`（导入拆书文档）在 index.html onclick 引用了但没挂到 window（IIFE 闭包内函数不挂全局 → ReferenceError → 点了没反应）→ 补挂；
  - **⑤清理 plan_list 死调用**（后端无此路由，每次 loadPlans 都白发 404）；
  - **实测**：`_android_check` **235 项 ALL_OK**（改动只触前端/Java/服务层，引擎同源文件未动）；node --check app.js + ast.parse android_server.py 语法通过；构建正式签名 APK（versionCode 114，CN=XinghuoPen 同签名可覆盖安装）；PC 端 v1.42 不受影响（android_server/app.js 为安卓独有，PC 无此文件/此 bug）。
- **v1.12 版本同步 + 引擎同步（与桌面 v1.42 对齐；versionCode 113）**：
  - PC **全局文风与情景卡边界（用户：有些模型本身写作能力一般，想通过全局提示词/正文AI角色提示词控写作效果——这种全程生效的全局提示词会不会跟情景卡冲突？分不同情景卡也检查；可能没法测试，API 都在用，直接验证即可）**：**确认**主AI全局提示词只进主AI环节、与正文文风无关（无需改码）；**正文优先级显式裁定（prompts.write_chapter + consolidate）**——正文AI角色提示词**第一优先**、情景卡在其框架内对对应片段精修、冲突时以全局风格为基准（旧代码两处都标"必须遵守"但无裁定，模型天然偏 system 会把卡压掉）；**consolidate 注入【正文AI基础文风】**（`story_writer_prompt` + 风格要点）——主AI选卡/自制新卡前先确认正文文风、**自制卡必须契合**；**新功能：主AI按项目文风适配项目库情景卡**（`prompts.adapt_project_scene_card_ai` + `main_ai.adapt_project_scene_cards` + `engine.adapt_project_scene_cards`；gui_project「主AI按本文风适配本项目卡」按钮）——一次把项目库卡全部交给主AI逐张改写（**保持卡名/分类/情景内核不变、只调写法契合项目文风**），写回 `project.scene_cards`，**只改项目库、不动总库**；**修复：拆书库文档可再导出**（gui_break 风格库「导出选中风格（txt）」按钮）；
  - **实测**：PC smoke 全量 ALL_OK（新增 [9u2] 段：consolidate 注入基础文风+自制卡契合 + write_chapter 角色提示词第一优先/不得凌驾 + adapt 卡保持内核 + engine 只改项目库 + gui 按钮/导出源码断言）；本轮 **prompts.py + engine.py + main_ai.py 整文件同源同步**（文风优先级裁定 + 适配项目库卡引擎能力安卓随之具备）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 113，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.11 版本同步 + 引擎同步（与桌面 v1.41 对齐；versionCode 112；回退 v1.38 + 只加多情景卡）**：
  - PC **回退到 v1.38（7e5e8cb）基线 + 只加多情景卡功能**（用户强烈不满 bug 恢复：连角色卡生成重复、必要角色生成错误或直接不生成这种远古 bug 都复活了，要求回退到全面清查 bug 前的版本，把多情景卡功能加进去）；`git checkout 7e5e8cb` 回退 src/README/_smoke/scripts，丢弃 v1.39 的「落库前非法字节清洗 + StopRequested 扫描清理」（storage.py 回到无清洗原样，角色卡生成/落库路径与 v1.38 完全一致）与 v1.40 除多情景卡外的改动；重落多情景卡四处：①consolidate 选卡原则「一章同时出现几个特殊情景就选几张、**全选不漏**，分工组合而非单选」+ JSON schema scene_cards 说明同步；②engine `_collect_scene_cards` 注入卡带 category（`_c2nc`：category 字段直取或 content 首行【分类】回退提取；自做新卡带分类）；③write_chapter **多卡分工注入**——每卡带〔分类〕标注 + 多卡组合规则（每段只受所属片段对应卡约束、不得把多张卡的规则叠加在同一段）；④_smoke [9u] 断言段；
  - **实测**：PC smoke 全量 ALL_OK（105 行，含新 [9u]）；本轮 **prompts.py + engine.py + storage.py 整文件同源同步**（回退基线与多情景卡引擎能力安卓随之具备）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 112，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.10 版本同步 + 引擎同步（与桌面 v1.40 对齐；versionCode 111）**：
  - PC **一章多情景多卡组合（用户：工作文件夹放了新的拆书情景卡成果 txt——对话攻防/氛围酝酿/氛围反衬卡明显是一章内同时要用到的，主AI一次只能整一张给正文AI，写出来会割裂、描写混乱；情景卡得能自由组合、一次给好几张组合使用，正文AI能明白什么时候用什么卡、相互之间不能冲突）**：**根因**——consolidate 的 `scene_cards` 虽是数组但选卡原则②是单数语气「选用它」、各卡未带分类标注——主AI倾向一章只选一张；write_chapter 注入没有按片段类型告诉正文AI每张卡管哪段，多张卡塞一起正文AI不知何时用哪张 → 割裂；**修复（prompts.consolidate + engine + prompts.write_chapter）**：①consolidate 选卡原则明确「一章同时出现几个特殊情景就选几张、**全选不漏**，是分工组合而非单选」（如既有对话攻防又有氛围酝酿又有氛围反衬，三张全选）+ JSON schema scene_cards 说明同步「可多选——本章几个特殊情景选几张、全选不漏，各卡对应不同情景片段、分工组合互不冲突」；②engine `_collect_scene_cards` 传每张卡 category（`_c2nc`：category 字段直取 或 content 首行【分类】回退提取），自做新卡同样带分类；③write_chapter **多卡分工注入**——每张卡带〔分类〕标注（〔对话攻防〕〔氛围酝酿〕〔氛围反衬〕...），正文AI按片段对号入座（写对话交锋用〔对话攻防〕卡、写氛围酝酿/对视冲击用〔氛围酝酿〕卡、写景致反衬用〔氛围反衬〕卡）+ 新增**多卡组合规则**——每段文字只受『它所属片段类型』对应的那张卡约束、**不得把多张卡的规则叠加在同一段**（对话段别用氛围卡句式、氛围段别用对话卡节奏），各卡管各段、互不冲突；
  - **实测**：PC smoke 全量 ALL_OK（新增 [9s] 段：consolidate「全选不漏/分工组合/同时出现多个特殊情景/必须把每个情景各自匹配的卡全部选上」+ engine 多卡注入带分类（【分类】首行回退 + category 字段直取）+ write_chapter 含〔分类〕标注与「每段文字只受/不得把多张卡的规则叠加在同一段」）；本轮 **prompts.py + engine.py 整文件同源同步**（多卡组合引擎能力安卓随之具备）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 111，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.09 版本同步 + 引擎同步（与桌面 v1.39 对齐；versionCode 110）**：
  - PC **bug 清查（用户：做一下bug清查，把不规范的代码都调整一下吧，希望后续版本不会出现这个版本之前的问题）**：①**落库前非法字节清洗（storage.py）**——真实模型输出**偶发携带非法字节**（`\ufffd` 替换符/不可打印控制字符），原样写盘后按系统默认编码（GBK/cp936）读取会直接崩溃或出乱码块（v1.32 实测抓到、之前待确认未落地）；本次在 `_write_json` **统一递归清洗所有字符串字段**（删除 `\ufffd` 与 `\x00-\x08\x0b\x0c\x0e-\x1f\x7f`，**保留 `\n\t\r`**；dict/list 递归，非字符串原样保留），项目/章节/角色/伏笔/日志所有 JSON 落库路径全覆盖；②**StopRequested 传播清查**——AST 扫描 src 全部 try（内含 LLM 调用但 except 无 `StopRequested` 前置的兜底点）**0 处遗漏**，抽查 main_ai.py 各 LLM 环节确认均有 `except llm.StopRequested: raise` 前置（v0.87 修复无回退）；
  - **实测**：PC smoke 全量 ALL_OK（新增 [2f] 段：`_clean_value` 递归清洗 \ufffd/控制字符/保留换行制表回车/非字符串原样 + `_write_json` 落库后无非法字节）；本轮 **storage.py 整文件同源同步**（落库清洗引擎能力安卓随之具备）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 110，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.08 版本同步 + 引擎同步（与桌面 v1.38 对齐；versionCode 109）**：
  - PC **本地网关不认 reasoning_effort 参数修复**（用户：本地 api 在 API 设置页全局思考强度设置那里，一设置就直接 api 报错）：**根因**——用户在设置页设了「推理思考强度」（全局 `reasoning_effort`）后，llm 请求 payload 带 `reasoning_effort` 参数；**本地网关（LM Studio/llama.cpp）大多不认 OpenAI 的这个参数 → 返回 400 → 直接报错**（之前默认不传该参数所以没事，一设置就炸）；**修复（llm.py）**——400 且 payload 带 `reasoning_effort` 时**自动去掉该参数重试一次**（与 400 max_tokens 超上限自动降档同款逻辑，`_effort_dropped` 防死循环）：本地/第三方网关自动兼容，**商汤等支持该参数的网关不受影响**（它们不会 400），用户设的思考强度在支持它的网关仍生效；
  - **实测**：PC smoke 全量 ALL_OK（新增 [2c2] 段：mock 网关第一次 400「unknown parameter: reasoning_effort」→ 自动去掉重试成功 + 断言重试 payload 不再带该参数）；本轮 **llm.py 整文件同源同步**（400 自动去掉 reasoning_effort 兼容安卓随之具备）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 109，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.07 版本同步 + 引擎同步（与桌面 v1.37 对齐；versionCode 108）**：
  - PC **事件跨章节奏与前后衔接**（用户：怎么感觉前后章节衔接有出问题了，每章有每章的想法，都想着自己搞高潮桥段，恨不得一章一个事件，完全没做铺垫衔接——一个事件从酝酿发展到高潮结尾基本上得用几章甚至十几章几十章讲述，主AI特别毛躁；短篇可能一章一事件但那是几万字写一个事件的，且写完也有前后衔接；让主AI自己做好判断）：**根因**——consolidate 任务6 要求「2-3 个本章**必须完成**的具体剧情点」（暗示一章装一个完整事件）+ write_chapter 情绪节奏「全章**至少一个情绪支点** + 结尾留**强烈钩子**」（诱使每章都要高潮收尾），铺垫/过渡被压缩、章与章之间像独立短篇；**修复（prompts.consolidate + prompts.write_chapter）**：①consolidate **事件节奏规则（v1.37）**——一个完整事件（酝酿→发展→高潮→收尾）通常**跨多章推进**（几章到十几章几十章），本章 beats 只是**事件链上的一步**（推进一个环节/一个阶段）、**绝不在单章内把一个事件从头到尾讲完**；按【故事整体进度】目标章数定节奏（目标多=长篇放慢铺陈、高潮前置多章酝酿；目标少=短篇紧凑但保留铺垫-发展-高潮-收尾层次且写完仍与前后衔接）；**前后衔接**——beats 承接【最近章节概要】上一章结尾的状态/悬念/现场继续推进，本章结尾为下一章留衔接（未解决事件/新悬念/情绪余波），**平淡铺垫章完全可以没有高潮**（作用就是酝酿），除非本章恰好在事件收尾位置否则不把「完成整个事件」写成 beat；②write_chapter **情绪支点不强制每章都有**（铺垫/发展/过渡章以自然推进与氛围为主、不硬造高潮，只有事件链高潮位置才集中写高潮名场面）+ **结尾按事件进度收束**（事件未完则留衔接钩子，不强行在章内收束大事件）；③JSON schema `chapter_beats` 字段说明同步为「当前事件链上的一步，非完整事件」；
  - **实测**：PC smoke 全量 ALL_OK（新增 [9r] 段：consolidate 事件节奏/跨多章推进/承接上章结尾/为下章留衔接/铺垫章可无高潮/不把完整事件写成 beat + write_chapter 不强制每章情绪支点/结尾按事件进度收束断言）；本轮 **prompts.py 整文件同源同步**（事件节奏引擎能力安卓随之具备；GUI 展示为 PC 专属）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 108，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.06 版本同步 + 引擎同步（与桌面 v1.36 对齐；versionCode 107）**：
  - PC **情景卡拆书边拆边显示**（用户：剧情拆书遇到长小说得一部分一部分拆，但得拆完才显示，能不能直接把已经拆完的直接都列出来，这样小说太长了我受不了的话也能停止，把已经拆出来的情景卡保存先用着）：引擎 `extract_scene_cards_from_novel` 新增 `on_card` 回调参数——阶段3每生成一张卡草稿就立即回调 `on_card(card)`（不等到全部拆完），停止/失败后已回调的卡不丢；GUI `SceneCardExtractWorker` 新增 `card_ready` 信号（`run` 把引擎 `on_card` 接到信号），拆书页新增 `_sc_add_card_item`（完成/实时共用入列）+ `_sc_on_card`（逐张实时入列，拆出一张显示一张、保存按钮随勾选数实时刷新），`_sc_on_done` 重构复用同一段入列逻辑；**停止文案改「已拆出的卡保留在结果列表，可直接保存」**——长小说拆到一半点停止，已拆出的卡留在列表里照常勾选存进总库；
  - **实测**：PC smoke 全量 ALL_OK（新增 [9q] 段：引擎 `on_card` 逐张回调数量与返回一致 + 停止时已回调的卡保留（StopRequested 不吞）+ worker 有 `card_ready` 信号 + 页面有 `_sc_on_card`/`_sc_add_card_item` + 停止文案断言）；本轮 **scene_card_extract.py 整文件同源同步**（on_card 逐张回调引擎能力安卓随之具备；GUI 实时入列展示为 PC 专属）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 107，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.05 版本同步 + 引擎同步（与桌面 v1.35 对齐；versionCode 106）**：
  - PC **主AI自制卡参考已有卡，不凭空创造**（用户：主ai自制卡的时候，有现成的卡，让主ai参考着写，别凭空造）：consolidate 之前只把**卡名清单**注入给主AI，主AI选卡时**看不到任何已有卡的实际内容**——选卡原则说「参考已有卡风格/结构」其实没有参照物，自做新卡只能凭空造，风格/结构/详略容易脱离库卡；修复：①卡清单**前 10 张卡附写法摘录**（content 前 150 字），主AI自做新卡时有真实写法参照；②自制卡原则措辞收紧——**「必须参考下方清单里已有卡的实际写法样例来写新卡——模仿其核心定位、分节结构、详略与表述风格，绝不凭空创造」**；③JSON schema `new_scene_cards` 字段说明同步加「自制前必须参考上方清单中已有卡的写法摘录，不凭空创造」；v1.30「不注入卡内容全文」边界保留（只注入前 150 字摘录，剧情判断仍以章节内容为准）；
  - **实测**：PC smoke 全量 ALL_OK（[9d] 断言更新：自制卡措辞含「不凭空创造」「写法摘录」+ 摘录内容实际注入断言；[9k][9l][9m] v1.30 旧断言升级——短卡全文即摘录应注入、长卡只注入前 150 字、全文不注入）；本轮 **prompts.py 整文件同源同步**（自制卡参考摘录引擎能力安卓随之具备）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 106，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.04 版本同步 + 引擎同步（与桌面 v1.34 对齐；versionCode 105）**：
  - PC **选卡名带「〔分类〕」前缀兼容修复**（用户要求上网取章拆书写章实测——全链路实测抓出真 bug）：consolidate 把清单里的**显示格式整串**填进 `scene_cards`（如「〔氛围酝酿〕环境奇观渲染描写」而非纯卡名「环境奇观渲染描写」）→ engine `_collect_scene_cards` 按**纯卡名**在项目库/总库精确匹配 → **匹配失败** → 明明主AI选中 2 张卡（reasoning 可见）却落「本章未选用情景卡」日志、卡**实际没注入正文AI**；修复双管齐下：①`_collect_scene_cards` 匹配时先**剥离「〔…〕」前缀**再查项目库/总库兜底（纯卡名匹配回归不受影响）②consolidate 提示词明确 **scene_cards 只填卡名本身、不要带【分类】前缀和来源标注**；
  - **全链路实测（anysearch 上网取章）**：《西游记》第一回 7260 字 → 情景卡拆书 **6 张卡全是写法类型**（宏大时空维度叙事/环境奇观渲染/并列式细节堆砌/生存危机目标设定/拟态行为/身份重塑仪式——泛化 + 「怎么写/怎么做」边界生效）→ 临时项目写一章《云深处的试炼》3681 字：主AI裁定走向、角色推理、审查**通过**，评分**沉浸9/节奏8/爽点7/人设9/自然8**，铺垫正常无直接进事件，选卡理由可见；
  - **实测**：PC smoke 全量 ALL_OK（新增 [9p] 断言段：consolidate 只填纯卡名措辞 + engine 剥离前缀匹配注入 + 纯卡名回归）；本轮 **prompts.py + engine.py 整文件同源同步**（选卡前缀兼容引擎能力安卓随之具备；GUI 日志展示为 PC 专属）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 105，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.03 版本同步 + 引擎同步（与桌面 v1.33 对齐；versionCode 104）**：
  - PC **情景卡「怎么写/怎么做」边界 + 选卡匹配即选不保守**（用户追问：平淡情景酝酿气氛时主AI会不会漏用匹配卡？卡学了「怎么做」会跟主AI指令冲突/抄袭/应用面窄）：①**选卡措辞收紧（prompts.consolidate）**——去掉「常规叙事章节一律不选卡」改「常规叙事章节不选卡」+ 新增正向硬要求「只要本章确实出现某类特殊情景（含氛围酝酿/冲突前奏/雨夜压抑等）且库卡匹配度足够高，就应该选用——绝不因怕选错而漏用；漏用匹配卡=失职」；新增 **`scene_cards_reason` 选卡理由字段（必填一句话）**——engine 日志与运行记录如实展示，主AI「怕犯错不敢选」直接暴露在理由栏；②**write_chapter 卡注入新增「卡的边界」**（prompts）——卡只讲这类情景「怎么写」（节奏铺陈/感官细节密度/氛围用词/对白留白比例/段落长短变化/情绪渐变语言手法），卡里任何具体行为/事件/情节字样只是写法示例、绝不照着做，人物做什么/事件怎么发展以【本章剧情】与【各角色行为指导】为准；③**拆书三阶段提示词写明「怎么写/怎么做边界」（scene_card_extract）**——候选类型从「情景类型」改「写法类型」（按节奏/感官/氛围/情绪渐变分类，不按情节/行为/事件分）、合并只看写法特征、生成卡**严禁写「怎么做」**（禁止任何行为/事件/情节指令，示例片段行为只许提炼写法不可照抄）——卡不与主AI指令冲突、不抄书、可适用于所有同类写法需求；④顺带修 scene_card_extract 残留旧 _SYS_MERGE/_SYS_CARD 重复定义；
  - **实测**：PC smoke 全量 ALL_OK（[9d]/[9o] 断言更新：匹配即选不保守+选卡理由必填+拆书写法边界）；本轮 **prompts.py + engine.py + scene_card_extract.py 整文件同源同步**（选卡理由/怎么写边界引擎能力安卓随之具备；GUI 日志展示为 PC 专属）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 104，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.02 版本同步 + 引擎同步（与桌面 v1.32 对齐；versionCode 103）**：
  - PC **情景卡机制修正八点**（用户：①主AI不主动——给一堆不相干卡也硬选不做合适卡 ②运行记录看不到选卡 ③新功能运行时空闲 ④拆书结果太具体没泛化 ⑤还有提示词冲突 ⑥情景卡后正文AI不会铺垫、直接发生事件 ⑦一章可能多情景/一情景只占小部分 ⑧剧情不参考角色推理+角色卡太精简）：**选卡与注入机制重构（prompts/engine）**——consolidate 选卡改「按需精确匹配」：平淡铺垫/日常/过渡/开篇引入等常规叙事章节一律不选卡（scene_cards 留空），正文AI按正常叙事把铺垫写足；仅当本章确实出现某类特殊情景且库里内容真正匹配才选卡（绝不硬套不匹配卡）；确实需要但无匹配才按需自做一张（new_scene_cards 参考已有卡风格、只进项目库标『AI 制作』）；write_chapter 卡注入从「整章必须逐条遵守」改「片段级写法参考」——卡只约束对应情景片段，铺垫/日常完全按正常节奏写足、不许为套卡压缩铺垫或改剧情；**选卡可见性**：engine 日志选中/未选都打印 + 运行记录展示「本章情景卡：xxx / 未选用」；**新功能运行状态**：情景卡 AI 生成/文本提取/拆书 worker 全程 set_running（不再一直空闲）；**拆书泛化**：候选/合并/生成卡三阶段强制「泛化要求」——卡名与规则抽象为可迁移通用写法、禁止绑定具体人物/关系/场景细节；**角色卡丰富化 + 推理落地**：generate_character_ai/generate_batch_roles/consolidate new_character 建档提示全面放开（personality 100-200 字/personality…、appearance 80-150 字、description 250-450 字），write_chapter 新增【遵循要求】段——正文必须落实各角色 RP 推理成果（意图/行动倾向/言语倾向），卡/写法参考不得凌驾其上；
  - **实测**：PC smoke 全量 ALL_OK（新增 [9o] 段：平淡章不选卡/绝不硬套 + write_chapter 片段级参考 + 拆书泛化提示词 + 角色卡丰富化 + set_running 源码断言）；真实模型 5 章短篇实测（gemma-4-12b，本地 12B 每章 12-18 分钟，用户叫停未跑完第 5 章）——第 1 章平淡开篇「未选卡 + 有铺垫」、第 2 章探索遗迹「主AI主动自做〔遗迹〕废墟勘测并选中注入」、第 3 章多情景「赶路+密室探秘+废墟勘测三卡并存」、第 4 章探秘选卡，**4 章正文全部主AI审查通过**（无直接进事件、铺垫正常、人物有辨识度），选卡日志完整可见；
  - 本轮 **prompts.py + engine.py + scene_card_extract.py 整文件同源同步**（选卡按需精确/片段级注入/拆书泛化引擎能力安卓随之具备；GUI/日志展示为 PC 专属）；验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 103，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.01 版本同步（与桌面 v1.31 对齐；versionCode 102）**：
  - PC 端**批量导入分类保留修复 + 本地 API 真机实测**（用户：再做一下全量测试吧，本地api，gemma-4-12b-qat-heretic-styletune我已经加载好了，你做一下实测，还有就是确定一下现在的按键没问题了吧。还有就是现在导入情景卡会丢失分类，我导出导入还得重新分类，修复一下）：①**批量导入丢分类根因**=v1.30 批量导出的「_细分」文件夹每卡一个文件内容只写正文（分类只在文件名 `[武打]夜战夺镖.txt`）→ 导入 `_parse_import` 只认内容首行【分类】行 → 分类全丢、卡名带 `[武打]` 前缀 → 修复双管齐下：**导出侧**细分文件内容首行写【分类】（与汇总一致）+ **导入侧** `_parse_import` 兼容旧版文件名 `[分类]卡名` 前缀拆分（内容含【分类】行时以内容为准）；新旧导出文件导入分类均保留；②**按键确认**：拆书「开始情景卡拆书」按钮真实点击链路（mock worker 秒完成：初始化→注入→done 复位按钮/结果列表/存进总库启用）+「＋加入」点行即勾选，smoke 全量 ALL_OK；③**本地 API 真机实测**（用户已加载 gemma-4-12b）：pick_profile 命中「本地api」、chat_json 3.7s 连通、generate_scene_card 真实生成 1265 字、extract_scene_cards_from_novel 全链路真实产出 3 张卡——全部 ALL_OK；
  - 本轮**纯 PC GUI 修复无引擎变更**（gui_scene_cards.py 批量导入导出分类为 PC 页面专属），安卓仅版本号同步；验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 102，CN=XinghuoPen 同签名可覆盖安装）。
- **v1.00 版本同步 + 引擎同步（与桌面 v1.30 对齐；十进制递增 0.99→1.00，versionCode 101）**：
  - PC 端**情景卡拆书按钮修复 + 批量导出细分/批量导入 + 主AI写乱情节修复**（用户：情景拆书我点了没反应，你咋又犯低级错误了，修复一下。另外就是情景卡批量导出的功能为什么是导出一个txt文件？除了一个txt文件外，还得有一个文件夹把细分的罗列在里面吧，不然我下次只想导入其中一个，多麻烦啊，另外加一个批量导入情景卡。再有就是这次ai写得确实情景会好很多，但是主ai对于情节有时候会写乱不知道为什么，是不是什么地方提示词冲突了，你检查一下）：①**情景卡拆书"点了没反应"根因**=v1.26 加情景卡拆书区块时忘了在 `BreakPage.__init__` 初始化 `self._sc_worker = None`（首次点按钮 AttributeError 无反馈）→ `__init__` 补初始化；②**批量导出改「txt + 细分文件夹」**（选文件夹生成汇总 txt 可整批再导入 + 「_细分」子文件夹每张卡一个文件、文件名带分类前缀如 `[武打]夜战夺镖.txt`、非法字符自动替换，想只导入一张直接选那个文件）+ **新增「📂 批量导入 txt」**（多选文件：汇总多卡/单卡按文件名，同名自动跳过不覆盖）；③**主AI写乱情节=consolidate 提示词冲突**——consolidate 曾把每张卡 300 字全文（最多 30 张≈9000 字）与剧情校验任务混在一个 user，主AI注意力被卡内容示范带偏、把卡当剧情指令 → 修复为 **consolidate 只注入卡名清单**（卡名+分类+来源标注），并明确「卡只是正文写法建议，**绝不影响你的剧情判断**（人物状态/伏笔/剧情走向/chapter_beats）」；本轮 **prompts.py 整文件同源同步**（consolidate 瘦身随之具备；①②为 PC GUI 专属）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 101，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.99 版本同步 + 引擎同步（与桌面 v1.29 对齐）**：
  - PC 端**审查补漏（用户：审查一下最近加的功能是否还有这类没注意到的小bug，不要用实际内容测试）**：静态审查 v1.17~v1.28 新功能 + 结构级断言，补 3 个同类小 bug：①一键成书「run 立项」与「应用以上设置」两处从总库复制卡进项目库**丢了 category**（v1.24 分类功能不一致，带入项目全变未分类）→ 改为全卡映射并补 `"category"` 字段；②情景卡拆书 `SceneCardExtractWorker.run` 只捕获 StopRequested，LLM 失败等异常杀死线程 → 拆书按钮永久卡死「正在运行」→ 补 `except Exception` 兜底（**严格放在 except llm.StopRequested 之后**，StopRequested 是 LLMError 子类防吞停止）复位按钮；③`scene_card_extract` 候选>60 分批二次合并时输入结构已是 `{type,examples[]}`、取示例逻辑只看 example/brief → 示例全丢 → `examples` 兜底取代表片段；本轮 **scene_card_extract.py 整文件同源同步**（补漏③引擎能力随之具备；①②为 PC GUI 修复）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 100，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.98 版本同步（与桌面 v1.28 对齐）**：
  - PC 端**一键成书「＋ 加入」点行即勾选修复 + 空勾选明确提示**（用户：怎么ai一键成书那里加入根本没用啊，我选中了情景卡，点了确定根本没添加上啊）：离屏全链路复现实证 `_card_pick` 本身正常——**根因=交互缺陷**：分组选卡弹窗里「点中卡行」只是选中高亮、不切换勾选框（复选框在行左侧需精确点击），用户以为点行=勾选，实际未勾 → 点确定自然没添加；修复：选卡弹窗列表改用 **`_CheckListWidget`（QListWidget 子类）**——**点行文本即切换该行勾选**（再点取消；x>28px 避开复选框区，点左侧复选框照旧；分类标题行点行即整类全选/全不选），一键成书「＋ 加入」与项目页「从总库加入」共用弹窗同时生效；`_card_pick` 空勾选点确定 → 明确提示「未勾选任何情景卡」+ 成功写入日志；
  - 本轮为 **纯 PC GUI 修复（无引擎文件变更），安卓仅版本号同步**（versionCode 99）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（CN=XinghuoPen 同签名可覆盖安装）。

- **v0.97 版本同步 + 引擎同步（与桌面 v1.27 对齐）**：
  - PC 端**情景卡拆书控制性提示词 + 主AI空库自动做卡确认**（用户：情景卡拆书怎么没有输入控制性提示词的地方？还有就是比如ai一键成书，或者正常项目，我完全不选情景卡的情况下，主ai应该会自己制作情景卡吧？）：①**情景卡拆书控制性提示词**——拆书页情景卡拆书区块新增「控制性提示词（可选）」输入框（sc_prompt_edit，如重点拆装逼打脸/战斗按流派细分/日常温馨；跳过感情戏）→ worker.run(text, prompt) → 引擎 `extract_scene_cards_from_novel(text, prompt=None)` 注入每片候选抽取【用户指定关注方向（必须遵守）】段，留空按通用全拆；②**主AI空库自动做卡确认已实现**（v1.22 链路）：一键成书不选卡/项目不启用情景卡 → 项目库空 → 每章 consolidate 鼓励主AI自做一张（new_scene_cards）→ engine._collect_scene_cards 自动存入项目库（source=ai 同名跳过）并注入本章正文，后续章节可沿用；本轮 **scene_card_extract.py 整文件同源同步**（prompt 参数引擎能力随之具备；控制性提示词输入框为 PC GUI 专属）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 98，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.96 版本同步 + 引擎同步（与桌面 v1.26 对齐）**：
  - PC 端**情景卡拆书：从导入小说自动拆出全部情景卡（同类/相似度高自动合并，可存进总库）**（用户：现在不是有个拆书的功能页吗，帮我做一个自动我导入的小说拆出所有情景卡的功能（情景卡拆书），不同的打斗、小说开篇、不同的矛盾引爆、男女朋友分手、绝境描写等诸多情景都得拆分……在完成情景卡拆书后，把相似度很高的情景卡合并一下……情景卡尽可能拆得详细些）：**新引擎 `scene_card_extract.py`** 三阶段——①分片抽候选（每片约 12000 字含完整章节，逐片列候选 `{type,brief,example}`，要求拆得细、写法差异大的同类也拆开，每片最多 8 个）②相似度合并去重（语义相似高合并，写法差异大保持分开，每类归大类 category，候选过多按批合并再合）③逐类生成卡草稿（按范例结构：核心定位+分节+自检清单，参考本书示例片段提炼不照抄，→ `[{name,content,category}]`）；拆书页新增「📇 情景卡拆书」区块（PC GUI：后台线程+立即停止+进度日志+结果勾选列表+「存进总库」（同名跳过，分类保留））；LLM 走用途分工·情景提示词制作（role="scene_card"）；本轮 **scene_card_extract.py 整文件同源同步**（引擎能力安卓随之具备；拆书页区块为 PC GUI 专属，安卓暂无对应 UI）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 97，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.95 版本同步（与桌面 v1.25 对齐）**：
  - PC 端**情景卡分类改下拉选择 + 选卡对话框按分类分组整类全选**（用户：分类能不能做成下拉列表，你现在这个是纯自己输入，我万一忘了就完蛋了。选择方面能不能直接选择整个分类（也要能选择分类里的子项））：①**编辑区「分类」改下拉列表**（QComboBox editable：列出所有已有分类 + 「未分类」，选中即填不怕忘，仍可输新分类；`_refresh_categories` 同步刷新、`_on_row`/`_card_new`/`_card_save` 适配取值）；②**选卡对话框按分类分组**（`_PickCardsDialog`：每组首行加粗分类标题带复选框——**勾选=整类全选、取消=整类全不选**，组内卡仍可**单独勾选**；卡名存 `data(UserRole)` 防标题/前缀干扰取值）；一键成书「＋ 加入」与项目页「从总库加入」共用弹窗同时生效；
  - 本轮为 **PC GUI 改动（无引擎文件变更），安卓仅版本号同步**（versionCode 96）；`_android_check` **235 项 ALL_OK**；构建正式签名 APK（CN=XinghuoPen 同签名可覆盖安装）。

- **v0.94 版本同步 + 引擎同步（与桌面 v1.24 对齐）**：
  - PC 端**一键成书改「加入」式选情景卡 + 情景卡分类管理**（用户：ai一键成书那里做成"加入"式，而不是现在的选择式，不然太多了很麻烦，点加入，然后从总库选择哪些加入到这里就行了。还有就是情景卡的页面得有能分类的功能，不然太多了的话，我也很难管理）：①**一键成书「加入」式（gui_book）**——去掉全部总库卡并列勾选，面板只显示已加入的卡：点「＋ 加入」弹总库选择对话框（勾选=要带，取消勾选=不带，已加入默认勾选，全量替换；对话框卡名带分类前缀）；未加入占位「未加入任何情景卡」，总库为空占位+「去情景提示词页建卡」按钮保留；scene_cards 取值=已加入列表 `_added_scene_cards`，立项/应用设置链路不变；②**情景卡分类（gui_scene_cards）**——卡结构新增 `category` 字段（空=未分类）：编辑区分类输入框 + 卡库列表顶部「分类筛选」下拉（全部/未分类/各分类，可输新分类名连续建卡）+ 列表项「[分类] 名称」前缀 + 从总库加入/放入总库/项目库显示带分类 + 导出带 `【分类】` 行/导入解析（无分类向后兼容）；③**models.py 项目库卡（scene_cards）category 随 to_dict/from_dict 往返**；本轮 **models.py 整文件同源同步**（分类字段引擎能力随之具备；一键成书加入/分类管理为 PC GUI 专属，安卓暂无对应 UI）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 95，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.93 版本同步 + 引擎同步（与桌面 v1.23 对齐）**：
  - PC 端**一键成书可选情景卡（可实际勾选）+ AI 生成卡支持细节方向**（用户：ai一键成书好像还是没法选择情景提示词卡啊，你弄了个框我看到了，但是没法选择啊。还有就是情景提示词卡的ai生成功能，怎么只能输入名称，然后剩下的就由ai写了，我连细节方向把控都做不到，不同的打斗有很大区别的啊）：①**一键成书"没法选择"根因**=勾选列表从总库（config.writer_scene_cards）渲染，之前总库为空→列表空→没法勾选——修复：总库为空时显示**引导占位**（不可勾选）+ 面板新增**「去情景提示词页建卡」按钮**（`_goto_scene_cards` 跳转 index 11，建卡保存后回来即可勾选）；总库有卡后正常显示可勾选卡（勾选→立项复制进新项目 scene_cards，v1.21 语义不变）；②**AI 生成情景卡支持细节方向**——`prompts.generate_scene_card_ai(type_name, detail=None)` 有 detail 时注入【细节方向（用户指定，这张卡必须按此方向设计，不能写跑偏）】段，`main_ai.generate_scene_card(type_name, detail=None)` 转发；UI 由只输名称改两步输入（类型名+细节方向可选多行），留空与原行为一致；本轮 **prompts.py + main_ai.py 整文件同源同步**（detail 参数引擎能力随之具备；一键成书勾选/生成细节输入为 PC GUI 专属，安卓暂无对应 UI）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 94，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.92 版本同步 + 引擎同步（与桌面 v1.22 对齐）**：
  - PC 端**「设为当前」API 老 bug 修复 + 主AI选卡策略强化**（用户：确定主ai会优先用已有的情景提示词卡，不会动不动就创新卡吧？创新卡是会参考已有卡，实在没有参考再按照你的提示词制作的逻辑吧？另外就是api设置的把api设置为当前怎么没用啊，我把本地api设置为当前，下面的选择也都是默认用当前，但是根本没调用本地api（感觉是老bug了，只是一直没发现））：①**config.pick_profile 分支 2 修复**——通用配置（role=all）设为当前后应匹配**任意用途**（旧实现漏了该分支，带用途的调用落到 api_profiles 列表第一个 role=all 配置，用户实测 current="本地api" 但全部调用走"商汤flash-lite模型"）；用途分工显式指定仍优先、专用当前配置只匹配自己用途（不变）；②**prompts.consolidate 选卡策略强化**——优先用已有卡（尤其用户提供的）；相近/可套用也选最接近的已有卡、不要动不动自做；仅当与**所有**已有卡都明显无关时才自做，且**自做卡必须参考已有卡的风格/结构**（核心定位+分节+自检清单格式统一）；项目库为空时注明「没有已有卡可参考」按通用范例做；本轮 **config.py + prompts.py 整文件同源同步**（pick_profile 修复 + 选卡策略强化随之具备；选卡/情景卡管理为 PC GUI 专属，安卓暂无对应 UI，未配置卡时不注入）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 93，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.91 版本同步 + 引擎同步（与桌面 v1.21 对齐）**：
  - PC 端**总库/项目库分离：主AI按需自做情景卡（只进项目库）+ 放入总库 + 一键成书/项目页入口同步**（用户：ai一键成书等同样需要配置情景提示词卡的功能你还没更新呢。允许主ai按照规则设计情景提示词卡，优先用我提供的已有的，但为防特殊情况我可能没空提供，让主ai自己按需制作，但主ai制作的只能放在"当前主ai可选情景提示词卡"里，也得有一个从"当前主ai可选情景提示词卡"里放进总库的功能，毕竟有时候主ai做的可能好用就留下来了呢。所以从这个版本开始把主库和主ai可用的库独立开来）：**主库（全局总库 config.writer_scene_cards）与「当前项目主AI可用库」（新字段 project.scene_cards，[{name,content,source}]，source=user|ai）彻底独立**——主AI每章只从项目库按正文类型选卡（优先用户提供的卡），没匹配卡时按规则**自做一张**（JSON 新增 `new_scene_cards`，只存本项目库标记「AI 制作」，同名跳过），用户可点「📥 放入总库」把好卡留进全局库（情景提示词页项目库管理区：从总库加入/移出/放入总库）；一键成书从总库勾选带入新项目、项目页⑤只读显示+跳转管理；旧项目 scene_cards_active 自动迁移；本轮 **models.py + prompts.py + engine.py + main_ai.py + config.py 整文件同源同步**（v1.17~v1.21 引擎补全同步：情景卡/字数循环/上下限/提取提示词；情景卡管理为 PC GUI 专属，安卓暂无对应 UI，未配置卡时不注入）；`_android_check` fake_write mock 签名适配（scene_cards/min_chars/max_chars 参数）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 92，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.90 版本同步 + 引擎同步（与桌面 v1.20 对齐）**：
  - PC 端**提取提示词可编辑（保存/恢复初始）+ 当前项目主AI可选情景卡显示框**（用户：从文本中提取这个功能的提取提示词你确定有效吗，应对不同情景都有用吗？做成带恢复初始、保存的功能，初始提示词用"初始提取.txt"中的稍微改改细节再用；加一个显示框显示当前项目主ai可选的情景提示词卡）：情景提示词页新增「从文本提取·提取提示词」编辑区（保存写入 config `extract_scene_card_prompt` / 恢复初始回内置）；内置初始提取提示词 `prompts._DEFAULT_EXTRACT_SYS` 微调自「初始提取.txt」（角色定位+七维度+只提风格忽略情节+规则卡结构）；`extract_scene_card_ai` 新增 prompt 参数（None 用内置）；情景提示词页新增当前项目可选情景卡显示框（`project_cards_view`，列 scene_cards_active 命中的卡）；本轮 **prompts.py + main_ai.py + config.py 整文件同源同步**（extract_scene_card_prompt 键 + prompt 参数；提取提示词编辑/显示框为 PC GUI 专属）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 91，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.89 版本同步 + 引擎同步（与桌面 v1.19 对齐）**：
  - PC 端**情景提示词制作：用途分工独立 API 行 + 从文本提取情景规则卡**（用户：api设置页怎么没有设置情景提示词制作的ai用哪个api的设置？另外就是在情景提示词那里加一个根据我提供的文本提取情景规则卡的功能（保留纯ai生成，但得增加一个根据我提供的生成的））：设置页用途分工 13 行 → 14 行（新增「情景提示词制作」scene_card 行，未指定时跟随通用，指定后情景卡生成/提取走该 API）；情景提示词页新增「📄 从文本提取」按钮（`prompts.extract_scene_card_ai` + `main_ai.extract_scene_card`，从参考文本提炼规则、禁止照抄原文，保留纯 AI 生成）；本轮 **prompts.py + main_ai.py 整文件同源同步**（extract_scene_card 引擎能力随之具备；用途分工行为 PC GUI 专属，安卓暂无对应 UI，未指定 scene_card 时跟随通用配置不受影响）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 90，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.88 版本同步 + 引擎同步（与桌面 v1.18 对齐）**：
  - PC 端**情景写作提示词独立功能页**（用户：没看到有能设置正文ai情景提示词的地方啊，ai一键成书也没看到可以选的地方啊。做一个专门储存这个情景写作提示词的功能页，其他地方选哪些是本项目要用的就行了；通用情景写作提示词.txt 是范例，ai 生成符合这个格式，字数不做要求；要求能导入导出、要能批量导出）：v1.17 卡库管理藏在设置页没被找到——本轮移出设置页做成专门功能页（gui_scene_cards.py：卡库 CRUD + AI 一键生成 + 导入/批量导出，批量导出每卡以【卡名】分隔可再导入）；AI 生成按范例格式（核心定位+分节细则+写作执行自检清单，字数不限）；**项目级启用 project.scene_cards_active**（项目页文风参考⑤ + 一键成书面板各勾选本项目用哪些卡，主AI每章只从启用卡里按正文类型选卡注入正文AI——consolidate 只注入启用卡，不再注入全局全部卡）；本轮 **prompts.py + models.py 整文件同源同步**（consolidate 启用卡注入逻辑 + scene_cards_active 字段），安卓引擎随之具备（情景卡管理/项目勾选为 PC GUI 专属，安卓暂无对应 UI；项目未启用卡时不注入）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 89，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.87 版本同步 + 引擎同步（与桌面 v1.17 对齐）**：
  - PC 端**正文AI情景规则卡（可选插入项）+ 字数不达标循环重写直到达标 + 正文长度上下限开放**（用户：正文AI角色提示词做成可选插入项，标注类型后主AI按本章正文类型选用，任意个数、文风统一一个、AI 一键写作某类型提示词；字数不达标打回重写一次后不能由主AI接手，要接着重写直到达标；设置界面开放正文长度上下限自设）：设置页新增「正文AI情景规则卡」管理区（新增/编辑/删除/AI 一键生成），`prompts.consolidate` 注入卡清单+JSON `scene_cards` 字段（主AI按正文类型选卡），engine 解析后注入 `write_chapter`【本章情景规则卡】段；`_ensure_chapter_length` 由"重写一版就交差"改为循环重写直到落在上下限内（`LENGTH_RETRY_MAX=6` 防死循环，每轮带字数警示 feedback）；config 新增 `chapter_min_chars`/`chapter_max_chars`（0=自动 target×0.8/×1.15）供用户自设上下限；本轮 **prompts.py + engine.py + main_ai.py + config.py 整文件同源同步**，安卓引擎随之具备选卡注入与循环重写能力（情景卡管理区为 PC 设置页专属，安卓暂无对应 UI；未配置卡时不注入）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 88，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.86 版本同步（与桌面 v1.16 对齐）**：
  - PC 端**一键去AI味停止立即生效**（用户：去ai味的一键去AI味没法用停止直接停下，必须等完成后才会停下，跟我要求的停止逻辑不一致；另外确认是不是加了默认违禁词，为啥让 AI 写偏暴力的内容都写得很含糊）：`_AutoDeaiWorker.run` 补绑 `llm.set_abort(stop_event)`（此前只做轮间 stop_check，当前 LLM 调用不被中断，必须等完成才停）——点停止立即中断当前改写/验收；违禁词排查：星火笔代码**无默认内容审查违禁词**（tone_highlighter 套话检测只作用编辑器高亮、不进提示词；写作提示词「日常场景用语克制」只约束文风不限制战斗/激烈场景），暴力含糊大概率是模型侧安全对齐（未破限模型自己软化）；本轮为 PC GUI 改动，安卓无对应入口，**仅版本号同步**（versionCode 87）。

- **v0.85 版本同步（与桌面 v1.15 对齐）**：
  - PC 端**一键成书立项即刷新**（用户：一键成书显示能不能更及时一点？项目立好了但看不到项目，看不到 AI 设计的剧情/世界观等内容，必须等第一章完成才能看到）：`_BookWorker` 新增 `project_ready` 信号，立项完成（项目已建+三栏已写入）立即刷新项目页（书架+故事设定三栏立刻可见，不等第一章）；本轮为 PC GUI 改动，安卓无对应入口，**仅版本号同步**（versionCode 86）。

- **v0.84 版本同步 + 引擎同步（与桌面 v1.14 对齐）**：
  - PC 端**卷划分放开**（用户：你别固定卷划分啊，万一写 30 章的短篇小说呢？？让 AI 自己判断，给个参考标准就行了；同类问题也解决一下）：`prompts.plan_story_ai` 把 v1.13 写死的「卷划分 3~6 卷」「每卷 3~8 个事件」「world/rules 分栏条目数」全部放开——卷数由 AI 按全书规模自行判断（短篇可不分卷/1~2 卷，中长篇 3~5 卷，超长篇更多，只给参考标准不要生搬硬套），事件数随该卷剧情量自行把握，条目数按需给；安卓 **prompts.py 整文件同源同步**；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 85，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.83 版本同步 + 引擎同步（与桌面 v1.13 对齐）**：
  - PC 端**故事设定规范化**（用户：一键成书生成的故事设定完全不规范；剧情发展按 5.0.txt 剧情大纲来——卷和主要事件按规范并设定好章节；故事设定下 AI 生成/修缮同规范；一键成书没法设置项目名）：`prompts.plan_story_ai` 三栏规范化——story 按规范大纲（主线总判→卷划分（卷题/起止章号/剧情任务，覆盖全书总章数）→卷内主要事件（事件名+章数范围+一句话）→结尾方向；world/rules 按分栏条目）；一键成书 BookPanel 新增书名/项目名输入框（用户填了优先，留空 AI 起名）；安卓 **prompts.py 整文件同源同步**；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 84，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.82 版本同步 + 引擎同步（与桌面 v1.12 对齐）**：
  - PC 端**主AI拆书参考五维度强化**（用户：每个事件的长度、事件的影响等内容也蛮重要的，尤其是事件剧情的长度和影响层级，AI 总是弄不明白；修改主AI得到拆书文档的提示词，一键成书支持用拆书文档把控主AI设置剧情也别忘了）：`prompts.main_system()` 拆书参考段重写为五维度主动运用要求（①**事件长度与节奏**：起因/经过/高潮/结尾各占多少章、长短事件交替②**事件影响层级**：单章小事件/跨章中事件/卷级大事件、影响哪些人物关系、连锁后果③**冲突与误导**④**伏笔与回收**⑤**钩子与情绪节拍**），保留"只学技法不抄情节"；`book_break.merge_doc` L3 learning 生成提示词同步要求覆盖五维度；一键成书与正常写作共用 main_system 入口自动生效；安卓 **prompts.py + book_break.py 整文件同源同步**，主AI拆书学习能力随之具备；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 83，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.81 版本同步 + 引擎同步（与桌面 v1.11 对齐）**：
  - PC 端**拆书四段式改造**（用户：细纲事件段缺少起因/经过/高潮/结尾的描述，且拆书成果字数太少——2k 多章的书才 1w7 字，离 8w 上限早得很）：L2 事件按 **起因→经过→高潮→结尾** 四段拆解（每段标注占用章数范围，起因写因何引起、经过写受哪些因素误导、高潮写冲突怎么产生、结尾写以什么方式收场）；L3 卷内细纲事件段四段式展开 + **篇幅放开**（超长篇上千章写到 5~8 万字接近上限，严禁压缩成只剩标题的提纲）；安卓 **book_break.py 整文件同源同步**，拆书引擎能力随之具备；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 82，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.80 版本同步 + 引擎同步（与桌面 v1.10 对齐）**：
  - PC 端**拆书穿插改造**（用户：拆书重点放在人物和事件上，要保证拆书后得到的小说细纲能还原出原小说；人物和事件穿插着来，分开很多信息得重复，按故事卷区分；没有明确卷概念时要求AI自己判断故事分卷；尽可能把锚点伏笔等剧情细节都整合进去）：L3 final 主体改为**卷内细纲**（人物与事件穿插，禁止人物表+事件表分离写法——每个事件段内直接写卷入人物的抉择/反应/关系推进 + 本卷锚点与伏笔 + 卷末人物状态）；L1-b arcs 支持无明确卷概念时按剧情阶段自行判卷（basis 判卷依据）；L3 partial 分部同步穿插；安卓 **book_break.py 整文件同源同步**，拆书引擎能力随之具备；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 81，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.79 版本同步 + 引擎同步（与桌面 v1.09 对齐）**：
  - PC 端**拆书工坊细化**（用户：拆书内容还是不够详细，完善提示词，现在拆书结果用来指导 AI 还是太潦草了）：L2 事件加 **逐章节拍 beats**（每个事件按覆盖的每一章给「第X章：推进了什么、章末落什么钩子」，主AI续写知道下一章往哪儿推）+ 人物加 **当前状态 state**（续写直接接）+ 伏笔加 **埋设载体 carrier / 回收方式 by**；L3 汇总带逐章节拍/当前状态/载体回收；安卓 **book_break.py 整文件同源同步**，拆书引擎能力随之具备；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 80，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.78 版本同步（与桌面 v1.08 对齐）**：
  - PC 端**AI 对话/Agent 会话可自定义命名**（用户：ai对话的每个话题都没法命名，只能是新对话1/2/3什么的，没法区分）：数据层 rename_topic/rename_agent_session 早存在但 UI 只留隐蔽的右键入口=等于没法命名——本轮补三个显眼入口：新建话题/会话**先弹命名框**（默认名可改，自动兜底创建不打扰）+ 标题栏**「✏️ 重命名」按钮** + 树内**双击改名**；对话/Agent 页均为 PC GUI，安卓无对应页面，本轮仅版本号同步；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 79，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.77 版本同步（与桌面 v1.07 对齐）**：
  - PC 端**参考文风样本放开 + 前后章节参考**（用户：去AI味的参考文风为什么只能放几百字？打斗/文斗/日常/情景酝酿等不同情节笔调根本不一样；还有为什么不能设置AI在校对的时候看前后章节，防剧情偏移）：①参考样本三类限制全放开（UI 编辑框 90→260px、文案"几百字即可"改多情景笔调引导、verify/校对注入截断 800/600→6000 字——多段不同情景笔调样本可完整参考）；②新配置 `deai_nearby_chapters`（默认前后各 2 章，0=只看本章）：main_ai 组装前后章标题+梗概+正文节选注入**去AI味审查/改写/验收三环节**与**写后校对**，AI 对照前后文核对人物状态/地点/时间线/事件连续性，防剧情偏移，验收另加"与前后文衔接一致，冲突判 false"；安卓 core（config/prompts/main_ai 整文件）同源同步，引擎能力随之具备，安卓界面无对应入口；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 78，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.76 版本同步（与桌面 v1.06 对齐）**：
  - PC 端**联网搜索多源修复**（用户：主AI联网搜索和AI对话的联网搜索根本不能用；真网络实测根因=Bing 中国对长中文查询降级分词成单字，查「黑神话悟空 剧情设计」返回「黑字词条」——主源改**搜狗**（国内直连+中文相关度好），回退链 搜狗→Bing→360→DuckDuckGo，搜索超时封顶 20s；web_search.py 双端同源同步，安卓搜索能力随之修复）+ **去AI味验收上限放开**（轮次 1-999、字数容差至 99999，用户自己决断不再限死）；安卓界面无自动去AI味入口（PC 功能），联网搜索路由 `search` 同步受益；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 77，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.75 版本同步（与桌面 v1.05 对齐）**：
  - PC 端**一键自动去AI味修订**（用户三连：轮次结束应取评分最高的一篇而非最后一轮 / 字数容差直接用正文写作的 ±500 字标准 / 验收 AI 判严点；并审查有无 bug）：每章从已跑轮次中选**评分最高**的轮次作为成果——达标则用该轮自动合并，不达标报告"最高 X 分（第 N 轮）"保留原文；字数容差从 ±% 改为 **±N 字（默认 500，与正文写作一致）**、旧百分比配置自动迁移；`deai_verify` 验收从严（宁严勿松 + 扣分锚点 + plot_same 逐项清单）；**安卓本轮 core 引擎继续与 PC 同源同步**（config/prompts/main_ai 整文件），安卓界面无自动去AI味入口（PC 功能），手动去AI味不受影响；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 76，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.74 版本同步 + 引擎补同步（与桌面 v1.04 对齐）**：
  - PC 端**一键自动去AI味**（用户：结合文风校对功能做自动去AI味工作流——批量选中章节一键跑，自动比对规则/参考文本，达到设置的相似度阈值自动通过，直到完成整个批次；去AI味后字数和剧情必须基本维持原样）：去AI味页新增验收区块——每章 整体审查→按规则+参考样本改写→自动验收（文风契合度 [有样本=0.4×TFIDF+0.6×LLM评分，无样本=去AI味完成度] + 剧情一致性 + 字数浮动±容差）→达标自动合并回原文（旧稿备份草稿箱），未达标自动带验收反馈重写直到达标或达最大轮次，不达标保留原文；**安卓本轮：core 引擎顺带补同步 v1.01~v1.04**（config/prompts/main_ai 整文件与 PC 对齐——含章节标题按类型取题、去AI味参考文风样本、自动去AI味工作流引擎能力，安卓界面无对应入口，仅引擎具备）；去AI味 App 已有手动功能不受影响；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 75，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.73 版本同步（与桌面 v1.03 对齐）**：
  - PC 端**修复章节标题重设计完成弹框卡死**（用户：完成后弹完成提示框显示不完整就整个 UI 卡死——根因是后台线程直接调 QMessageBox，改为信号回主线程弹框 + 全项目 AST 排查确认仅此一处）；**安卓端无重设计标题功能，本轮仅版本号同步**；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 74，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.72 版本同步（与桌面 v1.02 对齐）**：
  - PC 端**去AI味加「参考文风样本」**（用户：除了规则类控制，加一个参考文本，单纯靠规则不够）：去AI味页新增参考文本编辑框（全局配置 `deai_style_ref`），AI 去AI味时把原文往这种语感上改（模仿句式/节奏/描写手法，不抄内容），章节级三种模式 + 段落工具 deai 模式均注入；**安卓端去AI味无参考文本入口（本轮仅版本号同步）**；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 73，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.71 版本同步（与桌面 v1.01 对齐）**：
  - PC 端**章节标题按类型取题 + 批量重设计**（用户：《飞升是我编的》章节名全是「xx与xx」，要根据小说类型/书名风格取题；正文生成页加重新设计第 x~y 章章节名功能）：写章提示词内置标题风格引导（贴合书名气质、严禁「xx与xx」模板连用）；生成页新增「章节标题重设计」区间控件 + `main_ai.retitle_chapters`（AI 按类型/书名取题、逐章贴合梗概，只改标题不碰正文）；**安卓端暂未加此功能（PC 功能，本轮仅版本号同步）**；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 72，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.70 版本同步（与桌面 v1.00 对齐）**：
  - PC 端**一键成书面板「AI 设置」区完整覆盖全部项目级 AI 设置**（用户纠正版本命名 v1.00；一键成书要支持文风/拆书风格/主AI提示词等全部 AI 设置）：文风要点 + 参考文风样本 + 主AI全局提示词 + 正文AI角色提示词 + 拆书设计风格，新建一键成书自动写入新项目；已生成几章可改面板 →「✓ 应用以上设置到当前项目」→ 从下一章生效、不删已生成章节；「你是一个……」规则类文风要求原样注入正文AI提示词直接生效；**安卓端一键成书卡片暂未加设置区（本轮仅版本号同步，如需可在后续给 book-start 卡片加）**；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 71，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.69 版本同步（与桌面 v0.99 对齐）**：
  - PC 端**角色卡导出严格对齐酒馆 spec_v2**（用户要求按 spec_v2 格式导出中文 .json 到酒馆玩）：data 补全 creator/extensions/avatar 键、description 无内容时多字段回退拼装（老卡也能直接玩）、中文内容 + 中文文件名不转义；**安卓端暂无角色卡导出功能，本轮仅版本号同步**；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 70，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.68 引擎同源同步（与桌面 v0.98 对齐）**：
  - **安卓引擎 10 个核心模块整体回归同源**（engine/main_ai/prompts/models/config/llm/git_tool/book_break/novel_import/style_extract——此前自 v0.57 起未同步，llm 缺 think_role/on_chunk、config 缺 role_thinking 等）；PC 本轮改动一并同步：①**防重复建档**（save_generated_character 按名查重复用旧卡，杜绝同角色两张卡）②**主AI归档角色 + 角色卡库**（归档不删，可恢复）③**酒馆 spec_v2 角色卡**（tags/character_version/creator_notes/post_history_instructions 字段）④写后校对命名（正文审查环节日志由「文风校对」改「写后校对」）⑤git 存档无仓库自动 init（消除 not a git repository 警告）；
  - 验证：`_android_check` **235 项 ALL_OK**（v036/v037 文风工坊 mock 契约随 llm.chat_text 签名升级适配 **kw）；构建正式签名 APK（versionCode 69，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.67 版本同步（与桌面 v0.97 对齐）**：
  - PC 端**导入导出加固**（用户反馈：导出项目后导入章节/角色卡丢失只剩世界观——storage 层往返实测完好，加固防 zip 截断/损坏静默导入）：导出改临时文件+原子改名并写 `manifest.json`（章节/角色/快照计数）；导入校验 zip 内条目数与实际还原数，不一致返回警告；GUI 导入成功提示显示实际导入章节/角色/快照数量；**storage.py 双端同源同步**；
  - 验证：`_android_check` **235 项 ALL_OK**（新增 zip 含 manifest 检查）；构建正式签名 APK（versionCode 68，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.66 版本同步（与桌面 v0.96 对齐）**：
  - PC 端**对话页与 Agent 页消息改为气泡渲染**（新增头像框：用户=金色「我」右侧、AI=蓝色「AI」左侧；原 QTextBrowser HTML 气泡因 Qt 富文本不支持 inline-block 而不生效，两页一起修）；**API 配置与 Key 随 zip 打包**（`data/config.json` 不再剔除，解压新版免重新输入 Key）；安卓引擎同源未动（API 存 WebView localStorage，App 更新不丢）；
  - 验证：`_android_check` **234 项 ALL_OK**；构建正式签名 APK（versionCode 67，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.65 版本同步（与桌面 v0.95 对齐）**：
  - PC 端**功能级思考强度补「关闭思考（off）」档**（现 6 档：跟随全局/关闭/低/中/高/最大）；**对话页与 Agent 页布局防 200% 缩放挤压**（头部拆两行、状态独立一行）；安卓引擎同源未动；
  - 验证：`_android_check` **234 项 ALL_OK**；构建正式签名 APK（versionCode 66，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.64 版本同步（与桌面 v0.94 对齐）**：
  - PC 端**思考强度按功能**（设置页用途分工 13 行各配「思考」下拉：跟随全局/低/中/高）；**AI 对话与 Agent 的 API 设置并入设置页用途分工统一管理**（页面改为只读生效配置标签，Agent 可选 API 的修复）；安卓引擎同源未动；
  - 验证：`_android_check` **234 项 ALL_OK**；构建正式签名 APK（versionCode 65，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.63 版本同步（与桌面 v0.93 对齐）**：
  - PC 端对话页与 Agent 页新增**实时上下文用量显示**（估算 token / 窗口比例，窗口来自星火笔配置「拉取模型」记录）；**Agent 上下文占用 ≥60% 自动压缩**（防用户忘用 /compress，压缩后自动继续发送）；安卓引擎同源未动；
  - 验证：`_android_check` **234 项 ALL_OK**；构建正式签名 APK（versionCode 64，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.62 版本同步（与桌面 v0.92 对齐）**：
  - PC 端主目录清理（历史打包/检查脚本归档到 scripts\、删除测试输出 txt、data/ 整体 gitignore）；安卓引擎同源未动；
  - 验证：`_android_check` **234 项 ALL_OK**；构建正式签名 APK（versionCode 63，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.61 版本同步（与桌面 v0.91 对齐）**：
  - PC 端把 **AI 对话**与 **Agent（Qwen Code 智能体）**拆成两个独立功能页：对话页纯净化（LM Studio/Cherry Studio 式，新增话题搜索、联网搜索、文件/图片附件）；Agent 页独立（coding 项目文件夹下拉新建、星火笔项目设定复制进子文件夹、纯 coding 模式、指令 /compress /goal /model 等、去更新功能、可用星火笔 API 配置、沙盒硬约束禁止越界）；安卓引擎同源未动；
  - 验证：`_android_check` **234 项 ALL_OK**；构建正式签名 APK（versionCode 62，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.60 版本同步（与桌面 v0.90 对齐）**：
  - PC 端 AI 对话页再扩展：**消息编辑/重新生成/继续生成/删除**（LM Studio 式，作用于最后一条）、**agent 指令**（/compress 压缩上下文 /goal 目标任务 /help /clear /skills /mcp）、**Skill/MCP 安装多样化**（文件夹/zip/本机已有；MCP 支持 env、JSON 导入、同步 qwen 用户级 `qwen mcp add`）；安卓引擎同源未动；
  - 验证：`_android_check` **234 项 ALL_OK**；构建正式签名 APK（versionCode 61，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.59 版本同步（与桌面 v0.89 对齐）**：
  - PC 端 AI 对话页扩展 **Qwen 智能体**：Agent 权限模式三档（规划/自动/YOLO，映射 qwen `--approval-mode plan|auto|yolo`）、**导入 Skill**（复制到工作区 `.qwen/skills/`）、**MCP 配置**（写工作区 `.qwen/mcp.json`，CLI 带 `--mcp-config`）、工作区建 **coding/ 代码文件夹**；安卓引擎同源未动；
  - 验证：`_android_check` **234 项 ALL_OK**；构建正式签名 APK（versionCode 60，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.58 版本同步（与桌面 v0.88 对齐）**：
  - PC 端新增 **AI 对话页**（话题存储/文件夹/导出、API 测试、可选读项目不含正文、Qwen Code 隔离工作区模式）；`llm.py` 新增 `on_chunk` 流式回调；安卓引擎同源未动（对话页为 PC 专属 UI，后续可移植）；
  - 验证：`_android_check` **234 项 ALL_OK**；构建正式签名 APK（versionCode 59，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.57 停止传播修复（与桌面 v0.87 对齐）**：
  - `engine.py` `_proofread_once` 外层补 `except llm.StopRequested: raise`——写后校对环节用户点停止立即传播，不再被外层 `except Exception` 吞成「保留原文继续」（此前关闭自动审查时该环节停止无效、本章照常归档）；
  - `style_extract.py` `_wait_pause` 补停止判断——文风校对工坊暂停期间收到停止立即退出挂起（与拆书 `book_break._wait_pause` 语义对齐）；
  - 验证：`_android_check` **234 项 ALL_OK**（engine/style_extract 双端同源同步）；构建正式签名 APK（versionCode 58，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.53 引擎同步（与桌面 v0.83 对齐）**：
  - `style_extract.py` 新增 `pause_check`（文风校对工坊暂停语义，PC 端为「⏸ 暂停 / ▶ 继续」按钮）；`prompts.py`/`main_ai.py`/`novel_import.py`/`android_server.py` 移除「写作技巧库」相关（`tech_extract` 路由、提示词注入、拆书技法写入——主AI可直接联网搜索/锚点/提示词控制）；`_android_check` 检查项同步调整（235 → 234）；
  - 验证：`_android_check` **234 项 ALL_OK**；构建正式签名 APK（versionCode 54，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.52 引擎同步（与桌面 v0.82 对齐）**：
  - `engine.py`/`book_break.py` 双端同源同步：**文风校对**环节 LLM 失败自动重试 3 次/2s（仍失败保留原文继续不阻断）；**拆书 NovelBreaker** 新增 `pause_check`/`_wait_pause()`（安卓服务端拆书同样支持暂停语义，前端按钮在 PC 端）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 53，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.51 一键成书章数放开 + 撤销设置页自定义禁词栏（与桌面 v0.81 对齐）**：
  - 一键成书「本次一键生成到」上限 100 → **9999**（可填全书总章节数一次生成完，引擎连写无章数上限）；
  - 设置页「自定义禁词」栏撤销（`s-tone` 输入/回填/保存移除；`tone_words_custom` config 已有值保留）；
  - 安卓设置页「文风校对（写后自动）」开关与校对规则提示词保留原样（桌面端该设置移至项目页，安卓仍在设置页）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 52，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.50 停止响应修复·并行子线程绑定停止（与桌面 v0.80 对齐；用户：生成停止按钮停不下——深度审查抓出的真 bug）**：
  - **真 bug**：角色推理/拆书/导入的并行子线程（ThreadPoolExecutor）有自己的线程局部，主 worker `set_abort` 绑定的停止事件不会传给子线程——限流重试风暴里子线程不响应点停止、主 worker 干等；
  - **修复**：`llm.py` 新增 `current_abort()`（返回当前线程停止事件），`char_ai.py`/`book_break.py`/`novel_import.py` 并行子线程统一绑定/恢复停止事件（实测点停止 0.6s 内全部并行子线程中断）；
  - 验证：`_android_check` **235 项 ALL_OK**（llm/char_ai/book_break/novel_import 双端同源同步）；构建正式签名 APK（versionCode 51，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.49 版本同步（与桌面 v0.79 对齐；PC 端 UI 卡死根因修复——安卓为服务端线程模型不受影响）**：
  - PC 端确诊：`QThread+moveToThread` worker 长时间运行会冻结主线程 Qt 事件循环（点开始即卡死一晚上），v0.79 改纯 Python threading 启动并实测零冻结；安卓端文风校对本就是 Flask 服务端任务线程模型，无 Qt 事件循环问题，本轮仅同步版本号；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 50，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.48 文风校对轮次上限放开（与桌面 v0.78 对齐；用户：99 轮限制太小，本来要 200 轮慢慢打磨）**：
  - **最大校对轮次 20 → 999**：前端 `se-rounds` 上限与后端 `max_rounds` clamp 同步放开（用户可设 200 轮慢慢打磨，不再自缚手脚）；
  - 引擎未改动（`style_extract.py` 双端同源保持 v0.76 基线）；本轮是纯 UI/参数上限修复，不碰任何 API 设置；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 49，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.46 API 硬限制清账（与桌面 v0.76 对齐；用户：审查还有哪些 API 限制全列举，能不限制的都别限制）**：
  - `llm.py`/`main_ai.py`/`web_search.py` 双端同源：**拉取模型超时 15s → 跟随设置「请求超时」**（慢网关不再拉取失败）；**联网搜索超时 15s → 跟随「请求超时」**；**一键成书起书名 max_tokens=40 → 不限制**（推理模型思考吃预算不再回退「AI 新书」）；
  - 验证：`_android_check` **235 项 ALL_OK**（三引擎文件同步后全量回归）；构建正式签名 APK（versionCode 47，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.45 输出不限制（与桌面 v0.75 对齐；用户：max_tokens 才 12000？搞这么小图什么？改成不限制）**：
  - `llm.py` 双端同源：`chat_json` 未显式传 max_tokens 时 payload **不带该键**（网关/模型自己决定输出长度，不再用 8000/12000 卡推理模型思考）；显式传参环节语义不变、400 超限自动降档保留；
  - 验证：`_android_check` **235 项 ALL_OK**（llm.py 同步后全量回归）；构建正式签名 APK（versionCode 46，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.44 推理预算一次到位（与桌面 v0.74 对齐；用户批评：思考占满 max_tokens？max_tokens 不会搞大点？）**：
  - `llm.py` 双端同源：`chat_json` 默认 max_tokens 8000→**12000**（thinking 留足）；响应只取正文 `content`，思考只用于检测"空正文=思考吃光预算"、**从不展示/保存**；预算不足自动翻倍重试且**不消耗「重试次数」**（重试次数=1 也正常）；
  - 真实本地网关验证（127.0.0.1:1234 qwen3.8-9b-heretic）：**TEXT 3/3、JSON 5/5 全部一次成功**（20-80s/次）；调试教训：第一版"见到 thinking 即中断翻倍"被 llama.cpp 打脸（每次请求都从思考开始，中断即掐断完整生成）——正确做法等完整响应、预算不足才翻倍；
  - 验证：`_android_check` **235 项 ALL_OK**（llm.py 同步后全量回归）；构建正式签名 APK（versionCode 45，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.43 本地推理模型适配（与桌面 v0.73 对齐；用户：本地 llama.cpp 也报错，"本地不可能限速、qwen code 调用没问题"）**：
  - `llm.py` 双端同源同步：**推理模型支持**——SSE/非流式都检测 `reasoning_content`（thinking），正文为空且出现过 thinking → 自动翻倍 max_tokens 重试（思考消耗预算导致正文空）；仍空才显式报错，不静默返回空正文/空 JSON；
  - 真实网关验证（本地 1234 端口 qwen3.8-9b-heretic-uncensored）：修复前 TEXT 0/3、JSON 0/5 全失败 → **修复后 TEXT 3/3、JSON 5/5 成功**；
  - 验证：`_android_check` **235 项 ALL_OK**（llm.py 同步后全量回归）；构建正式签名 APK（versionCode 44，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.42 失败恢复按钮·继续写（与桌面 v0.72 对齐；用户：失败停住后「鬼知道怎么重试、怎么从头来」——必须直接给恢复入口）**：
  - `book_auto` 路由新增 **`continue` 参数**（v0.42 继续写）：在「当前项目」上从断点自动连写剩余章节（跳过立项/建项目/核心角色），失败/停止后可点「继续写」往前推进，不用从头；
  - 一键成书卡新增「**▶ 继续写**」按钮（confirm 后 continue 模式连写），运行中禁用、完成后/失败后可点；拆书/导入 tab 已有「重新开始」按钮 + 开始按钮自动续传（失败后"继续=再开始"语义保留）；
  - 验证：`_android_check` **235 项 ALL_OK**（book_auto continue 参数 + 前端按钮结构）；构建正式签名 APK（versionCode 43，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.41 坏JSON内容级自动重试（与桌面 v0.71 对齐；用户全面审查"还有没有这种逆天逻辑"）**：
  - `llm.py` 双端同源同步：`chat_json` 新增**内容级重试**——模型偶发返回坏 JSON（解析失败）自动重新请求（次数与设置页「重试次数」一致，默认 3 次尝试），不再一次坏 JSON 就停下等手动重试/跳过；网络类错误仍由 chat 内部按原样重试、快速报错；全部 JSON 环节（写作决断/推理/审查/战后/一键成书/批量角色/拆书/导入/角色卡）受益；
  - 验证：`_android_check` **235 项 ALL_OK**（llm.py 同步后全量回归）；构建正式签名 APK（versionCode 42，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.40 失败环节自动重试（与桌面 v0.70 对齐；用户：拆书某单元出错「model did not return valid JSON」停下等手动重试——「你 tm 出错的章节不会自己重新跑？缺了一部分怎么拆？」）**：
  - 引擎双端同源：`book_break.py`/`novel_import.py` 全部 LLM 环节新增 `_retry_llm` 自动重试——LLMError（JSON 解析失败/网关流式错误/模型未加载/429 等）**自动重跑最多 3 次、间隔 2s**（用户停止不重试），瞬时错误第 2 次即补跑成功，不再停下等手动重试；重试耗尽仍失败才记入「N 个环节未完成」（断点续传/重新开始语义不变）；
  - 环节**返回空结果/非预期类型**也按失败处理（自动重试，仍空才显式报「已自动重试 3 次仍失败」）——不再静默当完成缺内容；
  - 验证：`_android_check` **235 项 ALL_OK**（引擎同步后全量回归）；构建正式签名 APK（versionCode 41，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.39 失败不跳过·重新开始（与桌面 v0.69 对齐；用户四连报：模型名被改/本地 llama.cpp 无法调用/拆书出错跳过、重试与重选 txt 都续传）**：
  - 引擎双端同源：`llm.py`（流式 `{"error":...}` chunk 立即抛 LLMError，不再静默吞掉返回空——本地 llama.cpp 未加载模型时秒报 "Model is unloaded."）；`book_break.py`/`novel_import.py`（失败批/单元/块/角色卡不落盘不视为完成，结尾返回「N 个环节未完成」可重试补跑；骨架空中断）；
  - `break_start`/`import_start` 新增 `restart` 参数（清空进度全部重来、不做续传）；拆书 tab 与导入卡新增「重新开始」按钮（confirm 后 restart）；
  - 验证：`_android_check` **235 项 ALL_OK**（引擎同步 + restart 参数 + 前端按钮结构）；构建正式签名 APK（versionCode 40，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.38 拉取模型解析修复（与桌面 v0.67 对齐；用户：拉取模型只能出现一个 id、没法选择）**：
  - `llm.py` 双端同源同步：`_parse_model_list` 健壮化——兼容顶层列表 / data.models / 嵌套 dict（{"data": {"list": [...]}} 等）/ 单模型对象 / dict 键即 id，条目 id/model 键均可（此前嵌套结构只拉出 1 个假 id）；
  - 验证：`_android_check` **235 项 ALL_OK**；构建正式签名 APK（versionCode 39，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.37 文风校对四节点独立 API（与桌面 v0.66 对齐；四节点可各选不同 API）**：
  - 引擎同步（`style_extract.py`）：`style_settings` 读 `style_profiles` dict（每节点留空跟随全局；node_a 兼容旧单键 `style_profile`），`run_workflow_stream` 各节点按自己配置调 `llm.chat_text(profile=...)`；
  - settings_get/save 加 `style_profiles`（四节点 dict）；设置页「文风校对 API 配置」单下拉 → **四个下拉**（s-style-a/b/c/d：节点A提取/B生成/C评分/D优化），app.js 回填与保存；
  - 验证：`_android_check` **235 项 ALL_OK**（新增 v037-四节点各用各的API + style_profiles 往返）；构建正式签名 APK（versionCode 38，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.36 文风校对移植（与桌面 v0.64 对齐；独立功能页 + 四节点多轮迭代磨合文风）**：
  - 引擎同步（`style_extract.py`）：A(提取文风)→B(生成文章)→C(评分)→D(优化提示词) 多轮迭代，评分 = 0.4×轻量 TF-IDF（字符 bigram，无 sklearn/jieba 依赖）+ 0.6×LLM 分；Top3 提示词导出；预设库仅 default 空壳（用户自行保存）；
  - 新增 8 个 `stylecheck_*` 路由（提示词/预设 CRUD + 任务化运行/停止/导出），复用任务轮询机制；设置页新增「文风校对 API 配置」下拉（`style_profile`，留空跟随全局）；
  - 前端新增「文风校对」页签（原文/txt 导入 + 轮次/阈值 + 实时任务日志 + Top3 结果 + 导出 + 四节点提示词编辑 + 预设管理），版本标识同步 v0.36；
  - 验证：`_android_check` **234 项 ALL_OK**（新增 v036 段 16 项）；构建正式签名 APK（versionCode 37，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.35 智能档位调整（与桌面 v0.63 对齐；智能模式三档比例上调）**：
  - 智能拆书三档比例调整：**激进 40%→70%**、正常 25%→50%、保守 12%→30%（按模型上下文自动定每部分 token）——1M 上下文激进档 ≈ **73 万 token/部分**（输入×0.75 安全系数后仍留输出余量，2000 万字拆得更快）；262144 三档 ≈ **7.9 万 / 13.1 万 / 18.4 万**（稳/均衡/快速）；
  - 引擎同步（`book_break.py` `SMART_SUBS`）；前端保存提示文案同步（按上下文×30%/×50%/×70% 自动定档）；`_android_check` 换算断言同步；
  - 验证：`_android_check` **217 项 ALL_OK**；构建正式签名 APK（versionCode 36，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.34 拆书人物刻画升级（与桌面 v0.62 对齐；性格事件级证据 + 关系按事件推进 + 男女主/反派关系全覆盖）**：
  - 引擎同步（`book_break.py`）：L2 人物 `portrayal` 改为「发生了什么事件→怎么抉择/反应→体现什么性格」，禁止只列静态细节（外貌/小动作）；`relation` 改为「关系推进的事件概述」（相识/升温/裂痕/反目的转折点）；L1-b 骨架 `characters` 加全书级 `key_relations` 关系锚点（男女主/配角/反派都列）；L3「核心人物设计」重写为 定位/弧光 → 关系线（事件概述序列）→ 性格刻画（事件证据），明确男女主与反派的对抗关系（怎么建立/怎么升级/矛盾焦点）写完整，让主AI直接照关系线续写；
  - 真实 API 实测（8 章两卷）达标：性格"暗箭射向阿禾时转身挡箭→重情轻命"、关系"雨夜收信相识→砸酒坛解围→挡箭相护→破庙托付生死"、反派线"铜牌'沈'字直指沈家→因果关联未交锋"；
  - 验证：`_android_check` **217 项 ALL_OK**；构建正式签名 APK（versionCode 35，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.33 拆书实测修复（与桌面 v0.61 对齐；引擎同步 + 测试连带修复）**：
  - **L3 汇总兜底**：桌面真实 API 实测（8 章两卷）发现商汤类网关对超长生成（v0.58 的「尽量保留细节 ≤8 万字」提示词诱导）返回空 → `chat_json` 抛 LLMError → 整个拆书中断；本轮同步修复——L3 提示词改「篇幅适中、信息密度优先」（8 万字仅为截断上限非生成目标）+ `_try_merge` 兜底（调用失败自动退化为阶段过程文档，不中断拆书）；
  - **测试连带修复**：`_try_merge` 统一传 `stage` 关键字后，`_android_check` 3 处旧 3 参 merge_doc mock TypeError（v022-主AI注入拆书技法断言曾短暂失败）→ 已升级为 4 参；
  - 验证：`_android_check` **217 项 ALL_OK**（v022 注入恢复）；引擎 book_break.py 已同步；构建正式签名 APK（versionCode 34，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.32 智能拆书·按上下文定档（与桌面 v0.59 对齐；智能模式三档子模式：保守/正常/激进 + L1 无意义章节名处理）**：
  - **智能模式三档子模式**：智能模式下新增「档位」——保守（≈上下文12%）/ 正常（≈25%，默认）/ 激进（≈40%），引擎按模型上下文长度自动换算每部分 token（夹紧 8000~200 万）；「上下文长度」输入（0=自动：优先用「拉取模型」时网关返回的 context_window，其次默认 262144 兜底）；**1M 上下文激进档 ≈ 41 万 token 一段（约 409600）**，2 千万字长文也能快速拆完；262144 三档 ≈ 3.1 万 / 6.5 万 / 10.5 万（稳/均衡/快速）；拆书开始日志打印生效的上下文来源与每部分章数；
  - **L1 无意义章节名**：自动编号/空标题占比 ≥ 50% 时，L1 标题批每条带「开头：前 80 字采样」让 AI 结合采样概览（不再只看无意义编号）；
  - **L3 智能自动分批**：单元数多时按上下文自动分批汇总（每批 ≤ 上下文 32%），单元少时一次合并；高级模式仍手填；
  - 设置键：`break_smart_sub` / `model_context_window`（settings_get/save 往返，非法档位拒绝、负值钳制 0）；拆书页与导入卡 UI：`break-smart-seg`/`import-smart-seg`（保守/正常/激进）+ 上下文输入，智能模式下自动隐藏手填 token；
  - 验证：`_android_check` 扩至 **217 项 ALL_OK**（v032-档位键往返/非法拒绝/负值钳制/换算与引擎一致/HTML-JS 结构）；构建正式签名 APK（versionCode 33，29MB，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.31 拆书工坊整改（与桌面 v0.58 对齐；保存直接可用 / 设置归位 / 三档模式 / 重叠 / L3 后手 / 输出加厚）**：
  - **修复「没法保存」**：拆书结果拆完即可直接「保存为拆书风格」存入风格库（桌面端此按钮此前从未启用——本轮修复；安卓端本就可用，两端保持一致）；
  - **设置归位（API 设置页只放 API 设置）**：设置页删掉拆书每部分 token / 并行串行 / 并行数 / 总提示词（只保留「拆书工坊 / 小说导入成项目 API 配置」两个下拉）；拆书参数全部移到「拆书工坊」页与「小说导入成项目」卡里（不再两份设置不知道用哪个）；
  - **拆书三档模式**：简单（基本参数，token 限 32000 + 并行/串行，智能模式抽风时兜底）/ **智能（默认，按每部分 token 预算自动切分）** / **高级（每部分 token 不卡上限到 200 万 + 重叠 token（相邻部分衔接连贯）+ 并行数 + 总提示词 + L3 分批汇总后手（每批单元数，0=一次合并全部，长文怕上下文不够时设小））**；模式切换自动显隐字段；
  - **输出加厚（还原原小说七八成）**：拆书文档上限 5 万 → **8 万字**、学习文本 4000 → 6000 字——事件带「推进要点（重要节点怎么一步步推进）」、人物带「关系进展（因哪些事件感情更进一步/反目）+ 性格刻画（通过哪些细节/事件体现）」（明确 NPC/龙套不写）、每部分带故事概述；引擎与桌面同源（`book_break.py`/`novel_import.py` 已同步，含重叠切分与 L3 分批）；
  - 验证：`_android_check` 扩至 **209 项 ALL_OK**（v031-模式三档键/非法模式拒绝/重叠换算/HTML-JS 结构断言：模式 seg、重叠/L3 字段、saveBreakSettings、设置页去重复、≤8 万文案）；构建正式签名 APK（versionCode 32，29MB，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.30 API 兼容修复（与桌面 v0.57 对齐）：llm.py 端点智能拼接 `_endpoint(base_url, path)`——兼容「网关根」与「完整端点（vibecoding 习惯）」两种 base_url 填法，不再重复拼出 `/chat/completions/chat/completions` 404；fetch_models 同步兼容；HTTP 400/404 报错给出排查提示（含火山豆包 ep- 端点 ID）。实测商汤端点/模型/路径正常（200、1s 返回），慢来自推理模型思考 + 429 限流重试 + 重负载，非配置错误。构建正式签名 APK（versionCode 31，29.1MB，CN=XinghuoPen 同签名可覆盖安装）。**

- **v0.29 整改（与桌面 v0.56 对齐；API 设置页补拆书/导入 API 选择、教程页、导入规划栏）**：
  - **API 设置页**：「拆书工坊 API 配置」手填小输入框改为**下拉选择**（列出全部已保存配置名，留空跟随全局）；新增「小说导入成项目 API 配置」下拉（留空跟随拆书工坊）；保存写入 `break_profile` / `import_profile`（settings_get/save 往返）；
  - **教程页**：底部导航新增「教程」tab，页内 seg 分页（快速上手/写作/角色/项目/拆书/设置，`tutShow` 切换），按「它解决什么 → 怎么用 → 小提示」介绍主要功能；
  - **导入规划栏**：import-card 新增「小说规划（整体介绍）」输入（`import_intro`）——导入的大多是未完成的小说，把剧情设计/方向/主题/已有情节到哪告诉 AI，拆书/逐块人物抽取/角色卡/管理笔记各环节都会参考，防止因情节缺失被带偏；移除手打 API 配置输入框；
  - 验证：`_android_check` 扩至 **199 项 ALL_OK**（v029-教程tab/分页、拆书与导入 API 下拉、规划栏、settings 往返、规划注入）；构建正式签名 APK（versionCode 30，29MB，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.28 整改（与桌面 v0.55 对齐；顶部入口按钮移除 / 导入设置界面 / 断点续传 / 停止立即生效）**：
  - **顶部入口按钮移除**：书架行不再放「✨ 一键成书」「📥 小说导入成项目」按钮（卡片内已有功能按键）；book-card / import-card 常驻展开（卡片内「收起」折叠）；
  - **导入设置界面**：import-card 新增「导入设置」区（拆书每部分 token / 并行·串行 + 并行数 / 拆书 API 配置 / 拆书总体提示词 + 保存导入设置，写入 config 拆书设置键与设置页同步）；三个默认选项（保存拆书风格/生成设定与角色卡/导入章节正文）移除（默认全做）；
  - **断点续传（拆书工坊 + 小说导入成项目）**：`break_start`/`import_start` 自动创建 job 目录（data/jobs/），各环节结果即时落盘——API 出错/停止/软件退出后对同一 txt 再启动自动跳过已完成环节（任务日志提示"自动续传"）；完成即删；落库幂等（续传复用已建项目，不重复新建）；
  - **停止立即生效**：任务线程绑定停止事件，`break_stop`/`import_stop`/`book_stop` 置位后 **LLM 调用立即断开当前请求**（不再等本次请求写完），未 finalize 的章节不落盘（已归档保留）；`generate` 全自动任务同样立即中断；
  - 验证：`_android_check` 扩至 **190 项 ALL_OK**（v028-顶部按钮移除/卡片常驻+设置控件/引擎级续传跳过已完成/停止后任务快速结束且不建项目）；构建正式签名 APK（versionCode 29，29MB，CN=XinghuoPen 同签名可覆盖安装）。
- **v0.27 小说导入成项目（与桌面 v0.54 对齐；把一本 txt 小说还原成完整项目，删除章节后角色卡自动回退）**：
  - 项目页书架卡新增「📥 小说导入成项目」入口，展开为常驻卡片（`import-card`，与一键成书平级）——「选择小说 txt」（复用系统文件选择器桥 → `imports/picked.txt`）→ 解析预览（卷/章/字数）→ 书名 → 三选项（保存拆书风格 / 生成设定与角色卡 / 导入章节正文）→ 开始 / 停止 / 进度 / 日志；
  - **还原管线**（`novel_import.py` 双端同源）：解析（保留全章正文）→ 复用拆书四阶段管线（中间结果骨架/卷细纲回传）→ 设定合成（剧情/世界观/规则/文风/风格要点/设定锚点/伏笔/管理笔记）→ 逐块人物抽取（新角色 + 分章状态轨迹，支持并行）→ 名册全名匹配定每章出场 → 批量角色卡 → 章节原样 approved 入库；
  - **删除章节 → 角色卡回退**：角色卡含分章状态轨迹 `chapter_states`，`chapter_delete` 后自动 `rebuild_world_after_delete`（不再出场的角色删卡、保留者回退处境/状态、信息库与伏笔台账截断）；导入项目无逐章快照时「重写此章」自动走轨迹回退兜底；
  - 新路由：`import_start`（任务化，可停止）/ `import_stop`；`__breakTxtReady` 同时刷新拆书与导入两处预览；
  - 验证：`_android_check` 扩至 **180 项 ALL_OK**（v027-导入任务/统计/切换/风格入库/章节原样/角色建立/删章回退/停止）；构建正式签名 APK（versionCode 28，29MB，CN=XinghuoPen 同签名可覆盖安装）。

- **v0.11** 全功能移植（项目设定/角色管理/逐章与全自动生成/故事档案/去AI味/审稿/导出/多配置）；
- **v0.12** UI 重设计 + 自绘图标 + 生成任务异步化实时进度（毛玻璃/大圆角卡片/五步指示器/沉浸阅读）；
- **v0.13 项目对接（与 PC 端互导）**：`storage.export_project`/`import_project`（PC 端同款格式，自带防冲突与防 zip-slip）——
  - **导出**：打包整个项目（设定/角色+信息库/章节/伏笔/锚点/快照）为 zip → **系统分享面板**发送（微信/网盘/数据线拷到 PC），PC 端「项目」页导入即可无缝续写；
  - **导入**：PC 端导出的项目 zip 通过**系统文件选择器**选入（MainActivity `ACTION_OPEN_DOCUMENT` 桥 + FileProvider），导入后自动成为当前项目；
  - Java↔Python 桥：`MainActivity` 传入 Python（`start_app(files_dir, this)`），Python 调 `pickZip()`/`shareFile()`，选择结果经 `onActivityResult` 写 `filesDir/imports/picked.zip` 并回调前端 `window.__importReady`；
  - 单项目语境：`_CURRENT_DIR` 记录当前/最近导入项目，项目页直接编辑。
- **v0.14 横屏 = PC 版布局 + 屏幕方向切换**：转横屏自动切换为与电脑端完全一致的界面——左侧 208px 固定导航（标题/项目名/**项目→角色管理→小说生成→去AI味→故事档案→设置**六入口，顺序与名称同 PC 版）+ 右侧工作区（写作页两栏：左=项目信息+生成控制+草稿箱，右=正文+推理日志）——
  - **方向切换三选**：设置页「屏幕方向」跟随系统/竖屏/横屏，顶栏与侧边导航都有「⇄ 横屏 / ⇄ 竖屏」一键切换；选择记忆在本地（重启生效）；
  - **旋转不丢内容**：manifest 声明 `configChanges`（orientation|screenSize|screenLayout|smallestScreenSize|keyboard|keyboardHidden|uiMode），旋转仅触发 CSS 重排——WebView 不重建，方向/剧情点/草稿等输入框内容原样保留；
  - 竖屏维持移动端五页签布局；横屏「去AI味」入口对齐 PC 版：无当前草稿时从已归档章节列表选择治理。
- **v0.14 修复版**：①「⇄」切换改为按**当前实际屏幕方向**取反（此前在"跟随系统"模式下若屏幕已是目标方向会点起来"没反应"）；②Java 侧 `setRequestedOrientation` 移入 UI 线程（HTTP 后台线程跨线程调用在部分 ROM 无效）；③`localStorage` 读写异常时降级为内存记忆，方向请求不受影响。
- **v0.15 生成前剧情点确认关卡 + EPUB 导出系统分享**：与 PC 端确认关卡对齐——设置页开关（默认开），生成时主AI校验完**先弹窗展示本章剧情点清单与走向**（可逐条增删改），「确认，按此继续生成」用你的剧情点写正文 /「跳过」沿用主AI规划；全自动连写每章把关；任务化机制：任务线程在确认点**暂停**（task_status 返回 pending + 剧情点），前端弹窗后 `task_confirm` 放行（`threading.Event` 同步，不阻塞不丢结果）；EPUB 导出复用桌面端 `export_novel_epub`（纯 Python 标准库、EPUB3：mimetype 首文件 + container/opf/nav/toc.ncx + 每章 xhtml），导出后**自动弹系统分享面板**（Java `shareFile` 按扩展名识别 MIME：epub/zip/txt）。
- **v0.16 多项目书架 + 语音码字**：项目页顶部新增**我的书架**——列出全部项目（书名/进度/章节数/角色数，当前项高亮），点选即切换，非当前项目可删除（确认后不可恢复）；「＋ 新建项目」进入新建语境（防 fallback 标记 `_NEW_MARK`，填好保存才真正创建，不再误建空项目）；**保存语义修正**：有当前项目=更新（`project_save`，可改名），无当前项目=新建（`project_create`）——此前保存总是新建导致项目堆积；语音码字——写作页「🎤 语音码字」唤起**系统语音识别面板**（RecognizerIntent，zh-CN），识别文本经 Java `onActivityResult` 回调 `window.__voiceReady` **插入当前聚焦输入框的光标处**（无聚焦插到正文编辑区）。
- **v0.18 UI 图标化·质感升级（与桌面 v0.52 同步；用户指示"多上网找点图片图标美化界面"）**：下载 **Bootstrap Icons 1.11.3（MIT）** 33 枚 SVG 到 `assets/www/icons/`（npmmirror CDN；GitHub/jsdelivr 不可达）；**图标体系**——底部/侧边导航 emoji 全部换成 SVG 图标（CSS `mask + currentColor` 随主题变色：写作 pencil/角色 people/档案 book/项目 folder2-open/设置 gear/去AI味 stars），顶栏 logo 加金色铅笔图标（渐变 mask）、语音码字/导出TXT/导出EPUB/项目导入导出/通过/重新生成等主按钮图标化、空状态（角色/时间线/书架）emoji 换图标；**质感**——body 背景径向光晕（左上金/右下蓝）+ 深蓝黑线性渐变（background-attachment:fixed）、卡片渐变光泽（顶部高光边框）、导航图标透明度切换选中态。

- **v0.26 一键成书独立 UI（与桌面 v0.53 对齐；一键成书从弹窗改为项目页内独立卡片界面，与新建项目平级）**：
  - 项目页内新增常驻「✨ 一键成书」**独立卡片**（`book-card`，非弹窗；默认收起，点书架卡「✨ 一键成书」展开）——基本提示词框 / 小说总章节数 / 本次生成到多少章 / 开始 / 停止 / 进度条 / 日志 / 完成结果全部在卡片内，即"从创建项目到设计细节全打包的一次性流程"且全程可控可中断（写完当前章停，项目正常建好）；
  - `bookStart` 改为展开/收起卡片；`showBookPanel` 直接操作卡片内元素（不再弹 modal）；完成/停止后刷新书架与状态；
  - 验证：`_android_check` **164 项 ALL_OK**；构建正式签名 APK（versionCode 27，29MB，CN=XinghuoPen）。

- **v0.25 一键成书设置（与桌面 v0.52 对齐；一键成书可设置基本提示词/小说总章节/本次生成到多少章，可中断且中断后项目正常建好）**：
  - **一键成书弹窗三输入齐全**（`bookStart` 弹窗）：基本提示词/小说想法 + **小说总章节数（全书计划，默认 30，写入项目 volume_target + state.volume_plan，主AI按此规划节奏与完本判断，可改）** + **本次一键生成到多少章（默认 5，可小于总章节数）**——先写开头几章，风格满意后继续；`bookSubmit` 传 `total_chapters`；
  - **中断可用**：进度面板「停止」按钮（`bookStop`，写完当前章后停，项目已建好保留书架）；
  - 验证：`_android_check` 扩至 **164 项 ALL_OK**（v021-总章节数写入项目目标 30）；构建正式签名 APK（versionCode 26，29MB，CN=XinghuoPen）。

- **v0.24 整改（用户指正三处，与桌面 v0.51 对齐）：①拆书只做了导出没做导入 → 拆书页新增「导入拆书文档」**（系统文件选择器选 txt/md/json → `break_import_doc` 路由（fname 读文件/content 直传）→ `book_break.import_break_from_text`（JSON 识别 learning；纯文本全文为 doc；learning 缺失时主AI注入退化为取 doc 前缀）→ 存为拆书风格 → 可应用到当前项目）；**②一键成书不该在小说生成页 → 入口迁移到「项目」页书架卡**（写作页按钮移除）；**③拆书工坊看不到提示词 → 拆书页顶部新增「拆书总体提示词（大方向；留空=照常）」+「每部分 token」+「保存提示词/预算」**（`saveBreakPrompt` 写 config，`initBreakTab` 回填，与设置页同步）；验证：`_android_check` 扩至 **163 项 ALL_OK**（v022-拆书文档导入 content/fname/可读/删除）；构建正式签名 APK（versionCode 25，29MB，CN=XinghuoPen）。

- **v0.23 拆书设置（与桌面 v0.56 对齐；拆书按 token 预算拆分 / 单独选 API / 并行串行可切 / 总体提示词大方向）**：
  - 设置页新增**拆书设置**字段：**每部分 token 预算**（默认 8000，决定每部分含多少章——由预算÷每章采样估算自动推导）、**拆书 API 配置**（填写已保存配置名，拆书四阶段全走该配置，留空跟随全局；`llm.chat` 支持显式 profile）、**并行/串行 + 并行数**（并行时标题批与卷细纲单元并发，L1 骨架/L3 汇总始终串行；默认串行）、**拆书总体提示词**（可选大方向：如"重点分析日常情节与人物塑造"或"更看重脑洞与哲思"；留空=照常，只改关注重点不改拆书结构）；
  - 设置保存经 `settings_save`（break_profile/break_token_per_part/break_parallel/break_parallel_n/break_prompt），`settings_get` 回填；拆书任务运行时引擎自动读这套设置（`book_break.break_settings()`）；
  - 验证：`_android_check.py` 扩至 **159 项 ALL_OK**（v022-拆书设置保存/读取往返、预算换算与引擎一致、带设置（并行+提示词+单独API）拆书任务完成）；构建正式签名 APK（versionCode 24，29MB，CN=XinghuoPen）。

- **v0.22 拆书工坊（与桌面 v0.55 对齐；导入 txt 长篇小说 → AI 拆书 → 保存风格 → 主AI学习设计技法）**：
  - **底部导航新增「拆书」tab**（横屏侧边导航同样有「拆书工坊」入口）：`pick_txt` 唤起系统文件选择器选 txt（MainActivity `pickTxt` 桥 → imports/picked.txt → `__breakTxtReady`）→ `break_parse` 分卷分章预览（无卷标自动分卷/序章楔子/超长兜底）→ `break_start` 任务化拆书（进度条 + 日志 + 停止）→ 结果预览 → `break_save` 保存为拆书风格 → `break_apply` 应用到当前项目 → `break_export` 导出 txt + 系统分享；
  - **四阶段拆书管线**（`book_break.py`，双端引擎一致，应对 3000 章长文并维系整体性）：L1-a 章节标题流分批概览 → L1-b 全书骨架（主线/分卷任务/核心人物/**全局伏笔池**/技法，先立骨架避免拆碎）→ L2 逐卷事件细纲（**事件拆分：起止章/章数/推动方式/冲突/高潮** + 伏笔埋设含**日常式伏笔** + 回收 + 人物变化）→ L3 汇总压缩（拆书文档 ≤5 万字 + 设计技法学习文本 ≤4000 字）；
  - **主AI学习**：`project.story_break_style` 挂风格后，`prompts.main_system` 注入【拆书风格参考】——学剧情推动/伏笔设计/人物塑造技法，**不照抄情节**；
  - **安卓路由**：`pick_txt` / `break_parse` / `break_start`（任务化，`task_status` 增补 progress 阶段）/ `break_stop` / `break_save` / `breaks_list` / `break_load` / `break_delete` / `break_apply` / `break_export`（9+1 个）；`_state` 增补 `break_style`；
  - 验证：`_android_check.py` 扩至 **154 项 ALL_OK**（v022-解析统计/缺文件拒绝/无activity报错/任务完成/结果含doc/保存/列表/读取/应用/主AI注入拆书技法/导出txt/停止指令/删除后列表空）；构建正式签名 APK（versionCode 23，29MB，CN=XinghuoPen）。

- **v0.21 一键成书（与桌面 v0.54 对齐；完全自动生成：描述小说 + 章节数 → AI 自动立项/世界观/所有事宜）**：
  - 写作页顶行新增「✨ 一键成书」——只需描述你想写什么小说 + 设置章节数（1~100），AI 自动完成：**起书名**（`plan_title`）→ **起草三栏设定**（剧情/世界观/特殊规则，`plan_story_ai` 注入章数约束）→ **创建项目**（书架可见、自动成为当前项目）→ **生成核心角色**（`ensure_world`）→ **全自动连写 N 章**（复用 `generate_draft + finalize_chapter` 逐章定稿）；
  - **随时可停止**：进度面板「停止」按钮 → 写完当前章后结束，已写章节完整保留；**停止/完成后项目保留在书架**，可像普通项目一样继续写/改设定/重写章节——省去手动立项的一堆设置；
  - **任务化**：`book_auto` 路由提交任务（t["stop"] 置位停止、t["progress"] 上报已写/目标），前端 `bookStart/bookPoll/bookStop` 轮询展示日志 + 进度条，`task_status` 增补 progress 字段；
  - **顺手修复存量 bug**：前端全自动模式调 `generate_auto` 路由但后端未注册（404）——新增 `_do_generate_auto` 别名（强制 mode=auto）；
  - 验证：`_android_check.py` 扩至 **137 项 ALL_OK**（v021-空描述/非法章数拒绝、成书任务完成+书名+1章、项目入书架、成为当前项目、章节完整、停止指令+提前结束+章数不超+项目保留、generate_auto 路由）；构建正式签名 APK（versionCode 22，29MB，CN=XinghuoPen）。

- **v0.20 写作工作台 Pro（与桌面 v0.53 对齐；用户指示"大胆改"，补齐安卓最后四个 PC 缺口 + 三个新能力）**：
  - **AI 段落工具**：写作页新增「AI 段落工具」按钮——选中任意输入框中的一段文字 → 弹窗选处理方式（文笔润色/扩写补足/精简浓缩/去AI味）→ 后台处理 → 可手动微调 → 「替换选中文本」就地写回（后端 `polish` 路由 → `main_ai.polish_paragraph`；上限 6000 字）；
  - **全文搜索**：档案页时间线顶部新增搜索框——标题/梗概/正文三路匹配（后端 `search` 路由 → `storage.search_chapters`），结果列表点击直接打开对应章节；
  - **章节交换（排序）**：章节详情新增「⇄ 交换章节…」——输入目标章号，两章标题/正文/梗概/出场角色/场景/伏笔/卷归属互换（章号不变，不破坏世界快照回滚语义），旧版自动备份草稿箱（后端 `swap` 路由）；
  - **写作统计仪表盘**：档案页新增「统计」页签——总字数（千分位）/已写章数/当前卷目标与进度条/各卷分布表（后端 `stats` 路由 → `storage.project_stats`）；
  - **重写此章（世界状态回滚，补齐 PC 缺口）**：章节详情新增「↺ 重写此章」——回滚世界状态（角色卡/信息库/伏笔/管理笔记）到该章开始前，删除该章及之后全部章节，进度回退到该章可重新生成；被删章节自动备份草稿箱（后端 `rewrite` 路由 → `engine.rewrite_from`，与 PC 端同语义）；
  - **整卷合并（补齐 PC 缺口）**：章节详情新增「分卷管理」——卷分布一览 + 输入"把第 X 卷并入第 Y 卷"，整卷迁移后空卷消失（后端 `volume_merge` 路由 → `store.rename_volume`）；
  - **听写历史（补齐 PC 缺口）**：语音码字识别文本自动记入**听写历史**（localStorage 最近 10 条），写作页展示时间+内容，点击一键回填到当前输入框；可一键清空；
  - 验证：`_android_check.py` 扩至 **123 项 ALL_OK**（v020-段落润色/扩写/空文本/超长拒绝、搜索命中/无命中/空词、章节交换+备份+同章拒绝、写作统计聚合、重写此章成功路径+进度回退+其后章节删除、整卷合并+同卷/非法卷拒绝）；构建正式签名 APK（versionCode 21，29MB，CN=XinghuoPen）。

- **v0.19 补齐 PC 功能 + 自动拉取模型**（用户问"做了自动获取模型 id 吗？感觉缺功能"后系统盘点补齐）：
  - **模型自动拉取**：设置页打开且已填 API 地址/Key 时**静默自动拉取**模型列表填入原生下拉（`<datalist>`），点模型输入框直接选；「拉取模型」弹窗点选保留（`llm.fetch_models`）；
  - **编辑已归档章节**：时间线章节详情新增「✎ 编辑本章」（改标题/正文，**原版自动备份到草稿箱**——`chapter_edit` 路由先 `backup_chapter_draft` 再保存，对齐 PC 章节管理）；
  - **主AI知识库**：档案页新增「知识库」页（`project.story_knowledge`，主AI长期记忆——联网灵感/设定落定/伏笔关键信息，只读展示）；
  - **生成日志**：档案页新增「生成日志」页（`store.read_log(300)`，与 PC 端同源）；
  - **TXT 导出系统分享**：导出 TXT 后自动弹系统分享面板（此前只有 EPUB 能分享）。

## 目录结构

```
星火笔-android/
├── settings.gradle / build.gradle / gradle.properties     # Gradle 工程
├── app/
│   ├── build.gradle                                       # Chaquopy 17 + 签名配置
│   └── src/main/
│       ├── AndroidManifest.xml
│       ├── java/com/xinghuobi/novel/MainActivity.java     # 起 Python + WebView
│       ├── python/                                        # 复用桌面端引擎（无 PySide6 依赖）
│       │   ├── android_server.py                          # 本地 API 服务器（全功能）
│       │   ├── engine.py main_ai.py char_ai.py prompts.py
│       │   ├── storage.py models.py config.py llm.py web_search.py
│       │   ├── git_tool.py export_utils.py name_gen.py
│       └── assets/www/                                    # 移动端前端（index.html/style.css/app.js）
├── scripts/
│   ├── make_release_keystore.bat                          # 生成 release 签名（keytool）
│   └── build_apk.bat                                      # 构建指引
└── README.md
```

## 构建（已实测产出正式签名 APK，2026-09-30）

前置：**JDK 17** + **Android SDK（platform-34 / build-tools 34 / platform-tools）** + **Python 3.10**（构建机需 Python 3.10，与 Chaquopy 默认运行时一致）。
无需安装 NDK（Chaquopy 17 的 Python 解释器是预编译的）。

本机构建环境位于 `F:\download\work file\novel\.android-tools`（非 C 盘，用完整体删除即可清理）：
`jdk-17.0.12+7` / `sdk` / `gradle-8.7`。

1. **生成 release 签名（只需一次，长期复用升级安装）**：
   ```bat
   scripts\make_release_keystore.bat
   ```
   产物：`app/release.keystore`（**务必妥善备份**——后续版本用同一签名才能覆盖安装）
   + `app/keystore.properties`（已 .gitignore，不入库）。
2. **构建**（注意：Windows 上 AGP 拒绝非 ASCII 工程路径——「星火笔-android」含中文，需先复制到纯 ASCII 路径再构建）：
   ```bat
   robocopy 星火笔-android F:\download\work file\novel\.android-tools\build\src /E /XD .git app\build build .gradle
   set JAVA_HOME=...\.android-tools\jdk-17.0.12+7
   set ANDROID_HOME=...\.android-tools\sdk
   ...\.android-tools\gradle-8.7\bin\gradle.bat --no-daemon -p ...\.android-tools\build\src assembleRelease
   ```
3. 产物：`app\build\outputs\apk\release\app-release.apk`（约 29MB，arm64-v8a + x86_64，已含正式签名 CN=XinghuoPen）。
4. 验签：`apksigner verify --print-certs app-release.apk`（`sdk\build-tools\34.0.0\apksigner.bat`，需 JAVA_HOME）。

## 构建踩坑记录（开发日志）

- **非 ASCII 工程路径**：AGP 在 Windows 拒绝中文路径（`b.android.com/95744`），报错 `Your project path contains non-ASCII characters` → 复制到 ASCII 路径（如 `.android-tools\build\src`）构建，产物拷回。
- **keystore.properties 尾随空格**：`echo` 写入 properties 后值带行尾空格，Java `Properties.load` **保留尾部空白** → 密码变成 `xinghuobi2026 ` 导致 `keystore password was incorrect` → build.gradle 的 signingConfigs 对所有属性 `.trim()` 兜底。
- **Chaquopy 17 无 NDK**：`There's no need to actually install the NDK, as all of Chaquopy's native libraries are already pre-compiled`——只装 platform/build-tools/platform-tools 即可。
- **构建机 Python 版本**：必须与应用运行时主次版本一致（默认 3.10）；Windows 默认找 `py -3.10` / `python`。

## 与 PC 端对接（v0.13）

1. **PC → 手机**：PC 端「项目」页导出项目 zip → 传到手机（微信/网盘/数据线）→ 手机「项目」页点「导入项目 zip」→ 系统文件选择器选该 zip → 自动成为当前项目，章节/角色/设定/伏笔全量续写。
2. **手机 → PC**：手机「项目」页点「导出项目 zip」→ 系统分享面板发送到电脑 → PC 端「项目」页导入即可。

## 首次使用

1. 打开 App → 「设置」页填入你的 API 地址 / Key / 模型（与桌面端同一套配置，数据独立存放于 App 私有目录）。
2. 「设定」页填写 书名/简介/世界观/特殊规则 → 保存。
3. 「写作」页填方向（可选）→ 「生成下一章」：本地 RP 管线跑完显示推理过程日志 + 正文（可编辑）
   + 主AI审查（意图/剧情点/评分/套路检测/AI八股治理）。
4. 满意点「通过并完成本章」定稿；不满意填意见「凭意见重新生成」。

## 与桌面端的差异（安卓版 v0.20）

| 项 | 桌面端 | 安卓版 v0.20 |
| --- | --- | --- |
| 界面 | PySide6 桌面 | WebView + 移动端前端：**竖屏五页签**；**横屏 = PC 版布局**（左侧导航六入口 + 右侧工作区，写作页两栏） |
| 一键成书 | 生成页「✨ 一键成书」对话框（描述+章数 → 自动立项连写，可停止，进度日志面板） | 写作页顶行「✨ 一键成书」弹窗（同语义，任务化进度条+日志+停止；停后项目保留书架） |
| 项目 | 多项目/书架 | **多项目书架**（列表切换/新建语境/删除非当前；项目页直接编辑，可导入导出/改名） |
| 生成 | 逐章/全自动/剧情点确认关卡 | 逐章/全自动连写/剧情点/草稿/重写此章；确认关卡弹窗（确认/修改/跳过） |
| 段落工具 | 正文区选中文本 → 润色/扩写/缩写/去AI味 → 替换 | 任意输入框选中文本 → AI 段落工具（同四模式，弹窗预览后替换） |
| 搜索/统计 | 章节管理内全文搜索 + 写作统计对话框 | 档案页时间线搜索框 + 「统计」页签（总字数/卷分布/进度条） |
| 章节排序 | 章节管理「交换章节…」 | 章节详情「⇄ 交换章节…」（章号不变，旧版备份草稿箱） |
| 分卷 | 时间线按卷分组 + 分卷管理对话框（归卷/整卷合并） | **时间线按卷分组 + 归卷 + 分卷管理（整卷合并）** |
| 角色 | 完整角色卡+信息库+批量/分类/导入 | 全字段编辑+信息库+AI生成/批量/分类/导入（酒馆 JSON）/随机起名；横屏列表两列 |
| 故事档案 | 时间线/伏笔看板/管理笔记/阅读元信息 | 同左（时间线/伏笔回收恢复/管理笔记/章节详情元信息/知识库/生成日志） |
| 去AI味 | 独立页（任选章节治理） | 治理（clean/replace/rewrite）→查看→采用合并（原稿自动备份）；横屏入口可从已归档章节选择（对齐 PC 版） |
| 语音码字 | 对话框录音→在线识别→插入光标（SpeechRecognition+pyaudio） | **系统语音识别面板**（RecognizerIntent zh-CN）→识别文本插入当前输入框光标处 + **听写历史**（最近 10 条可点击回填） |
| 导出 | TXT/EPUB/项目包（均按卷分组） | TXT（完整+分章文件夹，按卷分组）/ EPUB（系统分享，按卷分页）/ 项目 zip 互导 |
| 存档 | git | 无 git 时自动跳过（数据持久化在私有目录） |

## 已知限制

- 首次生成耗时取决于 API 与模型（与桌面端相同）；期间请勿切换页面。
- 横屏 PC 布局是移动端对 PC 版布局的忠实还原（左侧导航 + 右侧工作区），各页功能与竖屏一致，非像素级克隆。
- 所有数据只存 App 私有目录（卸载即清空）；TXT 导出到私有目录 export/。

## 版本规划（安卓序列）

- v0.10 核心闭环 / v0.11 全功能移植 / v0.12 UI 重设计·实时进度
- v0.13 项目对接：与 PC 端互导（zip 系统分享/文件选择，单项目语境）
- v0.14 横屏 PC 版布局：方向切换三选 + 左侧导航六入口 + 写作页两栏
- v0.15 剧情点确认关卡 + EPUB 导出系统分享
- v0.16 多项目书架 + 语音码字
- v0.17 分卷管理（时间线按卷分组 + 章节详情归卷 + 导出按卷）
- v0.18 UI 图标化·质感升级（Bootstrap Icons SVG 图标体系 + 渐变背景/卡片光泽）
- v0.19 补齐 PC 功能：模型自动拉取、编辑已归档章节、主AI知识库、生成日志、TXT 分享
- v0.20 写作工作台 Pro：AI 段落工具、全文搜索、章节交换/排序、写作统计、重写此章（世界回滚）、整卷合并、听写历史——与 PC 功能**完全拉平**
- v0.21 一键成书：描述小说 + 章节数 → AI 自动立项（书名/剧情/世界观/规则）→ 建项目 → 生成核心角色 → 全自动连写 N 章；随时可停止，停后项目保留书架
- v0.22 拆书工坊：导入 txt 长篇小说 → AI 四阶段拆书（标题概览/全书骨架/逐卷事件细纲/汇总）→ ≤5 万字拆书文档 + 设计技法学习文本 → 保存拆书风格 → 应用到当前项目让主AI学习剧情推动/伏笔设计技法（不抄情节）→ 导出 txt 系统分享
- v0.23 拆书设置：每部分 token 预算切分 / 拆书单独选 API / 并行串行 + 并行数 / 拆书总体提示词（大方向：日常/人物/脑洞/哲思）
- v0.24 整改：拆书导入文档（对称补齐导出）、一键成书入口迁移到项目页、拆书提示词页内可见可保存
- v0.25 一键成书设置：基本提示词 / 小说总章节数（写入项目目标）/ 本次生成到多少章（可小于总章节）/ 随时中断且项目正常建好
- v0.26 一键成书独立 UI（本版）：项目页内常驻一键成书卡片界面（与新建项目平级，非弹窗）——全参数可控、进度日志、随时中断
