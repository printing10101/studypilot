"""FastAPI 入口：REST API。"""
import json
import os
import pathlib
import shutil
import tempfile
import urllib.parse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from . import anki_io, audit, bkt_fit, campus_net, competitions, connectors, db, defects, experts, export, handbook, ingest, learning_methods, library, llm, note_review, planner, rag, schedule, skills, study_metrics, syllabus, velocity
from .config import settings

app = FastAPI(title="StudyPilot", version="0.1.0")

# 本机服务防 drive-by：浏览器发起的跨站请求必带 Origin 头，白名单之外一律 403
# （桌面端同源页面、curl 脚本不带 Origin，不受影响）。前端与后端同源部署
# （桌面端 FastAPI 托管 / 开发模式 vite proxy），无需 CORS 放行。
ALLOWED_ORIGINS = {
    "http://127.0.0.1:8178", "http://localhost:8178",
    "http://127.0.0.1:5173", "http://localhost:5173",  # 开发模式 vite
}


@app.middleware("http")
async def _origin_guard(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return PlainTextResponse("Forbidden origin", status_code=403)
    return await call_next(request)

UPLOAD_ROOT = pathlib.Path(settings.upload_dir).resolve()


class SpaceIn(BaseModel):
    name: str
    description: str = ""


class ChatIn(BaseModel):
    mode: str = "ask"       # ask / plan / craft
    message: str
    guide: bool = False     # 苏格拉底引导模式（Ask）：先提示思路，不直接给答案


class SkillIn(BaseModel):
    skill: str
    params: dict = {}


class McpIn(BaseModel):
    name: str
    command: list[str]


class AttachIn(BaseModel):
    space_id: str


class FeedbackIn(BaseModel):
    message_id: str = ""
    rating: str = ""          # helpful / unhelpful
    understood: int = -1      # 1 听懂 / 0 没听懂
    confusion: str = ""       # 哪里没懂的补充说明


class LlmConfigIn(BaseModel):
    routing: str | None = None
    cloud_base_url: str | None = None
    cloud_api_key: str | None = None
    cloud_model: str | None = None


class UrlIn(BaseModel):
    url: str
    title: str = ""


class RedoIn(BaseModel):
    qids: list[str] = []


class FlashGradeIn(BaseModel):
    know: bool | None = None   # 旧两档自评：记得/忘了（兼容保留）
    rating: int | None = None  # FSRS 四档：1=忘了 2=困难 3=良好 4=轻松，优先于 know


class ToggleIn(BaseModel):
    done: bool


class TaskDateIn(BaseModel):
    due_date: str = ""      # YYYY-MM-DD，空串清除


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


# ---------- 个人学生档案（单用户） ----------

@app.get("/api/profile")
def api_profile_get():
    return db.get_student_profile()


@app.put("/api/profile")
def api_profile_put(body: ProfileIn):
    return db.save_student_profile(body.model_dump())


@app.get("/api/profile/overview")
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


@app.get("/api/health")
def health():
    try:
        models = llm._get_client("local").get("/models").json()
        llm_ok = True
    except Exception as e:
        models = {"error": str(e)[:200]}
        llm_ok = False
    return {"status": "ok", "llm": llm_ok, "model": settings.llm_model, "models": models}


# ---------- 已修课程 · 培养方案完成度审核 ----------

class TakenCourseIn(BaseModel):
    name: str
    credit: float = 0.0
    grade: str = ""
    semester: str = ""
    status: str = "done"    # done 已修 / taking 修读中


class TextImportIn(BaseModel):
    text: str


@app.get("/api/audit/courses")
def api_audit_courses():
    return {"courses": db.list_taken_courses()}


@app.post("/api/audit/courses")
def api_audit_add_course(body: TakenCourseIn):
    try:
        return db.add_taken_course(body.name, body.credit, body.grade, body.semester, body.status)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/audit/courses/import")
def api_audit_import_courses(body: TextImportIn):
    """粘贴成绩单文本批量导入：规则解析优先，LLM 兜底。"""
    try:
        return audit.import_courses_text(body.text)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/audit/courses/{cid}")
def api_audit_delete_course(cid: str):
    if not db.delete_taken_course(cid):
        raise HTTPException(404, "课程不存在")
    return {"ok": True}


@app.post("/api/audit/courses/clear")
def api_audit_clear_courses():
    return {"removed": db.clear_taken_courses()}


@app.get("/api/audit/run")
def api_audit_run(school: str = "", major: str = ""):
    """完成度审核：学校/专业缺省时回退个人档案。"""
    return audit.run_audit(school, major)


# ---------- 教材书库 ----------

@app.on_event("startup")
def _seed_library():
    connectors.load_persisted()  # 恢复上次注册的 MCP server
    try:
        library.seed()
    except Exception:
        pass  # 书目预置失败不阻塞服务启动，可在前端重试


class CampusConfigIn(BaseModel):
    auto_sync: bool | None = None
    interval_min: int | None = None
    campus_hosts: list[str] | None = None
    internal_hosts: list[str] | None = None
    public_cidrs: list[str] | None = None
    sources: list[dict] | None = None


# ---------- 校园网感知 · 校园信息自动同步 ----------

@app.get("/api/campus/status")
def api_campus_status(force: int = 0):
    """网络状态（校园网/公网/离线）+ 上次同步 + 信息源配置；force=1 跳过检测缓存。"""
    if force:
        campus_net.detect(force=True)
    return campus_net.status()


@app.post("/api/campus/sync")
def api_campus_sync():
    """立即同步全部信息源（离线时返回 skipped）。"""
    return campus_net.sync()


@app.get("/api/campus/items")
def api_campus_items(source: str = "", limit: int = 60, q: str = ""):
    """已抓取的校园信息条目（按发布日期倒序；q 按标题模糊过滤，如 q=四六级）。"""
    return {"items": campus_net.list_items(source, limit, q=q)}


@app.put("/api/campus/config")
def api_campus_config(body: CampusConfigIn):
    try:
        campus_net.save_cfg(body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return campus_net.status()


@app.on_event("startup")
def _start_campus_sync():
    campus_net.start_background_loop()


@app.get("/api/library")
def api_library(query: str = "", subject: str = ""):
    return db.list_books(query, subject)


@app.get("/api/library/subjects")
def api_library_subjects():
    return db.list_subjects()


@app.post("/api/library/upload")
def api_library_upload(file: UploadFile = File(...)):
    display_name = (file.filename or "未命名").replace("\\", "/").rsplit("/", 1)[-1] or "未命名"
    if ingest.ext_of(display_name) == ".zip":
        return {"batch": library.register_zip(os.path.splitext(display_name)[0] or "压缩包", file.file)}
    title, ext = os.path.splitext(display_name)
    bid = library.register_upload(title or "未命名", ext, file.file)
    book = db.get_book(bid)
    return {"id": bid, "status": book["status"] if book else "local"}


@app.post("/api/library/url")
def api_library_import_url(body: UrlIn):
    try:
        return library.import_url(body.url, body.title)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/library/{bid}/fetch")
def api_library_fetch(bid: str):
    try:
        return library.fetch_pdf(bid)
    except ValueError as e:
        # 书目不存在 / 无直链 / 下载失败等业务原因，前端弹明确提示而非 500
        raise HTTPException(400, str(e))


@app.post("/api/library/{bid}/attach")
def api_library_attach(bid: str, body: AttachIn):
    if not db.get_space(body.space_id):
        raise HTTPException(404, "空间不存在")
    return library.attach(bid, body.space_id)


@app.get("/api/library/{bid}/spaces")
def api_library_book_spaces(bid: str):
    return db.list_book_spaces(bid)


@app.delete("/api/library/{bid}")
def api_library_delete(bid: str):
    return library.delete_book(bid)


# ---------- 项目空间 ----------

@app.get("/api/spaces")
def api_list_spaces():
    return db.list_spaces()


@app.post("/api/spaces")
def api_create_space(body: SpaceIn):
    return db.create_space(body.name, body.description)


@app.delete("/api/spaces/{sid}")
def api_delete_space(sid: str):
    db.delete_space(sid)
    return {"ok": True}


# ---------- 文档 / RAG ----------

@app.get("/api/spaces/{sid}/documents")
def api_list_documents(sid: str):
    return db.list_documents(sid)


@app.post("/api/spaces/{sid}/documents")
def api_upload(sid: str, file: UploadFile = File(...)):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    # 原始文件名仅作展示名存库；磁盘文件由 tempfile 在上传目录内生成，用户输入不参与路径
    display_name = (file.filename or "未命名").replace("\\", "/").rsplit("/", 1)[-1] or "未命名"
    ext = ingest.ext_of(display_name)
    if ext not in ingest.UPLOAD_EXTS:
        raise HTTPException(400, "仅支持 PDF / TXT / Markdown / PPTX / 图片(png/jpg/webp/bmp) / zip 压缩包"
                                "（老版 .ppt 请先另存为 .pptx）")

    if ext == ".zip":
        # 压缩包：安全展开 → 逐个索引，返回批量结果
        fd, zip_path = tempfile.mkstemp(dir=UPLOAD_ROOT, suffix=".zip")
        try:
            with os.fdopen(fd, "wb") as f:
                shutil.copyfileobj(file.file, f)
            members = ingest.expand_zip(zip_path, tempfile.mkdtemp(dir=UPLOAD_ROOT, prefix="zip_"))
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        batch = []
        for name, path in members:
            did = db.add_document(sid, name, path, doc_id=db.new_id())
            try:
                n = rag.index_document(sid, did)
                batch.append({"filename": name, "id": did, "status": "ready", "chunks": n})
            except Exception as e:
                batch.append({"filename": name, "id": did, "status": "error", "error": str(e)[:200]})
        return {"batch": batch}

    did = db.new_id()
    fd, tmp_path = tempfile.mkstemp(dir=UPLOAD_ROOT, suffix=ext)
    with os.fdopen(fd, "wb") as f:
        shutil.copyfileobj(file.file, f)
    db.add_document(sid, display_name, tmp_path, doc_id=did)
    try:
        n = rag.index_document(sid, did)
        return {"id": did, "status": "ready", "chunks": n}
    except Exception as e:
        raise HTTPException(400, f"索引失败: {e}")


@app.delete("/api/spaces/{sid}/documents/{did}")
def api_delete_document(sid: str, did: str):
    """删除知识库文档（含向量、磁盘文件；若为挂载教材则同时解除挂载）。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    doc = db.get_document(did)
    if not doc or doc["space_id"] != sid:
        raise HTTPException(404, "文档不存在")
    db.delete_document(did)
    return {"ok": True}


# ---------- 聊天 ----------

@app.get("/api/spaces/{sid}/messages")
def api_messages(sid: str):
    return db.list_messages(sid)


@app.post("/api/spaces/{sid}/chat")
def api_chat(sid: str, body: ChatIn):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    try:
        reply, citations, expert, user_mid, assistant_mid = experts.answer(
            sid, body.mode, body.message, guide=body.guide)
    except RuntimeError as e:
        # 模型通道不可用与技能/手册端点保持一致：502 + 明确原因，而非裸 500
        raise HTTPException(502, f"模型通道失败: {str(e)[:200]}")
    return {"reply": reply, "citations": citations, "expert": expert,
            "user_message_id": user_mid, "assistant_message_id": assistant_mid}


@app.post("/api/spaces/{sid}/chat/stream")
def api_chat_stream(sid: str, body: ChatIn):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")

    def gen():
        yield "data: " + json.dumps({"type": "meta"}) + "\n\n"
        full = []
        try:
            # 先落库用户提问：模型/检索失败时问题不丢失
            user_mid = db.add_message(sid, body.mode, "user", body.message)
            # 与非流式共用 prompt 组装（专家路由 + 上下文预算 + 记忆注入），避免两条路径行为漂移
            system, _expert_key, hits = experts.build_prompt(sid, body.mode, body.message, guide=body.guide)
            expert_key = _expert_key
            expert_name = experts.EXPERTS.get(expert_key, experts.EXPERTS["qa"])["name"]
            messages = [{"role": "system", "content": system},
                        {"role": "user", "content": body.message}]
            for delta in llm.chat_stream(messages):
                full.append(delta)
                yield "data: " + json.dumps({"type": "delta", "text": delta}, ensure_ascii=False) + "\n\n"
            reply = "".join(full).strip()
            if not reply:
                reply = "（模型未返回有效内容，请重试或在模型设置页检查通道连通性。）"
            citations = [{"index": i + 1, "source": h["source"], "score": round(h["score"], 3),
                          "snippet": h["text"][:120]} for i, h in enumerate(hits)]
            assistant_mid = db.add_message(sid, body.mode, "assistant", reply,
                                           expert=expert_name, citations=citations)
            # 学习分析后台化：done 事件不被 3 次串行 LLM 调用推迟
            experts.maybe_update_memory_async(sid)
            yield "data: " + json.dumps({"type": "done", "expert": expert_name, "citations": citations,
                                         "assistant_message_id": assistant_mid},
                                        ensure_ascii=False) + "\n\n"
        except Exception as e:
            # 明确告知前端失败原因，而不是让流静默断掉（前端显示"正在输入"到天荒地老）
            yield "data: " + json.dumps({"type": "error",
                                         "message": f"生成回答失败：{str(e)[:200]}"},
                                        ensure_ascii=False) + "\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------- 技能 ----------

@app.get("/api/skills")
def api_list_skills():
    return [{"id": k, "name": v["name"]} for k, v in skills.SKILLS.items()]


@app.post("/api/spaces/{sid}/skills")
def api_run_skill(sid: str, body: SkillIn):
    if body.skill not in skills.SKILLS:
        raise HTTPException(404, "技能不存在")
    p = dict(body.params)
    try:
        if body.skill == "quiz.generate":
            return skills.quiz_generate(sid, p.get("topic", ""), int(p.get("count", 5)))
        if body.skill == "quiz.grade":
            return skills.quiz_grade(sid, p["quiz_id"], p["answers"])
        if body.skill == "review.generate":
            return skills.review_generate(sid, int(p.get("count", 5)))
        if body.skill == "note.summarize":
            return {"note": skills.note_summarize(sid, p["document_id"])}
        if body.skill == "plan.study":
            return {"plan": skills.plan_study(sid, p.get("goal", ""))}
        if body.skill == "exam.mock":
            return skills.exam_mock(sid, int(p.get("count", 10)), int(p.get("minutes", 30)))
        if body.skill == "wrong.redo":
            return skills.wrong_redo(sid, p.get("qids") or None)
        if body.skill == "wrong.variants":
            return skills.wrong_variants(sid, p.get("qids") or None)
        if body.skill == "flashcard.generate":
            return skills.flashcard_generate(sid, p.get("topic", ""), int(p.get("count", 10)))
        if body.skill == "teach.check":
            return skills.teach_check(sid, p["topic"], p["explanation"])
        if body.skill == "graph.build":
            return skills.graph_build(sid)
    except (KeyError, ValueError) as e:
        # ValueError 携带具体业务原因（"没有可重做的错题"/"出题结果格式异常"…），直接透传
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        # 模型通道不可用属于上游故障，不要伪装成用户的参数错误
        raise HTTPException(502, f"模型通道失败: {str(e)[:200]}")
    raise HTTPException(400, "未知技能")


# ---------- 用户反馈 / 掌握度 / 复习调度 ----------

@app.post("/api/spaces/{sid}/feedback")
def api_feedback(sid: str, body: FeedbackIn):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    return experts.record_feedback(sid, body.message_id, body.rating, body.understood, body.confusion)


@app.get("/api/spaces/{sid}/mastery")
def api_mastery(sid: str):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    points = db.list_mastery(sid)
    fb = db.list_feedback(sid, 20)
    return {
        "points": points,
        "weak_count": sum(1 for p in points if p["status"] == "weak"),
        "mastered_count": sum(1 for p in points if p["status"] == "mastered"),
        "due": db.due_points(sid),
        "recent_feedback": fb,
    }


@app.get("/api/spaces/{sid}/review/due")
def api_review_due(sid: str):
    due = db.due_points(sid)
    weak = db.weak_points(sid, 5)
    return {"due": due, "weakest": weak}


# ---------- 错题本 ----------

@app.get("/api/spaces/{sid}/wrong-questions")
def api_wrong_questions(sid: str):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    return db.wrong_questions(sid)


@app.post("/api/spaces/{sid}/wrong-questions/redo")
def api_wrong_redo(sid: str, body: RedoIn):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    try:
        return skills.wrong_redo(sid, body.qids or None)[0]
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- 闪卡 ----------

@app.get("/api/spaces/{sid}/flashcards")
def api_flashcards(sid: str, due: int = 0, limit: int = 30):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    return {"cards": db.list_flashcards(sid, due_only=bool(due), limit=limit, with_preview=bool(due)),
            "stats": db.flashcard_stats(sid)}


@app.post("/api/spaces/{sid}/flashcards/{fid}/grade")
def api_flashcard_grade(sid: str, fid: str, body: FlashGradeIn):
    if body.rating is None and body.know is None:
        raise HTTPException(400, "缺少评分：rating(1..4) 或 know(bool)")
    r = db.grade_flashcard(sid, fid, know=body.know, rating=int(body.rating or 0))
    if not r:
        raise HTTPException(404, "闪卡不存在")
    return r


@app.delete("/api/spaces/{sid}/flashcards")
def api_flashcards_clear(sid: str):
    db.clear_flashcards(sid)
    return {"ok": True}


# ---------- 学习计划任务 ----------

@app.get("/api/spaces/{sid}/plan")
def api_plan_tasks(sid: str):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    tasks = db.list_plan_tasks(sid)
    return {"tasks": tasks, "done": sum(1 for t in tasks if t["done"]), "total": len(tasks)}


@app.post("/api/spaces/{sid}/plan/{tid}/toggle")
def api_plan_toggle(sid: str, tid: str, body: ToggleIn):
    r = db.toggle_plan_task(sid, tid, body.done)
    if not r:
        raise HTTPException(404, "任务不存在")
    return r


@app.post("/api/spaces/{sid}/plan/{tid}/date")
def api_plan_set_date(sid: str, tid: str, body: TaskDateIn):
    try:
        r = db.set_plan_task_date(sid, tid, body.due_date)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not r:
        raise HTTPException(404, "任务不存在")
    return r


@app.get("/api/spaces/{sid}/today")
def api_today(sid: str):
    """今日学习视图：到期复习点 + 到期闪卡 + 今日/未排期计划任务 + 今日完成 + 学习速度。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    snap = db.today_snapshot(sid)
    # 附加学习速度与完成预测
    try:
        snap["velocity"] = velocity.compute_velocity(sid)
        snap["forecast"] = velocity.forecast_completion(sid)
    except Exception:
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
        snap["methods"] = None
    try:
        snap["metrics"] = {
            "consistency": study_metrics.consistency(sid),
            "load": study_metrics.daily_load(sid),
            "calibration": study_metrics.calibration(sid),
            "countdown": study_metrics.exam_countdown(sid),
        }
    except Exception:
        snap["metrics"] = None
    return snap


@app.get("/api/spaces/{sid}/velocity")
def api_velocity(sid: str):
    """学习速度 + 完成度预测。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    return {"velocity": velocity.compute_velocity(sid),
            "forecast": velocity.forecast_completion(sid)}


@app.get("/api/spaces/{sid}/daily-question")
def api_daily_question(sid: str):
    """今日一题：ZPD 最优推荐。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    try:
        return skills.daily_question(sid)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, f"模型通道失败: {str(e)[:200]}")


@app.get("/api/transfer-opportunities")
def api_transfer_opportunities():
    """跨空间迁移检测：已掌握概念可加速学习的关联概念。"""
    return velocity.detect_cross_space_transfer()


@app.get("/api/learning-methods")
def api_learning_methods():
    """证据导向学习方法目录。"""
    return {"methods": learning_methods.list_catalog()}


@app.get("/api/spaces/{sid}/methods")
def api_space_methods(sid: str):
    """空间个性化学习方法建议（诊断信号 × 学习者画像 → 方法映射，零 LLM）。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    advice = learning_methods.advise_for_space(sid, limit=5)
    from . import learner_persona
    return {
        "tip": advice.tip,
        "focus": advice.focus,
        "methods": advice.methods,
        "persona": advice.persona,
        "signals": learning_methods.space_signals(sid),
        "inferred": learner_persona.infer_personas(sid),
    }


@app.get("/api/learner-personas")
def api_learner_personas():
    """学习者画像目录。"""
    from . import learner_persona
    return {"personas": learner_persona.list_catalog()}


@app.get("/api/spaces/{sid}/persona")
def api_space_persona(sid: str):
    """当前空间解析出的学习者画像（档案勾选 + 行为推断）。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    from . import learner_persona
    profile = learner_persona.resolve_profile(sid)
    primary = learner_persona.PERSONAS.get(profile.primary)
    return {
        "primary": profile.primary,
        "primary_name": primary.name if primary else "",
        "primary_blurb": primary.blurb if primary else "",
        "primary_tip": primary.tip if primary else "",
        "session": primary.session if primary else "",
        "labels": profile.labels(),
        "explicit": profile.explicit,
        "inferred": profile.inferred,
        "evidence": profile.evidence,
    }


@app.get("/api/spaces/{sid}/metrics")
def api_space_metrics(sid: str):
    """一致性 / 负载 / 校准 / 方法效果 / 考试倒计时。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    return study_metrics.space_metrics(sid)


@app.post("/api/spaces/{sid}/quiz/{qid}/predict")
def api_quiz_predict(sid: str, qid: str, body: dict):
    """交卷前记录自我预测正确率（0~1），用于校准过度/不足自信。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    if "predicted" not in body:
        raise HTTPException(400, "缺少 predicted")
    try:
        return study_metrics.set_quiz_prediction(qid, float(body["predicted"]))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/study-load")
def api_study_load():
    """跨课程今日负载统筹。"""
    return {"spaces": study_metrics.cross_space_load()}


@app.get("/api/spaces/{sid}/mastery/history")
def api_mastery_history(sid: str):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    return db.list_mastery_history(sid)


# ---------- 知识缺陷诊断 / 知识点依赖图 ----------

@app.get("/api/spaces/{sid}/defects")
def api_defects(sid: str):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    return defects.diagnose(sid)


@app.get("/api/spaces/{sid}/graph")
def api_graph(sid: str):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    edges = db.list_edges(sid)
    # 节点 = 掌握度表中的知识点 ∪ 依赖边上的知识点（后者可能尚未有掌握度记录）
    by_name: dict = {}
    for p in db.list_mastery(sid):
        by_name[p["point"]] = p
    for e in edges:
        for n in (e["from_point"], e["to_point"]):
            by_name.setdefault(n, None)
    nodes = []
    for name, p in by_name.items():
        nodes.append({
            "point": name,
            "p_known": round(p["score"], 3) if p else None,
            "status": p["status"] if p else "unknown",
            "attempts": p["attempts"] if p else 0,
            "correct": p["correct"] if p else 0,
            "wrong": p["wrong"] if p else 0,
        })
    return {"nodes": nodes, "edges": edges}


@app.get("/api/curriculum")
def api_curriculums():
    return defects.list_curriculums()


# ---------- 一键导出 ----------

@app.get("/api/spaces/{sid}/export")
def api_export(sid: str, kind: str = "report"):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    fn = export.EXPORTS.get(kind)
    if not fn:
        raise HTTPException(400, "kind 必须是 report / wrong / plan")
    from urllib.parse import quote
    md = fn(sid)
    fname = quote(f"studypilot-{kind}.md")
    return PlainTextResponse(
        md, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"})


# ---------- 成长手册 ----------

@app.post("/api/handbook/generate")
def api_handbook_generate(body: HandbookIn):
    try:
        return handbook.generate(body.space_id, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"手册生成失败（检查模型通道）：{str(e)[:200]}")


@app.get("/api/competitions/catalog")
def api_competition_catalog():
    """内置竞赛目录：级别 / 窗口 / 备赛周期 / 专业匹配 / 各路径价值。"""
    return competitions.catalog()


@app.post("/api/competitions/analyze")
def api_competition_analyze(body: CompetitionIn):
    """目标导向竞赛分析：至少参加哪些（分级推荐）+ 可选 LLM 备赛策略。"""
    try:
        return competitions.analyze(body.model_dump(), goal=body.goal, use_llm=body.use_llm)
    except Exception as e:
        raise HTTPException(502, f"竞赛分析失败：{str(e)[:200]}")


@app.get("/api/handbook")
def api_handbook_list():
    return handbook.list_handbooks()


@app.get("/api/handbook/{hid}")
def api_handbook_get(hid: str):
    h = handbook.get_handbook(hid)
    if not h:
        raise HTTPException(404, "手册不存在")
    return h


@app.delete("/api/handbook/{hid}")
def api_handbook_delete(hid: str):
    handbook.delete_handbook(hid)
    return {"ok": True}


# ---------- 学涯规划：培养方案 / 课程表 / 目标计划 ----------

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


@app.get("/api/syllabus/stats")
def api_syllabus_stats():
    return syllabus.stats()


@app.get("/api/syllabus/official")
def api_syllabus_official():
    """已收录官方全文的学校专业清单。"""
    return syllabus.official_sources()


@app.get("/api/syllabus/fulltext")
def api_syllabus_fulltext(school: str = "", major: str = ""):
    ft = syllabus.full_text(school, major)
    if not ft:
        raise HTTPException(404, "该学校专业暂未收录官方培养方案全文")
    return ft


@app.get("/api/syllabus/schools")
def api_syllabus_schools(q: str = "", region: str = "", tier: str = ""):
    return syllabus.list_schools(q, region, tier)


@app.get("/api/syllabus/majors")
def api_syllabus_majors(school: str = ""):
    return syllabus.majors_for_school(school)


@app.get("/api/syllabus/program")
def api_syllabus_program(school: str = "", major: str = ""):
    return syllabus.program(school, major)


@app.post("/api/syllabus/import")
def api_syllabus_import_text(body: SyllabusImportIn):
    try:
        return syllabus.import_handbook(body.school, body.major, body.text, source="粘贴文本")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, f"培养方案抽取失败（检查模型通道）：{str(e)[:200]}")


@app.post("/api/syllabus/import/file")
def api_syllabus_import_file(school: str, major: str = "", file: UploadFile = File(...)):
    display_name = (file.filename or "未命名").replace("\\", "/").rsplit("/", 1)[-1] or "未命名"
    ext = ingest.ext_of(display_name)
    if ext not in ingest.UPLOAD_EXTS:
        raise HTTPException(400, "支持 PDF / TXT / Markdown / 图片（会 OCR）")
    fd, tmp_path = tempfile.mkstemp(dir=UPLOAD_ROOT, suffix=ext)
    with os.fdopen(fd, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        text = rag.parse_file(tmp_path, display_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    try:
        return syllabus.import_handbook(school, major, text, source=display_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, f"培养方案抽取失败（检查模型通道）：{str(e)[:200]}")


@app.get("/api/schedule")
def api_schedule(term: str = ""):
    terms = db.list_schedule_terms()
    if not term:
        term = terms[0]["term"] if terms else ""
    return {"term": term, "terms": terms, "courses": db.list_schedule(term)}


@app.post("/api/schedule/import")
def api_schedule_import_text(body: ScheduleTextIn):
    try:
        return schedule.import_from_text(body.text)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/schedule/import/file")
def api_schedule_import_file(file: UploadFile = File(...)):
    display_name = (file.filename or "未命名").replace("\\", "/").rsplit("/", 1)[-1] or "未命名"
    ext = ingest.ext_of(display_name)
    if ext not in ingest.IMAGE_EXTS + (".xlsx", ".csv", ".json", ".txt", ".md", ".markdown"):
        raise HTTPException(400, "课程表支持：截图(png/jpg/webp/bmp) / Excel(.xlsx) / CSV / JSON(WakeUp) / 文本")
    fd, tmp_path = tempfile.mkstemp(dir=UPLOAD_ROOT, suffix=ext)
    with os.fdopen(fd, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        return schedule.import_from_file(tmp_path, display_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@app.put("/api/schedule")
def api_schedule_save(body: ScheduleSaveIn):
    try:
        n = schedule.save(body.term, body.courses)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"term": body.term, "saved": n, "courses": db.list_schedule(body.term)}


@app.delete("/api/schedule")
def api_schedule_delete(term: str):
    db.delete_schedule(term)
    return {"ok": True}


@app.get("/api/planner")
def api_planner_list():
    return db.list_career_plans()


@app.post("/api/planner/generate")
def api_planner_generate(body: PlannerIn):
    try:
        return planner.generate(body.school, body.major, body.year, body.goal_type,
                                body.target, body.term, body.horizon, body.space_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, f"计划生成失败（检查模型通道）：{str(e)[:200]}")


@app.get("/api/planner/{pid}")
def api_planner_get(pid: str):
    p = planner.get_plan(pid)
    if not p:
        raise HTTPException(404, "计划不存在")
    return p


@app.post("/api/planner/{pid}/toggle")
def api_planner_toggle(pid: str, body: PlanToggleIn):
    r = planner.toggle_task(pid, body.task_id, body.done)
    if not r:
        raise HTTPException(404, "任务不存在")
    return r


@app.post("/api/planner/{pid}/push")
def api_planner_push(pid: str, body: PlanPushIn):
    try:
        return planner.push_to_space(pid, body.space_id, body.replace)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/planner/{pid}")
def api_planner_delete(pid: str):
    r = planner.delete_plan(pid)
    return {"ok": True, "removed_pushed_tasks": r.get("deleted_pushed_tasks", 0)}


# ---------- LLM 通道配置（本地 / 云端） ----------

@app.get("/api/llm/config")
def api_llm_config():
    return llm.get_status()


@app.put("/api/llm/config")
def api_llm_update(body: LlmConfigIn):
    try:
        llm.update_runtime_config(routing=body.routing, cloud_base_url=body.cloud_base_url,
                                  cloud_api_key=body.cloud_api_key, cloud_model=body.cloud_model)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return llm.get_status()


@app.post("/api/llm/test")
def api_llm_test():
    """实测两个通道：各发一条极短补全，报告连通性与延迟。"""
    return {
        "local": llm.probe_latency("local"),
        "cloud": llm.probe_latency("cloud") if llm._cloud_profile()
                 else {"ok": False, "error": "未配置"},
    }


@app.get("/api/llm/stats")
def api_llm_stats(hours: int = 24):
    """最近 N 小时的 LLM 调用统计：按通道/任务的延迟分布与成功率。"""
    from . import llm_stats
    return {
        "summary": llm_stats.summary(hours=hours),
        "health": llm_stats.channel_health(),
        "task_routing": {k: v["priority"] for k, v in llm.TASK_ROUTING.items()},
    }


@app.get("/api/llm/usage")
def api_llm_usage(days: int = 30):
    """用量仪表盘：按天/通道/任务/模型聚合 Token 与调用次数。"""
    from . import llm_stats
    return llm_stats.usage_dashboard(days=max(1, min(days, 90)))


@app.post("/api/llm/stats/clear")
def api_llm_stats_clear():
    from . import llm_stats
    llm_stats.clear_history()
    return {"ok": True}


@app.get("/api/spaces/{sid}/quizzes")
def api_quizzes(sid: str):
    return db.list_quizzes(sid)


# ---------- 记忆 ----------

@app.get("/api/spaces/{sid}/memory")
def api_memory(sid: str):
    m = db.list_memory(sid)
    return {
        "l1_count": len(db.list_messages(sid, 20)),
        "l2": [x for x in m if x["level"] == 2],
        "l3": [x for x in m if x["level"] == 3],
    }


@app.delete("/api/spaces/{sid}/memory/{level}")
def api_clear_memory(sid: str, level: int):
    db.clear_memory(sid, level)
    return {"ok": True}


# ---------- 专家 / 连接器 ----------

@app.get("/api/experts")
def api_experts():
    return [{"id": k, **{kk: vv for kk, vv in v.items() if kk != "system"}} for k, v in experts.EXPERTS.items()]


@app.get("/api/connectors")
def api_connectors():
    return connectors.list_connectors()


@app.post("/api/connectors/mcp")
def api_register_mcp(body: McpIn):
    try:
        connectors.register_mcp(body.name, body.command)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/api/connectors/mcp/{name}")
def api_remove_mcp(name: str):
    if not connectors.remove_mcp(name):
        raise HTTPException(404, "未注册的 MCP server")
    return {"ok": True}


# ---------- 启动迁移 ----------

@app.on_event("startup")
def _startup_migrations():
    note_review.ensure_doc_fsrs_columns()


# ---------- Anki 导入导出 ----------

@app.post("/api/spaces/{sid}/anki/import")
async def api_anki_import(sid: str, file: UploadFile = File(...)):
    """导入 .apkg 牌组到指定空间。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    if not file.filename or not file.filename.endswith(".apkg"):
        raise HTTPException(400, "请上传 .apkg 文件")
    data = await file.read()
    if len(data) > 100 * 1024 * 1024:  # 100MB 上限
        raise HTTPException(400, "文件过大（上限 100MB）")
    result = anki_io.import_apkg(data, sid)
    return result


@app.get("/api/spaces/{sid}/anki/export")
def api_anki_export(sid: str):
    """导出空间闪卡为 .apkg。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    data = anki_io.export_apkg(sid)
    space = db.get_space(sid)
    fname = f"StudyPilot_{space['name'] if space else sid}.apkg"
    # HTTP 头只能 latin-1：中文空间名走 RFC 5987 filename*，ASCII 名走普通 filename
    quoted = urllib.parse.quote(fname, safe="")
    from fastapi.responses import Response
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename=\"deck.apkg\"; filename*=UTF-8''{quoted}"},
    )


# ---------- 讲义笔记级 FSRS 复习 ----------

@app.get("/api/spaces/{sid}/doc-reviews/due")
def api_due_doc_reviews(sid: str):
    """列出到期需要复习的讲义文档。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    return note_review.list_due_doc_reviews(sid)


@app.post("/api/spaces/{sid}/doc-reviews/{did}/grade")
def api_grade_doc_review(sid: str, did: str, body: dict):
    """对讲义做 FSRS 复习评分。body: {"rating": 1..4}"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    rating = body.get("rating", 3)
    if rating not in (1, 2, 3, 4):
        raise HTTPException(400, "rating 必须是 1(忘了)/2(困难)/3(良好)/4(轻松)")
    result = note_review.schedule_doc_review(did, rating)
    if not result:
        raise HTTPException(404, "文档不存在")
    return result


@app.get("/api/spaces/{sid}/doc-reviews/{did}/preview")
def api_preview_doc_review(sid: str, did: str):
    """预览四档评分的下次间隔。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    result = note_review.doc_review_preview(did)
    if not result:
        raise HTTPException(404, "文档不存在")
    return result


# ---------- BKT 参数个性化拟合 ----------

@app.post("/api/spaces/{sid}/bkt/fit")
def api_bkt_fit(sid: str):
    """对空间内有足够答题记录的知识点做 Baum-Welch EM 个性化拟合。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    fitted = bkt_fit.fit_for_space(sid)
    return {"fitted_count": len(fitted), "params": fitted}


@app.get("/api/spaces/{sid}/bkt/params")
def api_bkt_params(sid: str):
    """查看当前使用的 BKT 参数（个性化或默认）。"""
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    mastery_list = db.list_mastery(sid)
    result = {}
    for m in mastery_list[:50]:
        result[m["point"]] = bkt_fit.get_params(sid, m["point"])
    return result


# ---------- 桌面模式：托管前端构建产物（SPA） ----------

from fastapi.staticfiles import StaticFiles  # noqa: E402

FRONTEND_DIST = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="spa")
