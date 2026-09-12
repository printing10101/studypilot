"""已修课程 · 培养方案完成度审核。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import audit, db

router = APIRouter()


class TakenCourseIn(BaseModel):
    name: str
    credit: float = 0.0
    grade: str = ""
    semester: str = ""
    status: str = "done"    # done 已修 / taking 修读中


class TextImportIn(BaseModel):
    text: str


@router.get("/api/audit/courses")
def api_audit_courses():
    return {"courses": db.list_taken_courses()}


@router.post("/api/audit/courses")
def api_audit_add_course(body: TakenCourseIn):
    try:
        return db.add_taken_course(body.name, body.credit, body.grade, body.semester, body.status)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/audit/courses/import")
def api_audit_import_courses(body: TextImportIn):
    """粘贴成绩单文本批量导入：规则解析优先，LLM 兜底。"""
    try:
        return audit.import_courses_text(body.text)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/api/audit/courses/{cid}")
def api_audit_delete_course(cid: str):
    if not db.delete_taken_course(cid):
        raise HTTPException(404, "课程不存在")
    return {"ok": True}


@router.post("/api/audit/courses/clear")
def api_audit_clear_courses():
    return {"removed": db.clear_taken_courses()}


@router.get("/api/audit/run")
def api_audit_run(school: str = "", major: str = ""):
    """完成度审核：学校/专业缺省时回退个人档案。"""
    return audit.run_audit(school, major)
