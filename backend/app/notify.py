"""外部推送提醒（P2，借鉴 DeepTutor IM 通道的单向最小版）：
到期复习点/闪卡/逾期任务汇总 → 微信（Server酱）或企业微信群机器人。

- 配置存 meta 表（notify_config），运行时经 /api/notify 配置，密钥不回传明文；
- 节流：每天最多推 1 次（当天首次发现「有到期内容」时推），且不早于 push_hour；
  纯本机的应用内横幅与系统通知不受影响，这是给"人不在电脑前"的补充通道；
- 消息组装（build_digest/format_text）与渠道 payload 为纯函数，离线可测；
  网络发送失败记录 last_error，不打断主服务。
"""
import json
import logging
import threading
import time

import httpx

from . import db

log = logging.getLogger("studypilot.notify")

_META_KEY = "notify_config"
_LAST_PUSH_KEY = "notify_last_push_date"
_ERR_KEY = "notify_last_error"

_TIMEOUT = 10.0
_UA = "StudyPilot/0.1 (local study assistant)"

_CHANNELS = ("serverchan", "wecom_webhook")


def _defaults() -> dict:
    return {"enabled": False, "channel": "serverchan",
            "serverchan_sendkey": "", "wecom_webhook": "", "push_hour": 8}


def get_cfg() -> dict:
    raw = db.get_meta(_META_KEY)
    cfg = _defaults()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                cfg.update({k: data[k] for k in cfg if k in data})
        except ValueError:
            log.warning("notify_config 损坏，已回退默认配置")
    # 钳制：push_hour 0-23，channel 必须在白名单内
    cfg["push_hour"] = max(0, min(23, int(cfg["push_hour"] or 0)))
    if cfg["channel"] not in _CHANNELS:
        cfg["channel"] = "serverchan"
    return cfg


def save_cfg(patch: dict) -> dict:
    cfg = get_cfg()
    cfg.update({k: patch[k] for k in cfg if k in patch})
    db.set_meta(_META_KEY, json.dumps(cfg, ensure_ascii=False))
    return get_cfg()  # 走读取侧归一化（push_hour 钳制 / 渠道白名单），保证落库即合法


def masked_cfg() -> dict:
    """给前端的配置：密钥只回掩码，避免明文在页面上回显。"""
    cfg = get_cfg()
    cfg["serverchan_sendkey"] = _mask(cfg["serverchan_sendkey"])
    cfg["wecom_webhook"] = _mask(cfg["wecom_webhook"])  # 保留 host 便于辨认，只遮 key 参数
    return cfg


def _mask(s: str) -> str:
    if not s:
        return ""
    if "?" in s:  # webhook：host 保留，查询串（含 key）整体遮蔽
        head, _, query = s.partition("?")
        return head + "?" + ("****" if query else "")
    return s[:4] + "****" if len(s) > 8 else "****"


# ---------- 今日摘要（跨空间聚合） ----------

def build_digest() -> dict | None:
    """跨空间汇总到期内容；毫无到期内容时返回 None（不推空消息打扰）。"""
    spaces = db.list_spaces()
    items = []
    for sp in spaces:
        snap = db.today_snapshot(sp["id"])
        n_due, n_flash, n_tasks = snap["due_total"], snap["flash_due"], len(snap["tasks_today"])
        if not (n_due or n_flash or n_tasks):
            continue
        items.append({
            "space": sp["name"],
            "due": n_due,
            "flash": n_flash,
            "tasks": n_tasks,
            "top_points": [p["point"] for p in snap["due_points"][:3]],
        })
    if not items:
        return None
    return {"date": time.strftime("%Y-%m-%d"), "items": items}


def format_text(digest: dict) -> tuple[str, str]:
    """digest → (标题, 正文)。纯函数。"""
    total_due = sum(i["due"] for i in digest["items"])
    total_flash = sum(i["flash"] for i in digest["items"])
    total_tasks = sum(i["tasks"] for i in digest["items"])
    title = f"StudyPilot 今日待学：{total_due} 个知识点 / {total_flash} 张闪卡"
    lines = []
    for i in digest["items"]:
        seg = f"《{i['space']}》：到期知识点 {i['due']}、闪卡 {i['flash']}、逾期任务 {i['tasks']}"
        if i["top_points"]:
            seg += "\n最急：" + "、".join(i["top_points"])
        lines.append(seg)
    text = "\n\n".join(lines) + f"\n\n逾期任务合计 {total_tasks} 个。打开 StudyPilot 开始今日学习吧。"
    return title, text


# ---------- 渠道发送 ----------

def _send_serverchan(sendkey: str, title: str, text: str) -> None:
    if not sendkey:
        raise ValueError("Server酱 SendKey 未配置")
    r = httpx.post(f"https://sctapi.ftqq.com/{sendkey}.send",
                   data={"title": title, "desp": text},
                   headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    r.raise_for_status()
    if r.json().get("code") != 0:
        raise ValueError(f"Server酱返回错误：{str(r.json())[:120]}")


def _send_wecom(webhook: str, title: str, text: str) -> None:
    if not webhook or "qyapi.weixin.qq.com" not in webhook:
        raise ValueError("企业微信机器人 webhook 未配置或不合法")
    # text 类型上限 2048 字节，超长截断保底
    content = f"{title}\n{text}"[:1000]
    r = httpx.post(webhook, json={"msgtype": "text", "text": {"content": content}},
                   headers={"User-Agent": _UA}, timeout=_TIMEOUT)
    r.raise_for_status()
    if r.json().get("errcode") != 0:
        raise ValueError(f"企业微信返回错误：{str(r.json())[:120]}")


def send(cfg: dict, title: str, text: str) -> None:
    if cfg["channel"] == "wecom_webhook":
        _send_wecom(cfg["wecom_webhook"], title, text)
    else:
        _send_serverchan(cfg["serverchan_sendkey"], title, text)


def test_push() -> dict:
    """配置页「测试推送」：发一条测试消息，回传成功/失败原因。"""
    cfg = get_cfg()
    try:
        send(cfg, "StudyPilot 推送测试", "这是一条测试消息。收到说明推送通道已就绪。")
        db.set_meta(_ERR_KEY, "")
        return {"ok": True}
    except Exception as e:
        msg = str(e)[:200]
        db.set_meta(_ERR_KEY, time.strftime("%Y-%m-%d %H:%M ") + msg)
        return {"ok": False, "error": msg}


# ---------- 每日一次的定时推送 ----------

def push_if_due(force: bool = False) -> dict:
    """有到期内容且今天还没推过 → 推送。返回 {pushed, reason} 供端点与调试。"""
    cfg = get_cfg()
    if not cfg["enabled"]:
        return {"pushed": False, "reason": "disabled"}
    today = time.strftime("%Y-%m-%d")
    if db.get_meta(_LAST_PUSH_KEY) == today and not force:
        return {"pushed": False, "reason": "already_pushed"}
    if not force and time.localtime().tm_hour < cfg["push_hour"]:
        return {"pushed": False, "reason": "before_push_hour"}
    digest = build_digest()
    if not digest:
        return {"pushed": False, "reason": "nothing_due"}
    title, text = format_text(digest)
    try:
        send(cfg, title, text)
    except Exception as e:
        msg = str(e)[:200]
        db.set_meta(_ERR_KEY, time.strftime("%Y-%m-%d %H:%M ") + msg)
        log.warning("推送失败：%s", msg)
        return {"pushed": False, "reason": f"send_failed: {msg}"}
    db.set_meta(_LAST_PUSH_KEY, today)
    db.set_meta(_ERR_KEY, "")
    return {"pushed": True, "reason": "ok", "spaces": len(digest["items"])}


_loop_started = False


def start_background_loop() -> None:
    """守护线程：每 5 分钟检查一次（推不推由 push_if_due 的日级节流决定）。幂等。"""
    global _loop_started
    if _loop_started:
        return
    _loop_started = True

    def _run():
        time.sleep(90)  # 等服务与数据库就绪，错开启动期其他初始化
        while True:
            try:
                push_if_due()
            except Exception:
                pass  # 后台推送失败不影响主服务，下一轮再试
            time.sleep(300)

    threading.Thread(target=_run, name="notify-push", daemon=True).start()
