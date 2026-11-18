# -*- coding: utf-8 -*-
"""打包星火笔 v0.79（UI卡死根因修复·线程重构）（便携 env + 源码 + 脚本；排除用户数据/测试输出）。"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v0.79（UI卡死根因修复·线程重构）.zip"

EXCLUDE_DIRS = {".git", "data", "projects", "__pycache__"}
EXCLUDE_FILES = {"e2e.log", "_smoke_out.txt", "_smoke_out2.txt", "_smoke_out3.txt",
                 "_smoke_out4.txt", "_smoke_out5.txt", "_smoke_out6.txt",
                 "_smoke_out7.txt", "_smoke_out8.txt", "_smoke_out9.txt",
                 "_smoke_out10.txt", "_smoke_out70.txt", "_smoke_out71.txt",
                 "_smoke_out72.txt", "_smoke_out73.txt", "_smoke_out74.txt",
                 "_smoke_out74b.txt", "_smoke_out74c.txt", "_smoke_out75.txt",
                 "_smoke_out76.txt", "_smoke_out77.txt", "_smoke_out78.txt",
                 "_smoke_out79.txt",
                 "_pack_v70_out.txt", "_pack_v70_out2.txt",
                 "_pack_v71_out.txt", "_pack_v72_out.txt", "_pack_v73_out.txt",
                 "_pack_v74_out.txt", "_pack_v75_out.txt", "_pack_v76_out.txt",
                 "_pack_v77_out.txt", "_pack_v78_out.txt", "_pack_v79_out.txt",
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
