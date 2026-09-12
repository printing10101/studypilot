"""StudyPilot 桌面端入口。

在一个进程内：后台线程跑 FastAPI（:8178），主线程用 pywebview
（Windows 上走 Edge WebView2）打开原生桌面窗口。
- 若 8178 已有 StudyPilot 服务在运行，则直接开窗口连接，不重复起服务。
- 支持普通 python 与 pythonw（无控制台，快捷方式使用）两种方式启动。
"""
import os
import socket
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


def port_occupied() -> bool:
    """端口上有监听者（无论是不是 StudyPilot）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def _fatal_box(msg: str) -> None:
    """无控制台（pythonw）场景下 print 没人看得见，故障必须弹原生对话框。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "StudyPilot 启动失败", 0x10)
    except Exception:
        print(msg)


def run_server() -> None:
    import uvicorn
    from app.main import app
    # pythonw 下无 stdout，把日志写入文件避免报错
    log_cfg = uvicorn.config.LOGGING_CONFIG
    log_cfg["handlers"]["access"]["stream"] = "ext://sys.stdout"
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", log_config=log_cfg)


def wait_server(timeout: float = 90.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server_alive():
            return True
        time.sleep(0.4)
    return False


if __name__ == "__main__":
    import webview

    if not server_alive():
        if port_occupied():
            _fatal_box(
                f"端口 {PORT} 已被其他程序占用，StudyPilot 服务无法启动。\n\n"
                f"请结束占用该端口的程序后重试，或修改 backend/desktop.py 中的 PORT。")
            raise SystemExit(1)
        threading.Thread(target=run_server, daemon=True).start()
        if not wait_server():
            # 等 90 秒仍不健康：不要对着别人的服务或空白窗口打开页面
            _fatal_box(
                "后端服务启动超时。常见原因：\n"
                f"1) 端口 {PORT} 被占用；\n"
                "2) 依赖未安装（请先在 backend 目录执行 uv sync）；\n"
                "3) 杀毒软件拦截了 python。详情见 backend/desktop.log。")
            raise SystemExit(1)

    # 前端构建产物缺失（新克隆仓库未执行 pnpm build）时页面只有一行 404，
    # 用户没有任何线索；提前检测并给出可执行的指引
    dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "frontend", "dist", "index.html")
    if not os.path.exists(dist):
        _fatal_box(
            "未找到前端构建产物 frontend/dist/index.html。\n\n"
            "请先构建前端再打开桌面端：\n"
            "  cd frontend\n"
            "  pnpm install && pnpm build")
        raise SystemExit(1)

    try:
        webview.create_window(
            "StudyPilot · 本地 AI 助教",
            f"http://{HOST}:{PORT}/",
            width=1400,
            height=880,
            min_size=(900, 640),
            background_color="#0f1322",
        )
        webview.start(gui="edgechromium")
    except Exception as e:
        # 未装 WebView2 Runtime 的 Win10 机器上 webview.start 直接抛异常：
        # pythonw 模式下只写进日志，用户视角是「双击后毫无反应」
        if "webview2" in str(e).lower() or "runtime" in str(e).lower():
            _fatal_box(
                "未检测到 Microsoft Edge WebView2 Runtime。\n\n"
                "请到 https://developer.microsoft.com/microsoft-edge/webview2/ "
                "下载安装「Evergreen Standalone Installer」后重试。")
        else:
            _fatal_box(f"窗口启动失败：{e}\n\n详情见 backend/desktop.log。")
        raise
