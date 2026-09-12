"""综合学习度量：一致性、负载、方法效果闭环、预测校准、考试倒计时。

与 learning_methods / learner_persona 协同：
- 度量提供「该推什么、该压什么」的硬信号；
- 方法/画像负责「怎么教」的软适配。
全部零 LLM。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta

from . import db

log = logging.getLogger("studypilot.study_metrics")

# 方法名（中文/近义）→ 方法 id，用于把 plan_tasks.method 映射到目录
_METHOD_ALIASES = {
    "检索": "retrieval", "检索练习": "retrieval", "自测": "retrieval", "测验": "retrieval",
    "间隔": "spacing", "间隔重复": "spacing", "分散": "spacing",
    "交错": "interleaving", "交错练习": "interleaving", "混练": "interleaving",
    "追问": "elaboration", "精细追问": "elaboration", "为什么": "elaboration",
    "自我解释": "self_explain", "讲步骤": "self_explain",
    "双重编码": "dual_coding", "画图": "dual_coding",
    "样例": "worked_example", "样例学习": "worked_example", "例题": "worked_example",
    "生成": "generation", "出题": "generation",
    "元认知": "metacognition", "校准": "metacognition",
    "合意困难": "desirable_difficulty", "变式": "desirable_difficulty",
    "费曼": "feynman", "讲解": "feynman",
    "会话结构": "session_structure", "番茄": "session_structure",
    "错因": "error_analysis", "复盘": "error_analysis",
}


def normalize_method_id(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    from . import learning_methods
    if raw in learning_methods.METHODS:
        return raw
    for m in learning_methods.METHODS.values():
        if raw == m.name or raw in m.name or m.name in raw:
            return m.id
    for alias, mid in _METHOD_ALIASES.items():
        if alias in raw:
            return mid
    return ""


# ---------- 表结构（懒迁移） ----------

_ENSURED = False
_ENSURE_LOCK = threading.Lock()


def _ensure_tables() -> None:
    global _ENSURED
    if _ENSURED:
        return
    # 加锁 + 双检：并发首用时两个线程同时走到 ALTER 会 duplicate column 500
    with _ENSURE_LOCK:
        if _ENSURED:
            return
        c = db.get_conn()
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS method_events(
              id TEXT PRIMARY KEY,
              space_id TEXT NOT NULL,
              method_id TEXT NOT NULL,
              kind TEXT DEFAULT 'task_done',  -- task_done | quiz | recommend
              meta TEXT DEFAULT '{}',
              score_delta REAL DEFAULT 0,     -- 关联掌握度变化（事后回填）
              created_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_me_space ON method_events(space_id, created_at);
            CREATE TABLE IF NOT EXISTS quiz_predictions(
              quiz_id TEXT PRIMARY KEY,
              space_id TEXT NOT NULL,
              predicted REAL NOT NULL,        -- 0~1 预测正确率
              actual REAL,                    -- 判卷后回填
              created_at REAL
            );
            """
        )
        qcols = {r[1] for r in c.execute("PRAGMA table_info(quiz_records)")}
        if "predicted" not in qcols:
            c.execute("ALTER TABLE quiz_records ADD COLUMN predicted REAL DEFAULT -1")
        c.commit()
        _ENSURED = True


# ---------- 方法使用与效果 ----------

def record_method_use(space_id: str, method_raw: str, kind: str = "task_done",
                      meta: dict | None = None) -> str:
    """记录一次方法使用（打卡完成计划任务、或系统推荐被采纳）。"""
    _ensure_tables()
    mid = normalize_method_id(method_raw)
    if not mid:
        return ""
    c = db.get_conn()
    eid = db.new_id()
    c.execute("INSERT INTO method_events(id,space_id,method_id,kind,meta,score_delta,created_at) "
              "VALUES(?,?,?,?,?,?,?)",
              (eid, space_id, mid, kind, json.dumps(meta or {}, ensure_ascii=False), 0.0, db.now()))
    c.commit()
    return eid


def _backfill_method_deltas(space_id: str) -> None:
    """把「方法使用后 48h 内相关知识点掌握度变化」回填到事件（幂等、轻量）。"""
    _ensure_tables()
    c = db.get_conn()
    rows = c.execute(
        "SELECT id, method_id, meta, created_at, score_delta FROM method_events "
        "WHERE space_id=? AND kind='task_done' AND score_delta=0 AND created_at>=?",
        (space_id, db.now() - 21 * 86400),
    ).fetchall()
    if not rows:
        return
    history = db.list_mastery_history(space_id)
    for row in rows:
        try:
            meta = json.loads(row["meta"] or "{}")
        except ValueError:
            meta = {}
        points = [str(p) for p in (meta.get("points") or []) if p]
        t0 = row["created_at"]
        t1 = t0 + 48 * 3600
        # 取这些点在事件后相对事件前的分差
        deltas = []
        for pt in points:
            before = [h for h in history if h["point"] == pt and h["created_at"] <= t0]
            after = [h for h in history if h["point"] == pt and t0 < h["created_at"] <= t1]
            if before and after:
                deltas.append(after[-1]["score"] - before[-1]["score"])
        if deltas:
            c.execute("UPDATE method_events SET score_delta=? WHERE id=?",
                      (round(sum(deltas) / len(deltas), 4), row["id"]))
    c.commit()


def method_efficacy(space_id: str, days: int = 30) -> list[dict]:
    """近 N 天各方法的使用次数与平均掌握度增量。"""
    _ensure_tables()
    _backfill_method_deltas(space_id)
    since = db.now() - days * 86400
    rows = db.rows_to_dicts(db.get_conn().execute(
        "SELECT method_id, kind, score_delta FROM method_events "
        "WHERE space_id=? AND created_at>=?", (space_id, since)).fetchall())
    from collections import defaultdict
    use = defaultdict(int)
    delta_sum = defaultdict(float)
    delta_n = defaultdict(int)
    for r in rows:
        use[r["method_id"]] += 1
        if r["kind"] == "task_done" and r["score_delta"]:
            delta_sum[r["method_id"]] += r["score_delta"]
            delta_n[r["method_id"]] += 1
    out = []
    for mid, n in sorted(use.items(), key=lambda x: -x[1]):
        avg = (delta_sum[mid] / delta_n[mid]) if delta_n[mid] else None
        out.append({
            "method_id": mid,
            "uses": n,
            "avg_delta": round(avg, 3) if avg is not None else None,
            "evidence_n": delta_n[mid],
        })
    return out


def efficacy_boost(space_id: str) -> dict[str, float]:
    """把「用得多且有效」的方法加权；用得多但无效的轻微降权。"""
    boost: dict[str, float] = {}
    for e in method_efficacy(space_id):
        b = 0.15  # 用过即可略优先（习惯延续）
        if e["evidence_n"] >= 2 and e["avg_delta"] is not None:
            if e["avg_delta"] >= 0.05:
                b += 0.6
            elif e["avg_delta"] >= 0.02:
                b += 0.3
            elif e["avg_delta"] <= -0.02:
                b -= 0.4
        elif e["uses"] >= 3 and e["avg_delta"] is None:
            b += 0.2  # 高频使用但还测不出增量：保持
        boost[e["method_id"]] = b
    return boost


# ---------- 一致性 / 负载 ----------

def _active_days(space_id: str, window_days: int = 30) -> set[str]:
    days: set[str] = set()
    for h in db.list_mastery_history(space_id):
        if h["created_at"] >= db.now() - window_days * 86400:
            days.add(time.strftime("%Y-%m-%d", time.localtime(h["created_at"])))
    for q in db.list_quizzes(space_id):
        if q.get("answers") and q.get("created_at", 0) >= db.now() - window_days * 86400:
            days.add(time.strftime("%Y-%m-%d", time.localtime(q["created_at"])))
    for t in db.list_plan_tasks(space_id):
        if t.get("done") and t.get("done_at", 0) >= db.now() - window_days * 86400:
            days.add(time.strftime("%Y-%m-%d", time.localtime(t["done_at"])))
    return days


def consistency(space_id: str) -> dict:
    """连续学习天数 + 近 7/30 天活跃天。"""
    # 窗口给足一年：streak 从今天往回数，40 天窗口会把长期连续学习封顶在 40
    days = _active_days(space_id, 366)
    if not days:
        return {"streak": 0, "active_7d": 0, "active_30d": 0, "last_active": ""}
    # streak：从今天或昨天往回数
    today = time.strftime("%Y-%m-%d")
    yesterday = time.strftime("%Y-%m-%d", time.localtime(db.now() - 86400))
    cursor = today if today in days else (yesterday if yesterday in days else "")
    streak = 0
    if cursor:
        d = datetime.strptime(cursor, "%Y-%m-%d")
        while True:
            key = d.strftime("%Y-%m-%d")
            if key not in days:
                break
            streak += 1
            d -= timedelta(days=1)
    def _in(n: int) -> int:
        cutoff = db.now() - n * 86400
        return sum(1 for day in days if datetime.strptime(day, "%Y-%m-%d").timestamp() >= cutoff)
    return {
        "streak": streak,
        "active_7d": _in(7),
        "active_30d": _in(30),
        "last_active": max(days),
    }


def daily_load(space_id: str) -> dict:
    """今日认知负载粗估：到期点 + 到期闪卡 + 今日任务。"""
    due = len(db.due_points(space_id))
    flash = db.flashcard_stats(space_id)
    snap = db.today_snapshot(space_id)
    tasks = len(snap.get("tasks_today") or [])
    # 权重：到期点 2、闪卡 0.3、任务 2（粗估「负担点」）
    load = due * 2 + flash.get("due", 0) * 0.3 + tasks * 2
    if load >= 20:
        band = "high"
    elif load >= 10:
        band = "medium"
    else:
        band = "low"
    return {
        "due_points": due,
        "flash_due": flash.get("due", 0),
        "tasks_today": tasks,
        "load_score": round(load, 1),
        "band": band,
        "suggested_minutes": 25 if band == "high" else (40 if band == "medium" else 50),
        "advice": (
            "负载偏高：只清到期与今日任务，不开新章；优先检索而非重读。"
            if band == "high" else
            "负载中等：到期 → 今日任务 → 一节新学，中间交错。"
            if band == "medium" else
            "负载可控：适合推进新学并做交错混练与合意困难。"
        ),
    }


def cross_space_load() -> list[dict]:
    """跨课程今日负载，便于统筹（排序：负载高优先）。"""
    out = []
    for s in db.list_spaces():
        try:
            load = daily_load(s["id"])
            if load["load_score"] <= 0 and load["tasks_today"] == 0:
                continue
            out.append({"space_id": s["id"], "space_name": s["name"], **load})
        except Exception:
            continue
    out.sort(key=lambda x: -x["load_score"])
    return out[:12]


# ---------- 预测校准 ----------

def set_quiz_prediction(quiz_id: str, predicted: float) -> dict:
    """交卷前记录学生自我预测正确率（0~1）。"""
    _ensure_tables()
    predicted = max(0.0, min(1.0, float(predicted)))
    c = db.get_conn()
    q = c.execute("SELECT id, space_id FROM quiz_records WHERE id=?", (quiz_id,)).fetchone()
    if not q:
        raise ValueError("测验不存在")
    c.execute("INSERT INTO quiz_predictions(quiz_id,space_id,predicted,actual,created_at) "
              "VALUES(?,?,?,?,?) ON CONFLICT(quiz_id) DO UPDATE SET predicted=excluded.predicted",
              (quiz_id, q["space_id"], predicted, None, db.now()))
    c.execute("UPDATE quiz_records SET predicted=? WHERE id=?", (predicted, quiz_id))
    c.commit()
    return {"quiz_id": quiz_id, "predicted": predicted}


def record_quiz_actual(quiz_id: str, actual: float) -> None:
    _ensure_tables()
    c = db.get_conn()
    q = c.execute("SELECT space_id FROM quiz_records WHERE id=?", (quiz_id,)).fetchone()
    if not q:
        return
    c.execute("INSERT INTO quiz_predictions(quiz_id,space_id,predicted,actual,created_at) "
              "VALUES(?,?,?,?,?) ON CONFLICT(quiz_id) DO UPDATE SET actual=excluded.actual",
              (quiz_id, q["space_id"], -1, actual, db.now()))
    c.commit()


def calibration(space_id: str, days: int = 60) -> dict:
    """预测 vs 实际：正偏差=过度自信。"""
    _ensure_tables()
    rows = db.rows_to_dicts(db.get_conn().execute(
        "SELECT predicted, actual FROM quiz_predictions "
        "WHERE space_id=? AND actual IS NOT NULL AND predicted>=0 AND created_at>=?",
        (space_id, db.now() - days * 86400)).fetchall())
    if not rows:
        return {"n": 0, "avg_bias": 0.0, "label": "unknown"}
    bias = sum(r["predicted"] - r["actual"] for r in rows) / len(rows)
    if bias >= 0.15:
        label = "overconfident"
    elif bias <= -0.12:
        label = "underconfident"
    else:
        label = "calibrated"
    return {
        "n": len(rows),
        "avg_bias": round(bias, 3),
        "avg_predicted": round(sum(r["predicted"] for r in rows) / len(rows), 3),
        "avg_actual": round(sum(r["actual"] for r in rows) / len(rows), 3),
        "label": label,
    }


# ---------- 考试倒计时 ----------

def _parse_deadline(timeline: str) -> str | None:
    """从档案时间线里抠出最近的 YYYY-MM / YYYY.MM.DD / YYYY年M月。"""
    import re
    t = timeline or ""
    # (?!\d) 防止区间日期把下个年份前两位当月/日；越界组合（month=20）跳过
    for m in re.finditer(r"(20\d{2})[年./-](\d{1,2})(?!\d)[月./-](\d{1,2})(?!\d)", t):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    for m in re.finditer(r"(20\d{2})[年./-](\d{1,2})月?(?!\d)", t):
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}-01"
    return None


def exam_countdown(space_id: str = "") -> dict | None:
    """基于个人档案 timeline 的考试倒计时与阶段方针。"""
    try:
        prof = db.get_student_profile()
    except Exception:
        return None
    deadline = _parse_deadline(prof.get("timeline") or "")
    if not deadline:
        return None
    try:
        end = datetime.strptime(deadline, "%Y-%m-%d")
    except ValueError:
        return None
    days_left = (end.date() - datetime.now().date()).days
    if days_left < 0:
        phase, strategy = "已过期", "核对是否需更新档案中的时间线。"
    elif days_left <= 14:
        phase, strategy = "冲刺期", "停止新学；每日：错题变式 + 全真模拟 + 睡眠；只补高风险点。"
    elif days_left <= 45:
        phase, strategy = "强化期", "交错真题与薄弱点；每周 2 次限时模拟；费曼讲清高频概念。"
    elif days_left <= 90:
        phase, strategy = "强化前期", "按依赖图补前置；检索+间隔为主；建立错因清单。"
    else:
        phase, strategy = "基础期", "样例→仿做→独立；建立知识图谱；养成每日到期检索。"
    load_hint = ""
    if space_id:
        try:
            ld = daily_load(space_id)
            load_hint = ld["advice"]
        except Exception:
            log.warning("考试倒计时的负载提示计算失败（load_hint 留空）", exc_info=True)
    return {
        "deadline": deadline,
        "days_left": days_left,
        "phase": phase,
        "strategy": strategy,
        "goal_type": prof.get("goal_type") or "",
        "load_hint": load_hint,
    }


# ---------- 综合快照 ----------

def space_metrics(space_id: str) -> dict:
    return {
        "consistency": consistency(space_id),
        "load": daily_load(space_id),
        "calibration": calibration(space_id),
        "method_efficacy": method_efficacy(space_id),
        "countdown": exam_countdown(space_id),
    }
