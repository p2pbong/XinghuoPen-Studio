# -*- coding: utf-8 -*-
"""打包星火笔 v0.91（对话Agent拆分）（便携 env + 源码 + 脚本）。"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v0.91（对话Agent拆分）.zip"

EXCLUDE_DIRS = {".git", "data", "projects", "__pycache__"}
EXCLUDE_FILES = {"e2e.log", "_smoke_out.txt", "_smoke_out2.txt", "_smoke_out3.txt",
                 "_smoke_out4.txt", "_smoke_out5.txt", "_smoke_out6.txt",
                 "_smoke_out7.txt", "_smoke_out8.txt", "_smoke_out9.txt",
                 "_smoke_out10.txt", "_smoke_out70.txt", "_smoke_out71.txt",
                 "_smoke_out72.txt", "_smoke_out73.txt", "_smoke_out74.txt",
                 "_smoke_out74b.txt", "_smoke_out74c.txt", "_smoke_out75.txt",
                 "_smoke_out76.txt", "_smoke_out77.txt", "_smoke_out78.txt",
                 "_smoke_out79.txt", "_smoke_out80.txt", "_smoke_out81.txt",
                 "_smoke_out82.txt", "_smoke_out83.txt", "_smoke_out84.txt",
                 "_smoke_out85.txt", "_smoke_out86.txt", "_smoke_out87.txt",
                 "_smoke_out88.txt", "_smoke_out89.txt", "_smoke_out90.txt",
                 "_smoke_out91.txt",
                 "_pack_v70_out.txt", "_pack_v70_out2.txt",
                 "_pack_v71_out.txt", "_pack_v72_out.txt", "_pack_v73_out.txt",
                 "_pack_v74_out.txt", "_pack_v75_out.txt", "_pack_v76_out.txt",
                 "_pack_v77_out.txt", "_pack_v78_out.txt", "_pack_v79_out.txt",
                 "_pack_v80_out.txt", "_pack_v81_out.txt", "_pack_v82_out.txt",
                 "_pack_v83_out.txt", "_pack_v84_out.txt", "_pack_v85_out.txt",
                 "_pack_v86_out.txt", "_pack_v87_out.txt", "_pack_v88_out.txt",
                 "_pack_v89_out.txt", "_pack_v90_out.txt", "_pack_v91_out.txt",
                 "_settings_check_out2.txt",
                 "release.keystore", "keystore.properties"}

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
