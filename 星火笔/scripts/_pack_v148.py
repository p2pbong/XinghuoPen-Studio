# -*- coding: utf-8 -*-
"""打包星火笔 v1.48（拆书章节解析多格式放宽——整本书只识别一章的修复 +
文风校对 D 节点可选参考 Top3 提示词与分数、在最高分基础上改进）。
（便携 env + 源码 + 脚本 + data/config.json + data/breaks + data/style_extract）。

v0.96 起按用户要求不再剔除 API 配置与 Key（data/config.json 随 zip）。
v1.43 起拆书文档（data/breaks/*.json）、文风校对预设（data/style_extract/*.json）
也随包（用户：打包拆书文档、情景卡还有文风校对的预设都不要清理，我都要用）。
其余 data/（话题/会话/工作区）仍不打包。
"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.48（拆书多格式识别+文风D参考Top3）.zip"

EXCLUDE_DIRS = {".git", "data", "projects", "__pycache__"}
EXCLUDE_FILES = {"e2e.log", "release.keystore", "keystore.properties"}
# v1.43 随包保留的数据子目录（拆书文档 + 文风预设 + 情景卡总库在 config.json）
KEEP_DATA_SUBDIRS = ("breaks", "style_extract")

files = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    base = os.path.basename(dirpath)
    if base == "data":
        # data 目录：只保留 KEEP_DATA_SUBDIRS 子目录（config.json 最后单独追加）
        dirnames[:] = [d for d in dirnames if d in KEEP_DATA_SUBDIRS]
    else:
        # 根层剪枝时要放行 data，由上面分支深入后再裁子目录
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

# API 配置（含 Key）随包：用户要求不再每次重新输入
cfg = os.path.join(ROOT, "data", "config.json")
if os.path.isfile(cfg):
    files.append((cfg, "data/config.json"))
else:
    print("WARN data/config.json 不存在，本次不打包")

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for full, rel in sorted(files):
        z.write(full, "星火笔/" + rel)
print("ZIP_OK", len(files), "files ->", OUT)