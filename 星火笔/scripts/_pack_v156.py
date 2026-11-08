# -*- coding: utf-8 -*-
"""打包星火笔 v1.56（提取预设·回归心动可乐满意版格式：以用户放回心动可乐目录的
「最满意但剧情污染」版为基底重建 node_a——恢复【什么是技法/风格】【提炼维度】
【情绪浓度适配】【产出要求】格式化名目；剧情污染修复=源头强化（技法必须脱离本小说
独立成立）+严禁把原文桥段/微案例摘入产出+node_b 防复述+node_d 防新增原文桥段；
文风情绪场景防固化=【情绪场景防固化】专门名目；量化节奏细节以【量化节奏参考】名目
保留（用户 v1.52 明确要的）；node_d 保留 v1.55【产出严禁·输出形态】条款。
（便携 env + 源码 + 脚本 + data/config.json + data/breaks + data/style_extract）。
"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.56(提取预设回归满意版格式).zip"

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
