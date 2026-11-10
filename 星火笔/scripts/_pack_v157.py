# -*- coding: utf-8 -*-
"""打包星火笔 v1.57（提取预设精简·回归心动可乐原文形态：用户指出我 v1.56 在提取
提示词里加了一大堆【】名目说明，导致 AI 提取时也爱模仿输出说明文——原本（心动可乐版）
的提示词没有这样搞。精简=node_a 回归心动可乐版原文一字不差（文风）/原文+三处半句
约束（剧情：防污染「技法必须能脱离本小说」、量化节奏「10~15%/50~60%/25~40%」、
防微案例「严禁把原文桥段摘入产出」），删除 v1.56 新增的大段名目
【情绪场景防固化】【量化节奏参考】；node_d 保留 v1.55【产出严禁·输出形态】防补丁条款）。
（便携 env + 源码 + 脚本 + data/config.json + data/breaks + data/style_extract）。
"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.57(提取预设精简回归原文).zip"

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
