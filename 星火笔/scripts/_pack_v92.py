# -*- coding: utf-8 -*-
"""打包星火笔 v0.92（主目录清理）（便携 env + 源码 + 脚本）。

v0.92 主目录已清理：历史打包/检查脚本归档到 scripts\、测试输出 txt 已删，
本脚本按新约定输出到调用方指定的重定向文件（.qwen\tmp），不再产生主目录输出文件。
"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v0.92（主目录清理）.zip"

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

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for full, rel in sorted(files):
        z.write(full, "星火笔/" + rel)
print("ZIP_OK", len(files), "files ->", OUT)
