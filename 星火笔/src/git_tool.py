# -*- coding: utf-8 -*-
"""git 存档工具：仅本地仓库，绝不推送云端。"""
import os
import shutil
import subprocess
import threading

_last_msg = None
_commit_lock = threading.Lock()   # 串行化 git add/commit：编辑/生成/删除可能并发触发归档


def _no_window():
    """v1.80 修「每章闪一下命令行」：Windows 下子进程（git.exe）默认会新开一个控制台
    窗口一闪而过——加 CREATE_NO_WINDOW 让 git 完全静默在后台跑（非 Windows 无此概念）。"""
    if os.name == "nt":
        return subprocess.CREATE_NO_WINDOW
    return 0


def available():
    return shutil.which("git") is not None


def ensure_repo(root):
    if not available():
        return False
    if not os.path.isdir(os.path.join(root, ".git")):
        try:
            subprocess.run(["git", "init", "-q"], cwd=root, timeout=30,
                           capture_output=True, creationflags=_no_window())
        except Exception:
            return False
    return True


def commit(root, message, log_fn=None):
    global _last_msg
    if not available():
        return
    # v0.98 修复「git commit 警告：fatal: not a git repository」：便携包/新目录无 .git 时
    # 自动 git init（本地存档仓库，绝不推送云端），不再每次报错
    if not ensure_repo(root):
        if log_fn:
            log_fn("warn", "git 不可用或初始化失败，跳过本地存档。")
        return
    with _commit_lock:
        try:
            subprocess.run(["git", "add", "-A", "."], cwd=root, timeout=60,
                           capture_output=True, creationflags=_no_window())
            r = subprocess.run(["git", "commit", "-q", "-m", message], cwd=root,
                               timeout=60, capture_output=True,
                               creationflags=_no_window())
            if r.returncode != 0 and r.stderr:
                err = r.stderr.decode("utf-8", "ignore")
                if "nothing to commit" not in err and r.returncode != 1:
                    if log_fn:
                        log_fn("warn", "git commit 警告：%s" % err.strip()[:200])
            _last_msg = message
        except Exception as e:
            if log_fn:
                log_fn("warn", "git 提交失败：%s" % e)


def last_message():
    return _last_msg