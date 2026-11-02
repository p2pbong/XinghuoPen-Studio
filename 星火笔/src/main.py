# -*- coding: utf-8 -*-
"""入口：启动 PySide6 桌面应用（v1.76 起由 start.bat 以 pythonw 无窗口启动）。

pythonw 模式下没有任何控制台输出——启动早期异常（环境不完整/缺依赖等）会静默失败，
这里统一兜底：把堆栈写入 data/launcher_error.log 并弹窗提示，避免"双击没反应"。
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import storage  # noqa: E402


def _fatal_box(message):
    """未捕获异常：写日志 + 弹窗（无控制台环境下错误仍可见）。"""
    try:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "data")
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "launcher_error.log"), "w",
                  encoding="utf-8") as f:
            f.write(message)
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, message, "星火笔 · 启动失败", 0x10)
    except Exception:
        pass


def main():
    try:
        storage.ensure_example_project()
        from gui_app import run
        run()
    except Exception:
        message = ("启动失败，错误详情已写入软件目录 data/launcher_error.log。\n\n%s"
                   % traceback.format_exc())
        _fatal_box(message)
        sys.exit(1)


if __name__ == "__main__":
    main()