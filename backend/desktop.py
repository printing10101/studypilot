"""StudyPilot 桌面端入口。

在一个进程内：后台线程跑 FastAPI（:8178），主线程用 pywebview
（Windows 上走 Edge WebView2）打开原生桌面窗口。
- 若 8178 已有 StudyPilot 服务在运行，则直接开窗口连接，不重复起服务。
- 支持普通 python 与 pythonw（无控制台，快捷方式使用）两种方式启动。
"""
import os
import threading
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))  # 保证 data/uploads 相对路径正确

HOST, PORT = "127.0.0.1", 8178


def server_alive() -> bool:
    import httpx
    try:
        r = httpx.get(f"http://{HOST}:{PORT}/api/health", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def run_server() -> None:
    import uvicorn
    from app.main import app
    # pythonw 下无 stdout，把日志写入文件避免报错
    log_cfg = uvicorn.config.LOGGING_CONFIG
    log_cfg["handlers"]["access"]["stream"] = "ext://sys.stdout"
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", log_config=log_cfg)


def wait_server(timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server_alive():
            return
        time.sleep(0.4)


if __name__ == "__main__":
    import webview

    if not server_alive():
        threading.Thread(target=run_server, daemon=True).start()
        wait_server()

    webview.create_window(
        "StudyPilot · 本地 AI 助教",
        f"http://{HOST}:{PORT}/",
        width=1400,
        height=880,
        min_size=(1080, 700),
        background_color="#070b14",
    )
    webview.start(gui="edgechromium")
