# -*- coding: utf-8 -*-
"""打包星火笔 v1.61（紧急修复 v1.59 引入的严重 bug：llm.py _do_post 外层 try 被
transform 脚本拼错 except 顺序——except Exception 排在最前，把 StopRequested 和
abort close 触发的 ChunkedEncodingError 全吞掉按 200 空内容返回，正是"文风停止
反复失效"的深层根因；修复=外层 handlers 改为 [StopRequested, ChunkedEncodingError,
ConnectionError] + finally 注销。bug 检查 verify_bugcheck_v160.py ALL_OK 24 项）。
（便携 env + 源码 + 脚本 + data/config.json + data/breaks + data/style_extract）。
"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.61(停止bug紧急修复).zip"

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