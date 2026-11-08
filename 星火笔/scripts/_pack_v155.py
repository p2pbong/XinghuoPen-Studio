# -*- coding: utf-8 -*-
"""打包星火笔 v1.55（提取预设防污染修复：剧情设计提取 top1/top2 曾输出「在排名第一
提示词第二十七节末尾增加以下内容」补丁式增量而非完整提示词——根因 config
style_d_see_top3 被开启(默认关防发散)导致 node_d 被要求「在排名第一基础上改进而
不是重写」；文风提取 top2/top3 曾带「你好，我无法给到相关内容。」拒绝语混入提示词。
修复=①源码 see_top3 追加措辞改为强制输出完整提示词、严禁增量补丁；②node_d 补
【产出严禁·输出形态】条款；③style_d_see_top3 关回默认 False）。
（便携 env + 源码 + 脚本 + data/config.json + data/breaks + data/style_extract）。
"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.55(提取预设防污染·完整提示词).zip"

EXCLUDE_DIRS = {".git", "data", "projects", "__pycache__"}
EXCLUDE_FILES = {"e2e.log", "release.keystore", "keystore.properties"}
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
