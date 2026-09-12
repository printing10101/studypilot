"""FSRS 间隔重复调度（闪卡与知识点复习共用）。

封装 py-fsrs（MIT 协议）：DB 行 <-> fsrs.Card 互转、评分调度、四档间隔预览、
幂律遗忘曲线留存率。旧的 Leitner 复习盒（box 1..5 固定间隔）数据无需迁移脚本——
首次评分时按 box 对应的旧间隔折算初始稳定性（在目标留存率 0.9 下 FSRS 间隔≈稳定性），
此后由 FSRS 接管调度；box 列保留但仅作展示（1=刚忘/学习中 .. 5=长稳）。
"""
from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from fsrs import Card, Rating, Scheduler, State

# 旧 Leitner 盒间隔（秒）：盒1=30分钟 盒2=1天 盒3=3天 盒4=7天 盒5=14天
# 仅用于老数据折算初始稳定性与 box 展示同步，新调度不再使用
BOX_DELAYS = {1: 1800.0, 2: 86400.0, 3: 259200.0, 4: 604800.0, 5: 1209600.0}

DESIRED_RETENTION = 0.9   # 目标记住率：调低间隔变长、调高变短
MAX_INTERVAL_DAYS = 365   # 课程学习场景：单卡最长一年后重现

scheduler = Scheduler(desired_retention=DESIRED_RETENTION,
                      maximum_interval=MAX_INTERVAL_DAYS,
                      enable_fuzzing=False)

# FSRS 四档评分
R_AGAIN, R_HARD, R_GOOD, R_EASY = 1, 2, 3, 4

# 掌握度证据 → FSRS 评分（verdict 与 db._EVIDENCE_STRENGTH 同一套枚举）
VERDICT_RATING = {"correct": R_GOOD, "partial": R_HARD, "progress": R_HARD,
                  "confused": R_AGAIN, "wrong": R_AGAIN}

# FSRS-6 幂律遗忘曲线 R(t,S) = (1 + F·t/S)^D，F=19/81、D=-0.5
_FACTOR = 19.0 / 81.0
_DECAY = -0.5


def _ts2dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=UTC)


def _dt2ts(dt: datetime) -> float:
    return dt.timestamp()


def _card_id(row_id: str) -> int:
    """由行 id 生成稳定整数 card_id（fsrs 6.x Card 序列化必填，仅内部标识用）。"""
    try:
        return int((row_id or "0")[:8], 16) or 1
    except ValueError:
        return 1


def _legacy_last_review(row: dict[str, Any], box: int) -> float:
    """推断老数据（无 FSRS 状态）上次复习时间；0 表示从未刷过。"""
    if "attempts" in row:  # mastery 行：updated_at 随每次评分刷新
        return float(row.get("updated_at") or 0) if int(row.get("attempts") or 0) > 0 else 0.0
    # flashcards 行：box>1 或 due 被推后过（>60s）都算刷过
    created = float(row.get("created_at") or 0)
    due = float(row.get("due_at") or 0)
    if box > 1:
        return max(created, due - BOX_DELAYS.get(box, BOX_DELAYS[1]))
    if due - created > 60:
        return created
    return 0.0


def card_from_row(row: dict[str, Any]) -> Card:
    """DB 行 → FSRS 卡：已有 FSRS 状态直接还原；老数据按 Leitner 盒折算初始状态。"""
    cid = _card_id(row.get("id") or "")
    due_ts = float(row.get("due_at") or 0) or time.time()
    stability = float(row.get("stability") or 0)
    if stability > 0:
        last = float(row.get("last_review") or 0)
        # state=0（New）是合法值，不能用 `or` 兜底——会把 New 吞成 Review
        raw_state = row.get("state")
        state_val = int(raw_state) if raw_state is not None else State.Review.value
        return Card(card_id=cid, state=State(state_val),
                    step=int(row["step"]) if row.get("step") is not None else None,
                    stability=stability,
                    difficulty=float(row.get("difficulty") or 5.0),
                    due=_ts2dt(due_ts),
                    last_review=_ts2dt(last) if last else None)
    box = int(row.get("box") or 1)
    last_ts = _legacy_last_review(row, box)
    if last_ts <= 0:  # 从未刷过 → 全新卡（立即到期，走学习步进）
        return Card(card_id=cid, due=_ts2dt(due_ts))
    interval_s = BOX_DELAYS.get(box, BOX_DELAYS[1])
    return Card(card_id=cid,
                state=State.Review if box > 1 else State.Learning,
                step=None,
                stability=max(interval_s, 600.0) / 86400.0,  # 间隔≈S(0.9)，把旧盒位当稳定性
                difficulty=5.0,
                due=_ts2dt(due_ts),
                last_review=_ts2dt(min(last_ts, time.time())))


def review(row: dict[str, Any], rating: int) -> dict[str, Any]:
    """对一条 DB 行执行 FSRS 评分，返回需写回的调度字段。

    rating: 1=忘了 2=困难 3=良好 4=轻松
    """
    card = card_from_row(row)
    new_card, _log = scheduler.review_card(card, Rating(int(rating)))
    d = new_card.to_dict()
    due_ts = _dt2ts(datetime.fromisoformat(d["due"]))
    last_ts = _dt2ts(datetime.fromisoformat(d["last_review"])) if d["last_review"] else time.time()
    # box 仅作展示同步：忘了→盒1，其余按原盒推进（封顶盒5）
    old_box = int(row.get("box") or 1)
    box = 1 if rating == R_AGAIN else min(5, old_box + 1)
    return {
        "state": int(d["state"]),
        "step": d["step"],
        "stability": round(float(d["stability"] or 0.0), 4),
        "difficulty": round(float(d["difficulty"] or 0.0), 4),
        "due_at": due_ts,
        "last_review": last_ts,
        "box": box,
        "interval_seconds": max(0.0, due_ts - time.time()),
    }


def preview_intervals(row: dict[str, Any]) -> dict[str, float]:
    """四档评分各自的下次间隔（秒），供前端在刷卡按钮上预告。"""
    card = card_from_row(row)
    out: dict[str, float] = {}
    for r in (R_AGAIN, R_HARD, R_GOOD, R_EASY):
        c2, _ = scheduler.review_card(card, Rating(r))
        d = c2.to_dict()
        due_ts = _dt2ts(datetime.fromisoformat(d["due"]))
        out[str(r)] = max(60.0, due_ts - time.time())
    return out


def retrievability(stability: float, last_review_ts: float,
                   at: float | None = None) -> float:
    """FSRS 幂律遗忘曲线估算当前留存率；无 FSRS 状态返回 -1（调用方退回旧公式）。"""
    if not stability or stability <= 0 or not last_review_ts or last_review_ts <= 0:
        return -1.0
    dt_days = max(0.0, ((at if at is not None else time.time()) - last_review_ts) / 86400.0)
    r = (1.0 + _FACTOR * dt_days / stability) ** _DECAY
    return min(1.0, max(0.0, r))
