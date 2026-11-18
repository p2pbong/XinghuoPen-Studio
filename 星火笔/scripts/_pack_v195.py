# -*- coding: utf-8 -*-
"""打包星火笔 v1.95（一键成书起草的故事设定/世界观/特殊规则输出结构硬性规范化：
   故事栏四段（主线总判→卷划分含起止章号→卷内事件→结尾方向）、世界观五栏、特殊规则三栏，
   栏名必须全出现（无则写『栏名：无』）、禁空洞词、字数下限拉高（story 400-900/world 300-800/
   rules 200-600）；与用户是否提供主AI提示词/拆书文档无关——无预设也照样结构化）。
   含 data 用户数据：config.json + breaks + style_extract。"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.95(一键成书设定结构规范化).zip"

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

names = [rel for _, rel in files]
assert not any(n.lower().endswith((".bat", ".cmd")) for n in names), "包内不应再有 bat"

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for full, rel in sorted(files):
        z.write(full, "星火笔/" + rel)
print("ZIP_OK", len(files), "files ->", OUT)