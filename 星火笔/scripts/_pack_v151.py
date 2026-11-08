# -*- coding: utf-8 -*-
"""打包星火笔 v1.51（文风/剧情设计提取预设·源头抽象+交叉验证优化+B/C/D 自由发挥配套：
用户要求——确认预设无遗漏、搜索网上 AI 剧情/文风把控经验做交叉验证后打包；
node_a 只产出跨题材抽象技法（剧情六维度含节奏/情感节拍/冲突层级递进/setup-payoff，
文风六维度含情绪浓度适配），node_b 尽量自由发挥（验证真学没学到而非表象），
node_c 配套标准（自由发挥下不依赖预设情节/结构、仅凭技法规则独立成立才算高分），
node_d 配套优化方向（自由发挥下稳定驱动、不越改越具体贴原文）。
（便携 env + 源码 + 脚本 + data/config.json + data/breaks + data/style_extract）。

v0.96 起按用户要求不再剔除 API 配置与 Key（data/config.json 随 zip）。
v1.43 起拆书文档（data/breaks/*.json）、文风校对预设（data/style_extract/*.json）
也随包（用户：打包拆书文档、情景卡还有文风校对的预设都不要清理，我都要用）。
其余 data/（话题/会话/工作区）仍不打包。
"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.51（提取预设源头抽象）.zip"

EXCLUDE_DIRS = {".git", "data", "projects", "__pycache__"}
EXCLUDE_FILES = {"e2e.log", "release.keystore", "keystore.properties"}
# v1.43 随包保留的数据子目录（拆书文档 + 文风预设 + 情景卡总库在 config.json）
KEEP_DATA_SUBDIRS = ("breaks", "style_extract")

files = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    base = os.path.basename(dirpath)
    if base == "data":
        dirnames[:] = [d for d in dirnames if d in KEEP_DATA_SUBDIRS]
    else:
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS or d == "data"]
    for fn in filenames:
        if fn in EXCLUDE_FILES:
            continue
        full = os.path.join(dirpath, fn)
        rel = os.path.relpath(full, ROOT)
        if rel.startswith("data" + os.sep):
            parts = rel.split(os.sep)[1:]
            if parts and parts[0] in KEEP_DATA_SUBDIRS:
                files.append((full, rel))
            continue
        files.append((full, rel))

cfg = os.path.join(ROOT, "data", "config.json")
if os.path.isfile(cfg):
    files.append((cfg, "data/config.json"))
else:
    print("WARN data/config.json 不存在，本次不打包")

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for full, rel in sorted(files):
        z.write(full, "星火笔/" + rel)
print("ZIP_OK", len(files), "files ->", OUT)