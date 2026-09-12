"""学涯规划：成长手册 / 竞赛分析 / 培养方案 / 课程表 / 目标计划。"""
import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import competitions, db, handbook, ingest, planner, rag, schedule, syllabus
from .common import MAX_UPLOAD_BYTES, display_name, save_upload_capped

router = APIRouter()


class HandbookIn(BaseModel):
    space_id: str = ""
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


class CompetitionIn(BaseModel):
    goal: str = ""              # 考研 / 推免/保研 / 就业 / 出国；留空按档案 goal_type 归一
    use_llm: bool = True        # 是否追加 LLM 备赛策略
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


class ScheduleSaveIn(BaseModel):
    term: str
    courses: list[dict] = []


class ScheduleTextIn(BaseModel):
    text: str


class PlannerIn(BaseModel):
    school: str = ""
    major: str = ""
    year: str = ""
    goal_type: str = "考研"
    target: str = ""
    term: str = ""
    horizon: str = "本学期"
    space_id: str = ""


class PlanToggleIn(BaseModel):
    task_id: str
    done: bool


class PlanPushIn(BaseModel):
    space_id: str
    replace: bool = False


class SyllabusImportIn(BaseModel):
    school: str
    major: str = ""
    text: str = ""


# ---------- 成长手册 ----------

@router.post("/api/handbook/generate")
def api_handbook_generate(body: HandbookIn):
    try:
        return handbook.generate(body.space_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"手册生成失败（检查模型通道）：{str(e)[:200]}") from e


@router.get("/api/competitions/catalog")
def api_competition_catalog():
    """内置竞赛目录：级别 / 窗口 / 备赛周期 / 专业匹配 / 各路径价值。"""
    return competitions.catalog()


@router.post("/api/competitions/analyze")
def api_competition_analyze(body: CompetitionIn):
    """目标导向竞赛分析：至少参加哪些（分级推荐）+ 可选 LLM 备赛策略。"""
    try:
        return competitions.analyze(body.model_dump(), goal=body.goal, use_llm=body.use_llm)
    except Exception as e:
        raise HTTPException(502, f"竞赛分析失败：{str(e)[:200]}") from e


@router.get("/api/handbook")
def api_handbook_list():
    return handbook.list_handbooks()


@router.get("/api/handbook/{hid}")
def api_handbook_get(hid: str):
    h = handbook.get_handbook(hid)
    if not h:
        raise HTTPException(404, "手册不存在")
    return h


@router.delete("/api/handbook/{hid}")
def api_handbook_delete(hid: str):
    handbook.delete_handbook(hid)
    return {"ok": True}


# ---------- 培养方案 ----------

@router.get("/api/syllabus/stats")
def api_syllabus_stats():
    return syllabus.stats()


@router.get("/api/syllabus/official")
def api_syllabus_official():
    """已收录官方全文的学校专业清单。"""
    return syllabus.official_sources()


@router.get("/api/syllabus/fulltext")
def api_syllabus_fulltext(school: str = "", major: str = ""):
    ft = syllabus.full_text(school, major)
    if not ft:
        raise HTTPException(404, "该学校专业暂未收录官方培养方案全文")
    return ft


@router.get("/api/syllabus/schools")
def api_syllabus_schools(q: str = "", region: str = "", tier: str = ""):
    return syllabus.list_schools(q, region, tier)


@router.get("/api/syllabus/majors")
def api_syllabus_majors(school: str = ""):
    return syllabus.majors_for_school(school)


@router.get("/api/syllabus/program")
def api_syllabus_program(school: str = "", major: str = ""):
    return syllabus.program(school, major)


@router.post("/api/syllabus/import")
def api_syllabus_import_text(body: SyllabusImportIn):
    try:
        return syllabus.import_handbook(body.school, body.major, body.text, source="粘贴文本")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(502, f"培养方案抽取失败（检查模型通道）：{str(e)[:200]}") from e


@router.post("/api/syllabus/import/file")
def api_syllabus_import_file(school: str, major: str = "", file: UploadFile = File(...)):
    display = display_name(file)
    ext = ingest.ext_of(display)
    if ext not in ingest.UPLOAD_EXTS:
        raise HTTPException(400, "支持 PDF / TXT / Markdown / 图片（会 OCR）")
    tmp_path = save_upload_capped(file, ext, MAX_UPLOAD_BYTES)
    try:
        text = rag.parse_file(tmp_path, display)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    try:
        return syllabus.import_handbook(school, major, text, source=display)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(502, f"培养方案抽取失败（检查模型通道）：{str(e)[:200]}") from e


# ---------- 课程表 ----------

@router.get("/api/schedule")
def api_schedule(term: str = ""):
    terms = db.list_schedule_terms()
    if not term:
        term = terms[0]["term"] if terms else ""
    return {"term": term, "terms": terms, "courses": db.list_schedule(term)}


@router.post("/api/schedule/import")
def api_schedule_import_text(body: ScheduleTextIn):
    try:
        return schedule.import_from_text(body.text)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/schedule/import/file")
def api_schedule_import_file(file: UploadFile = File(...)):
    display = display_name(file)
    ext = ingest.ext_of(display)
    if ext not in ingest.IMAGE_EXTS + (".xlsx", ".csv", ".json", ".txt", ".md", ".markdown"):
        raise HTTPException(400, "课程表支持：截图(png/jpg/webp/bmp) / Excel(.xlsx) / CSV / JSON(WakeUp) / 文本")
    tmp_path = save_upload_capped(file, ext, MAX_UPLOAD_BYTES)
    try:
        return schedule.import_from_file(tmp_path, display)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.put("/api/schedule")
def api_schedule_save(body: ScheduleSaveIn):
    try:
        n = schedule.save(body.term, body.courses)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"term": body.term, "saved": n, "courses": db.list_schedule(body.term)}


@router.delete("/api/schedule")
def api_schedule_delete(term: str):
    db.delete_schedule(term)
    return {"ok": True}


# ---------- 目标计划 ----------

@router.get("/api/planner")
def api_planner_list():
    return db.list_career_plans()


@router.post("/api/planner/generate")
def api_planner_generate(body: PlannerIn):
    try:
        return planner.generate(body.school, body.major, body.year, body.goal_type,
                                body.target, body.term, body.horizon, body.space_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(502, f"计划生成失败（检查模型通道）：{str(e)[:200]}") from e


@router.get("/api/planner/{pid}")
def api_planner_get(pid: str):
    p = planner.get_plan(pid)
    if not p:
        raise HTTPException(404, "计划不存在")
    return p


@router.post("/api/planner/{pid}/toggle")
def api_planner_toggle(pid: str, body: PlanToggleIn):
    r = planner.toggle_task(pid, body.task_id, body.done)
    if not r:
        raise HTTPException(404, "任务不存在")
    return r


@router.post("/api/planner/{pid}/push")
def api_planner_push(pid: str, body: PlanPushIn):
    try:
        return planner.push_to_space(pid, body.space_id, body.replace)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.delete("/api/planner/{pid}")
def api_planner_delete(pid: str):
    r = planner.delete_plan(pid)
    return {"ok": True, "removed_pushed_tasks": r.get("deleted_pushed_tasks", 0)}
