# -*- coding: utf-8 -*-
"""全量语法编译检查。"""
import glob
import os
import py_compile
import sys

root = os.path.dirname(os.path.abspath(__file__))
files = (glob.glob(os.path.join(root, "src", "*.py"))
         + [os.path.join(root, "_smoke.py"), os.path.join(root, "_e2e.py"),
            os.path.join(root, "_diag.py")])
bad = []
for f in files:
    try:
        py_compile.compile(f, doraise=True)
    except py_compile.PyCompileError as e:
        bad.append(str(e))
if bad:
    print("FAIL:")
    for b in bad:
        print(b)
    sys.exit(1)
print("ALL_SYNTAX_OK (%d files)" % len(files))
