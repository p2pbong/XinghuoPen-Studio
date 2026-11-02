# 星火笔 XinghuoPen ✒️ AI 小说写作室 · AI Novel Writing Studio

> **中文：** 你想当导演，AI 分工当编剧、演员和写手。
> **English:** You are the director; AI plays the screenwriters, actors, and writers.
>
> 「主AI决断 + 角色推理 + 正文写作 + 审查验收」全自动自推理管线 / A multi-agent AI novel-writing pipeline:
> **Main-AI decides → Character-AI reasons → Writer-AI writes → Reviewer-AI verifies**.
> 电脑端 + 安卓端双端开源，数据完全本地化。 / Open source on both Windows (portable) and Android; all data stays local.

---

## 它解决什么问题 / What it solves

写长篇小说最累的不是打字，而是**剧情线**——伏笔下章忘了收、人物OOC、剧情失控、满屏 AI 腔。
Writing a long novel is hard not because of typing, but because of everything your brain has to track —
unfired Chekhov guns, characters going OOC, plots spiraling out of control, and AI-cliché prose.

星火笔把这些拆给**分工明确的 AI 代理**，你当导演只管改：
XinghuoPen splits it into role-specialized AI agents — you just direct:

| 代理 Agent | 职责 Role |
|---|---|
| 🧠 主AI / Main AI | 剧情节奏与世界观一致性 / pacing & world consistency |
| 🎭 角色AI / Character AI | 替每个角色独立推理"TA 此刻会怎么想怎么做" / reasons for each character |
| ✍️ 正文AI / Writer AI | 把推理结果写成文章 / turns reasoning into prose |
| 🔍 审查AI / Reviewer AI | 人设/逻辑/文风/禁词验收 / verifies character-logic, style, banned words |

---

## ✨ 特色功能 / Features

| 功能 Feature | 说明 Description |
|---|---|
| 🧠 自推理管线 / Self-reasoning pipeline | 主AI决断→角色推理→正文写作→审查验收，自动或半自动 / decide → reason → write → verify |
| ⚡ 全自动连写 / Full-auto writing | 审过一章自动写下一章，停止立即生效 / one chapter done, next starts; stop takes effect at once |
| ✍️ 一键成书 / One-click novel | 一句话想法→自动起名/立设定/建角色→开写；支持 AI 自动判断章节数 / a single sentence of idea → auto title/settings/characters → start; **AI-estimated chapter count** |
| 📥 小说导入成项目 / Import txt as project | 已有 txt（未完结的尤其合适）完整还原：拆书→建卡→入库→续写，断点续传 / rebuild an unfinished novel into a writable project, resume-ready |
| 🪄 去AI味·写后校对 / De-AI-ify & proofread | 一键清 AI 腔；正文完稿后按文风规则先校一遍 / clean clichés; proofread before review |
| 🎨 文风校对工坊 / Style workshop | A提取→B生成→C评分→D优化 多轮迭代，向参考原文靠齐 / extract→generate→score→optimize, iteratively |
| 📚 拆书工坊 / Book-breaking workshop | 几千章长篇小说拆成设计细纲（≤5万字），学技法不抄情节 / break novels into design outlines — techniques, not plots |
| 👥 角色体系 / Character system | 角色卡 + 主AI专属信息库（防剧透）；批量建档、酒馆卡互换 / cards + Main-AI-only KB (anti-spoiler); batch & SillyTavern interchange |
| 💬 AI 对话 / AI chat | 多话题；读项目设定/联网搜索开关；消息可编辑/重生成/续写/导出 / multi-topic; project-context & web-search toggles; message editing |
| 📖 故事档案 / Story archives | 时间线、伏笔台账、管理笔记、知识库——越长越不乱 / timeline, foreshadowing, notes, KB |
| 🎴 情景规则卡 / Scene rule cards | 高频场景写成"写法圣经"，主AI每章自动选卡注入 / per-scene style bibles auto-injected |
| 🌸🌿🌙 三套主题 / 3 themes | 樱粉/薄荷/二次元夜，运行时切换，只换皮肤不改功能 / switchable themes, colors only |

---

## 🚀 快速开始 / Quick Start

**Windows（免安装 / portable）**
1. 下载 `XinghuoPen-PC-v1.77-Portable.zip` 并解压 / download & extract;
2. 双击 `start.bat`（无黑窗直接出 UI）/ double-click `start.bat`;
3. 「设置」填入任意 OpenAI 兼容 API（DeepSeek/Kimi/通义/本地 LM Studio/llama.cpp）/ add any OpenAI-compatible API in Settings;
4. 「项目」→ 新建 / 一键成书，开始写 / create a project or one-click novel.

**Android**
安装 `XinghuoPen-Android-v1.49.apk`（Android 7.0+），数据仅存本机；🌐 联网搜索需网络，其余离线可用。
Install the APK; data stays on-device; only web-search needs network.

---

## 🏗️ 从源码构建 / Build from source

```bash
# PC
cd 星火笔
pip install -r requirements.txt
python src/main.py            # 或双击 start.bat / or double-click start.bat

# Android (Android Studio / Gradle)
cd 星火笔-android
# 自建 keystore 后 ./gradlew assembleRelease   / generate your own keystore first
# Chaquopy 17 预编译 Python（无需 NDK）minSdk 24 / targetSdk 34
```

## 🔒 数据与隐私 / Data & Privacy

项目、章节、角色卡、伏笔台账、拆书文档、预设**全部存本机/App 私有目录**，API Key 只存本地；本仓库发布包均为**无痕迹版本**（无用户数据/项目/API Key/签名密钥）。
All data stays local; release packages here are **trace-free** — no user data, projects, API keys, or signing keys.

---

## 📌 开发者注 / A Note from the Developer

本项目开发者是**中国人**——源码、注释、界面以中文为主。
The developer of this project is **Chinese** — source code, comments and UI are primarily in Chinese.

如果你需要英文版本，推荐**自行通过 vibe coding（AI 辅助改代码）修改**；
本项目的任何功能都可以自由修改、改进、扩展。如果你愿意，也欢迎把改好的版本分享回来。
If you need an English version, it is recommended that you **modify it yourself through vibe coding**
(any AI-assisted editing tool). The project is fully open source — you are welcome to change,
improve, or extend **any feature**. Contributions back are appreciated.

---

## ⚖️ 许可与免责 / License & Disclaimer

个人开发作品，开源仅供**学习交流**；产出的小说版权归创作者本人；默认不附带担保，许可证由发布者决定。
A personal project, open-sourced for **learning and communication**; produced novels belong to their creators;
no warranty implied; the repository license is decided by the publisher.
