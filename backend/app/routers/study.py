"""学习调度：掌握度/复习、错题本、闪卡、计划任务、今日视图、讲义 FSRS 复习、BKT、Anki。"""
import logging
import urllib.parse

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .. import anki_io, bkt_fit, db, learning_methods, note_review, skills, study_metrics, velocity
from .common import space_or_404

router = APIRouter()


class RedoIn(BaseModel):
    qids: list[str] = []


class FlashGradeIn(BaseModel):
    know: bool | None = None   # 旧两档自评：记得/忘了（兼容保留）
    rating: int | None = None  # FSRS 四档：1=忘了 2=困难 3=良好 4=轻松，优先于 know


class ToggleIn(BaseModel):
    done: bool


class TaskDateIn(BaseModel):
    due_date: str = ""      # YYYY-MM-DD，空串清除


class DocGradeIn(BaseModel):
    rating: int = Field(ge=1, le=4)  # 1(忘了)/2(困难)/3(良好)/4(轻松)


# ---------- 掌握度 / 复习调度 ----------

@router.get("/api/spaces/{sid}/mastery")
def api_mastery(sid: str):
    space_or_404(sid)
    points = db.list_mastery(sid)
    fb = db.list_feedback(sid, 20)
    return {
        "points": points,
        "weak_count": sum(1 for p in points if p["status"] == "weak"),
        "mastered_count": sum(1 for p in points if p["status"] == "mastered"),
        "due": db.due_points(sid),
        "recent_feedback": fb,
    }


@router.get("/api/spaces/{sid}/review/due")
def api_review_due(sid: str):
    due = db.due_points(sid)
    weak = db.weak_points(sid, 5)
    return {"due": due, "weakest": weak}


@router.get("/api/spaces/{sid}/mastery/history")
def api_mastery_history(sid: str, limit: int = 500):
    space_or_404(sid)
    return db.list_mastery_history(sid, limit=min(max(limit, 10), 5000))


# ---------- 错题本 ----------

@router.get("/api/spaces/{sid}/wrong-questions")
def api_wrong_questions(sid: str):
    space_or_404(sid)
    return db.wrong_questions(sid)


@router.post("/api/spaces/{sid}/wrong-questions/redo")
def api_wrong_redo(sid: str, body: RedoIn):
    space_or_404(sid)
    try:
        return skills.wrong_redo(sid, body.qids or None)[0]
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# ---------- 闪卡 ----------

@router.get("/api/spaces/{sid}/flashcards")
def api_flashcards(sid: str, due: int = 0, limit: int = 30):
    space_or_404(sid)
    return {"cards": db.list_flashcards(sid, due_only=bool(due), limit=limit, with_preview=bool(due)),
            "stats": db.flashcard_stats(sid)}


@router.post("/api/spaces/{sid}/flashcards/{fid}/grade")
def api_flashcard_grade(sid: str, fid: str, body: FlashGradeIn):
    if body.rating is None and body.know is None:
        raise HTTPException(400, "缺少评分：rating(1..4) 或 know(bool)")
    r = db.grade_flashcard(sid, fid, know=body.know, rating=int(body.rating or 0))
    if not r:
        raise HTTPException(404, "闪卡不存在")
    return r


@router.delete("/api/spaces/{sid}/flashcards")
def api_flashcards_clear(sid: str):
    db.clear_flashcards(sid)
    return {"ok": True}


# ---------- 学习计划任务 ----------

@router.get("/api/spaces/{sid}/plan")
def api_plan_tasks(sid: str):
    space_or_404(sid)
    tasks = db.list_plan_tasks(sid)
    return {"tasks": tasks, "done": sum(1 for t in tasks if t["done"]), "total": len(tasks)}


@router.post("/api/spaces/{sid}/plan/{tid}/toggle")
def api_plan_toggle(sid: str, tid: str, body: ToggleIn):
    r = db.toggle_plan_task(sid, tid, body.done)
    if not r:
        raise HTTPException(404, "任务不存在")
    return r


@router.post("/api/spaces/{sid}/plan/{tid}/date")
def api_plan_set_date(sid: str, tid: str, body: TaskDateIn):
    try:
        r = db.set_plan_task_date(sid, tid, body.due_date)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not r:
        raise HTTPException(404, "任务不存在")
    return r


# ---------- 今日视图 / 学习速度 / 今日一题 ----------

@router.get("/api/spaces/{sid}/today")
def api_today(sid: str):
    """今日学习视图：到期复习点 + 到期闪卡 + 今日/未排期计划任务 + 今日完成 + 学习速度。"""
    space_or_404(sid)
    snap = db.today_snapshot(sid)
    # 附加学习速度与完成预测（附加面板失败降级为 null，但必须留痕——
    # 否则这些模块的真实 bug 会被吞成"面板空白"，无从发现）
    try:
        snap["velocity"] = velocity.compute_velocity(sid)
        snap["forecast"] = velocity.forecast_completion(sid)
    except Exception:
        logging.warning("today 附加面板 velocity 计算失败（space=%s）", sid, exc_info=True)
        snap["velocity"] = None
        snap["forecast"] = None
    # 证据导向学习方法建议（零 LLM）
    try:
        advice = learning_methods.advise_for_space(sid, limit=3)
        snap["methods"] = {
            "tip": advice.tip,
            "focus": advice.focus,
            "items": advice.methods,
            "daily": learning_methods.daily_tip(sid),
            "persona": advice.persona,
        }
    except Exception:
        logging.warning("today 附加面板 methods 计算失败（space=%s）", sid, exc_info=True)
        snap["methods"] = None
    try:
        snap["metrics"] = {
            "consistency": study_metrics.consistency(sid),
            "load": study_metrics.daily_load(sid),
            "calibration": study_metrics.calibration(sid),
            "countdown": study_metrics.exam_countdown(sid),
        }
    except Exception:
        logging.warning("today 附加面板 metrics 计算失败（space=%s）", sid, exc_info=True)
        snap["metrics"] = None
    return snap


@router.get("/api/spaces/{sid}/velocity")
def api_velocity(sid: str):
    """学习速度 + 完成度预测。"""
    space_or_404(sid)
    return {"velocity": velocity.compute_velocity(sid),
            "forecast": velocity.forecast_completion(sid)}


@router.get("/api/spaces/{sid}/daily-question")
def api_daily_question(sid: str):
    """今日一题：ZPD 最优推荐。"""
    space_or_404(sid)
    try:
        return skills.daily_question(sid)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(502, f"模型通道失败: {str(e)[:200]}") from e


# ---------- 讲义笔记级 FSRS 复习 ----------

@router.get("/api/spaces/{sid}/doc-reviews/due")
def api_due_doc_reviews(sid: str):
    """列出到期需要复习的讲义文档。"""
    space_or_404(sid)
    return note_review.list_due_doc_reviews(sid)


@router.post("/api/spaces/{sid}/doc-reviews/{did}/grade")
def api_grade_doc_review(sid: str, did: str, body: DocGradeIn):
    """对讲义做 FSRS 复习评分。body: {"rating": 1..4}"""
    space_or_404(sid)
    doc = db.get_document(did)
    if not doc:
        raise HTTPException(404, "文档不存在")
    if doc.get("space_id") != sid:
        # 与 DELETE /documents 同一口径：不许跨空间操作他空间文档
        raise HTTPException(404, "文档不属于该空间")
    result = note_review.schedule_doc_review(did, body.rating)
    if not result:
        raise HTTPException(404, "文档不存在")
    return result


@router.get("/api/spaces/{sid}/doc-reviews/{did}/preview")
def api_preview_doc_review(sid: str, did: str):
    """预览四档评分的下次间隔。"""
    space_or_404(sid)
    doc = db.get_document(did)
    if not doc:
        raise HTTPException(404, "文档不存在")
    if doc.get("space_id") != sid:
        raise HTTPException(404, "文档不属于该空间")
    result = note_review.doc_review_preview(did)
    if not result:
        raise HTTPException(404, "文档不存在")
    return result


# ---------- BKT 参数个性化拟合 ----------

@router.post("/api/spaces/{sid}/bkt/fit")
def api_bkt_fit(sid: str):
    """对空间内有足够答题记录的知识点做 Baum-Welch EM 个性化拟合。"""
    space_or_404(sid)
    fitted = bkt_fit.fit_for_space(sid)
    return {"fitted_count": len(fitted), "params": fitted}


@router.get("/api/spaces/{sid}/bkt/params")
def api_bkt_params(sid: str):
    """查看当前使用的 BKT 参数（个性化或默认）。"""
    space_or_404(sid)
    mastery_list = db.list_mastery(sid)
    result = {}
    for m in mastery_list[:50]:
        result[m["point"]] = bkt_fit.get_params(sid, m["point"])
    return result


# ---------- Anki 导入导出 ----------

@router.post("/api/spaces/{sid}/anki/import")
def api_anki_import(sid: str, file: UploadFile = File(...)):
    """导入 .apkg 牌组到指定空间。
    必须是同步 def：此前 async def 里同步解析 100MB zip 会冻结整个事件循环，
    导入期间所有页面请求、SSE 心跳、静态资源全部无响应。"""
    space_or_404(sid)
    if not file.filename or not file.filename.endswith(".apkg"):
        raise HTTPException(400, "请上传 .apkg 文件")
    data = file.file.read()
    if len(data) > 100 * 1024 * 1024:  # 100MB 上限
        raise HTTPException(400, "文件过大（上限 100MB）")
    return anki_io.import_apkg(data, sid)


@router.get("/api/spaces/{sid}/anki/export")
def api_anki_export(sid: str):
    """导出空间闪卡为 .apkg。"""
    space_or_404(sid)
    data = anki_io.export_apkg(sid)
    space = db.get_space(sid)
    fname = f"StudyPilot_{space['name'] if space else sid}.apkg"
    # HTTP 头只能 latin-1：中文空间名走 RFC 5987 filename*，ASCII 名走普通 filename
    quoted = urllib.parse.quote(fname, safe="")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=\"deck.apkg\"; filename*=UTF-8''{quoted}"},
    )
