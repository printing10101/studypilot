"""笔记级 FSRS 复习调度。

借鉴 LearnKit note review mode：不只闪卡，整篇讲义/教材章节也纳入
FSRS 间隔复习。到期时提示"该复习《XXX》了"，点进去是讲义 + 配套复习题。
"""
from . import db, fsrs


def ensure_doc_fsrs_columns() -> None:
    """给 documents 表补 FSRS 调度列（幂等迁移）。"""
    c = db.get_conn()
    cols = [r["name"] for r in c.execute("PRAGMA table_info(documents)")]
    # 字面量 DDL（同 db.get_conn 的迁移风格），列名不拼接任何外部输入
    if "review_state" not in cols:
        c.execute("ALTER TABLE documents ADD COLUMN review_state INTEGER DEFAULT 0")
    if "review_step" not in cols:
        c.execute("ALTER TABLE documents ADD COLUMN review_step INTEGER")
    if "review_stability" not in cols:
        c.execute("ALTER TABLE documents ADD COLUMN review_stability REAL DEFAULT 0")
    if "review_difficulty" not in cols:
        c.execute("ALTER TABLE documents ADD COLUMN review_difficulty REAL DEFAULT 0")
    if "review_due_at" not in cols:
        c.execute("ALTER TABLE documents ADD COLUMN review_due_at REAL DEFAULT 0")
    if "review_last" not in cols:
        c.execute("ALTER TABLE documents ADD COLUMN review_last REAL DEFAULT 0")
    if "review_reps" not in cols:
        c.execute("ALTER TABLE documents ADD COLUMN review_reps INTEGER DEFAULT 0")
    if "review_lapses" not in cols:
        c.execute("ALTER TABLE documents ADD COLUMN review_lapses INTEGER DEFAULT 0")
    c.commit()


def schedule_doc_review(did: str, rating: int) -> dict | None:
    """对讲义文档做 FSRS 评分。rating 1..4（忘了/困难/良好/轻松）。

    返回调度结果（含下次间隔预告）。
    """
    doc = db.get_document(did)
    if not doc:
        return None
    row = {
        "id": did,
        "state": doc.get("review_state", 0) or 0,
        "step": doc.get("review_step"),
        "stability": doc.get("review_stability", 0) or 0,
        "difficulty": doc.get("review_difficulty", 0) or 0,
        "last_review": doc.get("review_last", 0) or 0,
        "due_at": doc.get("review_due_at", 0) or 0,
        "reps": doc.get("review_reps", 0) or 0,
        "lapses": doc.get("review_lapses", 0) or 0,
    }
    sched = fsrs.review(row, rating)
    reps = row["reps"] + 1
    lapses = row["lapses"] + (1 if rating == fsrs.R_AGAIN else 0)

    c = db.get_conn()
    c.execute(
        "UPDATE documents SET review_state=?, review_step=?, review_stability=?, "
        "review_difficulty=?, review_due_at=?, review_last=?, review_reps=?, review_lapses=? "
        "WHERE id=?",
        (sched["state"], sched["step"], sched["stability"], sched["difficulty"],
         sched["due_at"], sched["last_review"], reps, lapses, did))
    c.commit()
    return {
        "id": did, "filename": doc.get("filename", ""),
        "state": sched["state"], "stability": round(sched["stability"], 2),
        "due_at": sched["due_at"],
        "interval_seconds": sched["interval_seconds"],
        "interval_human": _human_interval(sched["interval_seconds"]),
        "reps": reps, "lapses": lapses,
    }


def list_due_doc_reviews(space_id: str) -> list[dict]:
    """列出空间内到期需要复习的讲义文档。"""
    # 必须用带 review_* 列的查询：普通列表查询不含这些列，会让所有文档恒判「从未复习」
    docs = db.list_documents_with_review(space_id)
    now = db.now()
    due = []
    for d in docs:
        if d.get("status") != "ready":
            continue
        due_at = d.get("review_due_at", 0) or 0
        # 从未复习过的文档：创建后 1 天到期
        if due_at <= 0:
            created = d.get("created_at", now)
            due_at = created + 86400
        if due_at <= now:
            due.append({
                "id": d["id"],
                "filename": d["filename"],
                "due_at": due_at,
                "state": d.get("review_state", 0) or 0,
                "stability": d.get("review_stability", 0) or 0,
                "reps": d.get("review_reps", 0) or 0,
                "never_reviewed": (d.get("review_reps", 0) or 0) == 0,
            })
    due.sort(key=lambda x: x["due_at"])
    return due


def doc_review_preview(did: str) -> dict | None:
    """预览四档评分的下次间隔（供前端按钮预告）。"""
    doc = db.get_document(did)
    if not doc:
        return None
    row = {
        "id": did,
        "state": doc.get("review_state", 0) or 0,
        "step": doc.get("review_step"),
        "stability": doc.get("review_stability", 0) or 0,
        "difficulty": doc.get("review_difficulty", 0) or 0,
        "last_review": doc.get("review_last", 0) or 0,
        "due_at": doc.get("review_due_at", 0) or 0,
        "reps": doc.get("review_reps", 0) or 0,
        "lapses": doc.get("review_lapses", 0) or 0,
    }
    preview = fsrs.preview_intervals(row)
    return {
        "id": did,
        "filename": doc.get("filename", ""),
        "preview": {k: {"seconds": v, "human": _human_interval(v)} for k, v in preview.items()},
    }


def _human_interval(seconds: float) -> str:
    """秒 → 人可读间隔。"""
    if seconds < 60:
        return "不到 1 分钟"
    if seconds < 3600:
        return f"{int(seconds / 60)} 分钟"
    if seconds < 86400:
        return f"{int(seconds / 3600)} 小时"
    days = seconds / 86400
    if days < 30:
        return f"{int(days)} 天"
    if days < 365:
        return f"{days / 30:.1f} 个月"
    return f"{days / 365:.1f} 年"
