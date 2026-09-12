"""个人学生档案（单用户）+ 跨空间学习总览。"""
from fastapi import APIRouter
from pydantic import BaseModel

from .. import db

router = APIRouter()


class ProfileIn(BaseModel):
    current_school: str = ""
    major: str = ""
    year: str = ""
    rank_hint: str = ""
    flags: list[str] = []
    goal_type: str = "考研"
    target_school: str = ""
    target_major: str = ""
    timeline: str = ""
    notes: str = ""
    learner_personas: list[str] = []


@router.get("/api/profile")
def api_profile_get():
    return db.get_student_profile()


@router.put("/api/profile")
def api_profile_put(body: ProfileIn):
    return db.save_student_profile(body.model_dump())


@router.get("/api/profile/overview")
def api_profile_overview():
    """跨空间学习总览：各课程空间的掌握度/薄弱点/到期/测验/闪卡概览。"""
    out = []
    for s in db.list_spaces():
        sid = s["id"]
        points = db.list_mastery(sid)
        out.append({
            "id": sid, "name": s["name"],
            "points": len(points),
            "weak": sum(1 for p in points if p["status"] == "weak"),
            "mastered": sum(1 for p in points if p["status"] == "mastered"),
            "avg": round(sum(p["score"] for p in points) / len(points), 3) if points else 0.0,
            "due": len(db.due_points(sid)),
            "quizzes": db.count_quizzes(sid),
            "flash_due": db.flashcard_stats(sid)["due"],
        })
    return {"spaces": out}
