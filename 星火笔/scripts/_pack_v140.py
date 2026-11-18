# -*- coding: utf-8 -*-
"""打包星火笔 v1.40（一章多情景多卡组合：consolidate 明确一章几个特殊情景就选几张、
全选不漏、分工组合而非单选；engine _collect_scene_cards 注入卡保留 category（content
首行【分类】回退提取）；write_chapter 多卡分工注入——每张卡带〔分类〕标注 + 组合规则
（每段只受所属片段对应卡约束、不得把多张卡规则叠加在同一段、互不冲突））（便携 env +
源码 + 脚本 + data/config.json）。

v0.96 起按用户要求不再剔除 API 配置与 Key（data/config.json 随 zip，解压免重输 Key）。
其余 data/（话题/会话/工作区）仍不打包。
"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.40（情景卡多卡组合）.zip"

EXCLUDE_DIRS = {".git", "data", "projects", "__pycache__"}
EXCLUDE_FILES = {"e2e.log", "release.keystore", "keystore.properties"}

files = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
    for fn in filenames:
        if fn in EXCLUDE_FILES:
            continue
        full = os.path.join(dirpath, fn)
        files.append((full, os.path.relpath(full, ROOT)))

# API 配置（含 Key）随包：用户要求不再每次重新输入
cfg = os.path.join(ROOT, "data", "config.json")
if os.path.isfile(cfg):
    files.append((cfg, "data/config.json"))
else:
    print("WARN data/config.json 不存在，本次不打包（新装用户首次运行会自动生成）")

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for full, rel in sorted(files):
        z.write(full, "星火笔/" + rel)
print("ZIP_OK", len(files), "files ->", OUT)