"""FastAPI 入口：app 装配（中间件 / 启动钩子 / 路由注册 / 静态托管）。

路由实现按领域拆在 app/routers/ 下：profile、audit、campus、library、spaces、
chat、skills、study、insights、career、admin；共享工具在 routers/common.py。
"""
import logging
import pathlib

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import connectors, db, library, note_review
from .routers import admin, audit, campus, career, chat, insights, profile, skills, spaces, study
from .routers import library as library_routes

app = FastAPI(title="StudyPilot", version="0.1.0")

# 本机服务防 drive-by：浏览器发起的跨站请求必带 Origin 头，白名单之外一律 403
# （桌面端同源页面、curl 脚本不带 Origin，不受影响）。前端与后端同源部署
# （桌面端 FastAPI 托管 / 开发模式 vite proxy），无需 CORS 放行。
ALLOWED_ORIGINS = {
    "http://127.0.0.1:8178", "http://localhost:8178",
    "http://127.0.0.1:5173", "http://localhost:5173",  # 开发模式 vite
}


@app.middleware("http")
async def _origin_guard(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return PlainTextResponse("Forbidden origin", status_code=403)
    return await call_next(request)


# ---------- 启动钩子（保持原有注册顺序） ----------

@app.on_event("startup")
def _seed_library():
    connectors.load_persisted()  # 恢复上次注册的 MCP server
    try:
        library.seed()
    except Exception:
        logging.getLogger("studypilot").warning(
            "书目预置失败（不阻塞服务启动，可在前端重试）", exc_info=True)


@app.on_event("startup")
def _start_campus_sync():
    from . import campus_net
    campus_net.start_background_loop()


@app.on_event("startup")
def _startup_migrations():
    note_review.ensure_doc_fsrs_columns()
    n = db.reset_stale_pending()
    if n:
        logging.getLogger("studypilot").warning(
            "启动清扫：将 %d 个遗留「处理中」文档置为失败（进程上次被中断），可在资料中心重新索引", n)
    db.backup_database()  # 每次启动滚动备份整库，保留最近 7 份


# ---------- 路由注册 ----------

for _r in (profile, audit, campus, library_routes, spaces, chat, skills, study, insights, career, admin):
    app.include_router(_r.router)

# ---------- 桌面模式：托管前端构建产物（SPA） ----------

FRONTEND_DIST = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="spa")
