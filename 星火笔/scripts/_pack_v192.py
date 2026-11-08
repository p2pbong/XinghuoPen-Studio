# -*- coding: utf-8 -*-
"""打包星火笔 v1.92（正文AI「前文脉络」增强：伏笔台账新增 planted_note 埋设要点（综合校验
   埋设时记录「借什么物件/场景/动作/台词怎么露出来的」、开放伏笔清单带埋设细节）+ 正文AI
   新注入前文伏笔台账与关键角色立场/动机/行事风格块 + 主AI压缩笔记记录维度升级（人物立场
   动机、伏笔怎么埋的）——正文AI不再只凭几句裁定干写）。含 data 用户数据。"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.92(正文AI前文脉络增强).zip"

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