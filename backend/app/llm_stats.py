"""LLM 调用统计：延迟、Token、通道健康度。

借鉴 OpenLIT 的 per-call trace 思路：每次 chat/chat_json/chat_stream 调用
记录 {ts, task, channel, model, latency_ms, tokens_in, tokens_out, ok, error}，
存 SQLite 供模型设置页展示延迟分布、成功率，以及 auto 路由的通道选择依据。
"""
import json
import threading
import time
from collections import defaultdict

from . import db

_lock = threading.Lock()
# 内存滑动窗口（最近 200 条），避免频繁查库
_recent: list[dict] = []
_MAX_RECENT = 200


def _ensure_table() -> None:
    c = db.get_conn()
    c.execute("""CREATE TABLE IF NOT EXISTS llm_calls(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL NOT NULL,
        task TEXT DEFAULT '',
        channel TEXT DEFAULT '',
        model TEXT DEFAULT '',
        latency_ms INTEGER DEFAULT 0,
        tokens_in INTEGER DEFAULT 0,
        tokens_out INTEGER DEFAULT 0,
        ok INTEGER DEFAULT 1,
        error TEXT DEFAULT ''
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_llm_ts ON llm_calls(ts)")
    c.commit()


_ensure_table()


def record(task: str, channel: str, model: str, latency_ms: int,
           tokens_in: int = 0, tokens_out: int = 0,
           ok: bool = True, error: str = "") -> None:
    """记录一次 LLM 调用。"""
    entry = {
        "ts": time.time(), "task": task, "channel": channel, "model": model,
        "latency_ms": latency_ms, "tokens_in": tokens_in, "tokens_out": tokens_out,
        "ok": ok, "error": error[:200],
    }
    with _lock:
        _recent.append(entry)
        if len(_recent) > _MAX_RECENT:
            _recent.pop(0)
    try:
        c = db.get_conn()
        c.execute(
            "INSERT INTO llm_calls(ts,task,channel,model,latency_ms,tokens_in,tokens_out,ok,error) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (entry["ts"], task, channel, model, latency_ms, tokens_in, tokens_out,
             1 if ok else 0, entry["error"]))
        c.commit()
    except Exception:
        pass  # 统计失败不影响主流程


def estimate_tokens(text: str) -> int:
    """粗略估算 token 数：中文约 1.5 字/token，英文约 4 字符/token。"""
    if not text:
        return 0
    cn = sum(1 for ch in text if '一' <= ch <= '鿿')
    other = len(text) - cn
    return int(cn / 1.5 + other / 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """估算消息列表的输入 token 数。"""
    total = 0
    for m in messages:
        total += estimate_tokens(m.get("content", "")) + 4  # role 开销
    return total


def summary(hours: int = 24) -> dict:
    """最近 N 小时的调用统计汇总。"""
    cutoff = time.time() - hours * 3600
    try:
        rows = db.get_conn().execute(
            "SELECT task, channel, model, latency_ms, tokens_in, tokens_out, ok "
            "FROM llm_calls WHERE ts > ? ORDER BY id DESC LIMIT 500",
            (cutoff,)).fetchall()
    except Exception:
        return {"total": 0, "by_channel": {}, "by_task": {}}

    by_channel: dict[str, dict] = defaultdict(lambda: {"count": 0, "ok": 0, "latencies": [], "tokens_out": 0})
    by_task: dict[str, dict] = defaultdict(lambda: {"count": 0, "ok": 0, "latencies": []})
    total = 0
    for r in rows:
        total += 1
        ch = r["channel"] or "unknown"
        tk = r["task"] or "unknown"
        by_channel[ch]["count"] += 1
        by_channel[ch]["ok"] += r["ok"]
        by_channel[ch]["latencies"].append(r["latency_ms"])
        by_channel[ch]["tokens_out"] += r["tokens_out"]
        by_task[tk]["count"] += 1
        by_task[tk]["ok"] += r["ok"]
        by_task[tk]["latencies"].append(r["latency_ms"])

    def _agg(d: dict) -> dict:
        out = {}
        for k, v in d.items():
            lats = sorted(v["latencies"])
            out[k] = {
                "count": v["count"],
                "success_rate": round(v["ok"] / max(v["count"], 1), 3),
                "avg_latency_ms": int(sum(lats) / max(len(lats), 1)),
                "p50_latency_ms": lats[len(lats) // 2] if lats else 0,
                "p95_latency_ms": lats[int(len(lats) * 0.95)] if lats else 0,
            }
            if "tokens_out" in v:
                out[k]["total_tokens_out"] = v["tokens_out"]
        return out

    return {
        "total": total,
        "window_hours": hours,
        "by_channel": _agg(by_channel),
        "by_task": _agg(by_task),
    }


def channel_health() -> dict:
    """各通道最近健康状态：用于 auto 路由决策。"""
    with _lock:
        recent = list(_recent[-50:])
    health: dict[str, dict] = {}
    for ch in ("local", "cloud"):
        calls = [r for r in recent if r["channel"] == ch]
        if not calls:
            health[ch] = {"available": None, "avg_latency_ms": 0, "success_rate": 0.0}
            continue
        ok = sum(1 for r in calls if r["ok"])
        lats = [r["latency_ms"] for r in calls if r["ok"]]
        health[ch] = {
            "available": ok > 0,
            "avg_latency_ms": int(sum(lats) / max(len(lats), 1)),
            "success_rate": round(ok / len(calls), 3),
            "recent_calls": len(calls),
        }
    return health


def clear_history() -> None:
    """清空历史统计。"""
    with _lock:
        _recent.clear()
    try:
        db.get_conn().execute("DELETE FROM llm_calls").commit()
    except Exception:
        pass


def usage_dashboard(days: int = 30) -> dict:
    """用量仪表盘：按天/通道/任务/模型聚合 Token 与调用次数。

    返回结构类似质谱 Zcode 用量页：
    - totals: 累计总量（输入/输出/总 Token、总调用、成功率）
    - by_channel: 本地/云端各自总量
    - daily: 按天序列（供柱状图）
    - by_task: 按任务类型
    - by_model: 按模型名
    - recent: 最近 20 条调用明细
    """
    import datetime
    cutoff = time.time() - days * 86400
    try:
        rows = db.get_conn().execute(
            "SELECT ts, task, channel, model, latency_ms, tokens_in, tokens_out, ok "
            "FROM llm_calls WHERE ts > ? ORDER BY ts ASC",
            (cutoff,)).fetchall()
    except Exception:
        return _empty_dashboard(days)

    if not rows:
        return _empty_dashboard(days)

    # 累计
    total_in = sum(r["tokens_in"] for r in rows)
    total_out = sum(r["tokens_out"] for r in rows)
    total_calls = len(rows)
    total_ok = sum(r["ok"] for r in rows)

    # 按通道
    ch_data: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "ok": 0, "tokens_in": 0, "tokens_out": 0, "latencies": []})
    # 按任务
    task_data: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "ok": 0, "tokens_in": 0, "tokens_out": 0})
    # 按模型
    model_data: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "ok": 0, "tokens_in": 0, "tokens_out": 0, "channel": ""})
    # 按天
    daily_data: dict[str, dict] = defaultdict(lambda: {
        "calls": 0, "tokens_in": 0, "tokens_out": 0,
        "local_in": 0, "local_out": 0, "cloud_in": 0, "cloud_out": 0})

    for r in rows:
        day = datetime.datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d")
        ch = r["channel"] or "unknown"
        tk = r["task"] or "unknown"
        md = r["model"] or "unknown"

        ch_data[ch]["calls"] += 1
        ch_data[ch]["ok"] += r["ok"]
        ch_data[ch]["tokens_in"] += r["tokens_in"]
        ch_data[ch]["tokens_out"] += r["tokens_out"]
        ch_data[ch]["latencies"].append(r["latency_ms"])

        task_data[tk]["calls"] += 1
        task_data[tk]["ok"] += r["ok"]
        task_data[tk]["tokens_in"] += r["tokens_in"]
        task_data[tk]["tokens_out"] += r["tokens_out"]

        model_data[md]["calls"] += 1
        model_data[md]["ok"] += r["ok"]
        model_data[md]["tokens_in"] += r["tokens_in"]
        model_data[md]["tokens_out"] += r["tokens_out"]
        model_data[md]["channel"] = ch

        daily_data[day]["calls"] += 1
        daily_data[day]["tokens_in"] += r["tokens_in"]
        daily_data[day]["tokens_out"] += r["tokens_out"]
        key = f"{ch}_in" if ch in ("local", "cloud") else "local_in"
        key2 = f"{ch}_out" if ch in ("local", "cloud") else "local_out"
        daily_data[day][key] += r["tokens_in"]
        daily_data[day][key2] += r["tokens_out"]

    # 填充空白天（供图表连续）
    today = datetime.date.today()
    daily_list = []
    for i in range(days - 1, -1, -1):
        d = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        v = daily_data.get(d, {"calls": 0, "tokens_in": 0, "tokens_out": 0,
                                "local_in": 0, "local_out": 0, "cloud_in": 0, "cloud_out": 0})
        daily_list.append({"date": d, **v})

    def _fmt_channel(v: dict) -> dict:
        lats = sorted(v["latencies"])
        return {
            "calls": v["calls"],
            "success_rate": round(v["ok"] / max(v["calls"], 1), 3),
            "tokens_in": v["tokens_in"],
            "tokens_out": v["tokens_out"],
            "tokens_total": v["tokens_in"] + v["tokens_out"],
            "avg_latency_ms": int(sum(lats) / max(len(lats), 1)) if lats else 0,
            "p50_latency_ms": lats[len(lats) // 2] if lats else 0,
        }

    # 最近调用明细
    recent = []
    for r in reversed(rows[-20:]):
        recent.append({
            "ts": r["ts"],
            "task": r["task"],
            "channel": r["channel"],
            "model": r["model"],
            "latency_ms": r["latency_ms"],
            "tokens_in": r["tokens_in"],
            "tokens_out": r["tokens_out"],
            "ok": bool(r["ok"]),
        })

    return {
        "window_days": days,
        "totals": {
            "calls": total_calls,
            "success_rate": round(total_ok / max(total_calls, 1), 3),
            "tokens_in": total_in,
            "tokens_out": total_out,
            "tokens_total": total_in + total_out,
        },
        "by_channel": {k: _fmt_channel(v) for k, v in ch_data.items()},
        "daily": daily_list,
        "by_task": {
            k: {"calls": v["calls"], "tokens_in": v["tokens_in"],
                "tokens_out": v["tokens_out"], "tokens_total": v["tokens_in"] + v["tokens_out"],
                "success_rate": round(v["ok"] / max(v["calls"], 1), 3)}
            for k, v in sorted(task_data.items(), key=lambda x: -x[1]["tokens_out"])
        },
        "by_model": {
            k: {"calls": v["calls"], "tokens_in": v["tokens_in"],
                "tokens_out": v["tokens_out"], "tokens_total": v["tokens_in"] + v["tokens_out"],
                "channel": v["channel"], "success_rate": round(v["ok"] / max(v["calls"], 1), 3)}
            for k, v in sorted(model_data.items(), key=lambda x: -x[1]["tokens_out"])
        },
        "recent": recent,
    }


def _empty_dashboard(days: int) -> dict:
    import datetime
    today = datetime.date.today()
    daily = []
    for i in range(days - 1, -1, -1):
        d = (today - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        daily.append({"date": d, "calls": 0, "tokens_in": 0, "tokens_out": 0,
                       "local_in": 0, "local_out": 0, "cloud_in": 0, "cloud_out": 0})
    return {
        "window_days": days,
        "totals": {"calls": 0, "success_rate": 0, "tokens_in": 0, "tokens_out": 0, "tokens_total": 0},
        "by_channel": {},
        "daily": daily,
        "by_task": {},
        "by_model": {},
        "recent": [],
    }
