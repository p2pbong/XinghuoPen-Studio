# -*- coding: utf-8 -*-
"""打包星火笔 v1.58（提取预设·详细度与迭代稳定性修复：用户质疑②文风提取 479 字太短——
node_a 没要求每个维度展开写，模型偷懒给概括版；修复=文风 node_a 内嵌「每个维度必须
展开写具体、完整角色卡形式输出、务必详细丰富」，商汤实测 479→2043 字。质疑①D 迭代
越改越糟——style_d_see_top3 被开启成 True（D 每轮拿第一名+分数叠加改进）+node_d 无防
收缩条款（优化时把提示词改短）；修复=开关关回默认 False + node_d 补【防越改越短】条款
（篇幅不得短于当前提示词、不得删减成提纲））。
（便携 env + 源码 + 脚本 + data/config.json + data/breaks + data/style_extract）。
"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.58(提取预设详细度与迭代稳定).zip"

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