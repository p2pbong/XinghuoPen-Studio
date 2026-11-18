# -*- coding: utf-8 -*-
"""打包星火笔 v0.64（文风校对移植·UI优化）（便携 env + 源码 + 脚本；排除用户数据）。"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v0.64（文风校对移植·UI优化）.zip"

EXCLUDE_DIRS = {".git", "data", "projects", "__pycache__"}
EXCLUDE_FILES = {"e2e.log", "_smoke_out.txt", "_smoke_out2.txt", "_smoke_out3.txt",
                 "_smoke_out4.txt", "release.keystore", "keystore.properties"}

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
