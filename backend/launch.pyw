"""pythonw 静默启动入口（无控制台窗口）。

桌面快捷方式指向本文件：把 stdout/stderr 重定向到日志文件后执行 desktop.py。
"""
import os
import sys

base = os.path.dirname(os.path.abspath(__file__))
os.chdir(base)

log_path = os.path.join(base, "desktop.log")
log = open(log_path, "a", buffering=1, encoding="utf-8")
sys.stdout = log
sys.stderr = log

import runpy  # noqa: E402

runpy.run_path(os.path.join(base, "desktop.py"), run_name="__main__")
