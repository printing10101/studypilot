"""校园网感知 · 校园信息自动同步。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import campus_net

router = APIRouter()


class CampusConfigIn(BaseModel):
    auto_sync: bool | None = None
    interval_min: int | None = None
    campus_hosts: list[str] | None = None
    internal_hosts: list[str] | None = None
    public_cidrs: list[str] | None = None
    sources: list[dict] | None = None


@router.get("/api/campus/status")
def api_campus_status(force: int = 0):
    """网络状态（校园网/公网/离线）+ 上次同步 + 信息源配置；force=1 跳过检测缓存。"""
    if force:
        campus_net.detect(force=True)
    return campus_net.status()


@router.post("/api/campus/sync")
def api_campus_sync():
    """立即同步全部信息源（离线时返回 skipped）。"""
    return campus_net.sync()


@router.get("/api/campus/items")
def api_campus_items(source: str = "", limit: int = 60, q: str = ""):
    """已抓取的校园信息条目（按发布日期倒序；q 按标题模糊过滤，如 q=四六级）。"""
    return {"items": campus_net.list_items(source, limit, q=q)}


@router.put("/api/campus/config")
def api_campus_config(body: CampusConfigIn):
    try:
        campus_net.save_cfg(body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return campus_net.status()
