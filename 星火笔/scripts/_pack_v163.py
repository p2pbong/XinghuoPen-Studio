# -*- coding: utf-8 -*-
"""打包星火笔 v1.63（文风校对报错续跑 + 换API即时生效：用户反馈「文风校对报错 X 请求异常：
Response ended prematurely 后只能重新开始，之前跑的成果白跑；暂停后换 API 继续是否用新 API？」。
根因=①引擎 run_workflow_stream 无续跑机制，任一节点 LLM 报错（流式读取被网关掐断、
llm 重试耗尽抛 LLMError）整体终止，已跑轮次结果全丢；②profiles 在流程开始时只读一次快照，
暂停/继续不会重读，换 API 不生效。
修复=①引擎 _chat_node 包装节点调用：失败 yield("error") 挂起等 UI 点「继续」（retry_evt）
重试同一节点，已跑轮次与 Top3 全部保留，停止在挂起中也立即生效（StopRequested 优先传播）；
②每次节点调用前现读 style_settings()["profiles"]（暂停/报错后换 API 继续立即生效）；
③GUI error 分支显示错误+启用「继续」按钮，_resume 同时唤醒 retry。
verify_v163.py ALL_OK 21 项全过。含 data/config.json + data/breaks + data/style_extract。）
"""
import os
import zipfile

ROOT = r"F:\download\work file\novel\星火笔"
OUT = r"F:\download\work file\novel\历史版本-电脑端\星火笔-v1.63(文风校对报错续跑与换API即时生效).zip"

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