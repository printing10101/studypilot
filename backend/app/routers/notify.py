"""外部推送提醒：配置（密钥掩码回显）/ 测试推送 / 手动立即推送。"""
from fastapi import APIRouter
from pydantic import BaseModel

from .. import db, notify

router = APIRouter()


class NotifyCfgIn(BaseModel):
    enabled: bool | None = None
    channel: str | None = None
    serverchan_sendkey: str | None = None
    wecom_webhook: str | None = None
    push_hour: int | None = None


@router.get("/api/notify")
def api_notify_status():
    return {
        "config": notify.masked_cfg(),
        "last_push_date": db.get_meta("notify_last_push_date"),
        "last_error": db.get_meta("notify_last_error"),
    }


@router.put("/api/notify")
def api_notify_save(body: NotifyCfgIn):
    # 掩码值回传时不覆盖真实密钥（前端原样带回 "****" 或保留 host 的 webhook）
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    for k in ("serverchan_sendkey", "wecom_webhook"):
        if patch.get(k) and "****" in patch[k]:
            patch.pop(k)
    notify.save_cfg(patch)
    return {"config": notify.masked_cfg()}


@router.post("/api/notify/test")
def api_notify_test():
    return notify.test_push()


@router.post("/api/notify/push")
def api_notify_push():
    """手动立即推送（绕过当日节流与小时门，便于验证）。"""
    return notify.push_if_due(force=True)
