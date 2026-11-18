# -*- coding: utf-8 -*-
"""打包星火笔 v1.36（情景卡拆书边拆边显示：引擎 extract_scene_cards_from_novel 新增
on_card 回调逐张实时送卡 + GUI worker card_ready 信号实时入列——长小说分片拆出
一张列一张，随时可停止，已拆出的卡保留在结果列表可直接勾选保存）
（便携 env + 源码 + 脚本 + data/config.json）。

v0.96 起按用户要求不再剔除 API 配置与 Key（data/config.json 随 zip，解压免重输 Key）。
其余 data/（话题/会话/工作区）仍不打包。
"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.36（拆书边拆边显示）.zip"

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
