"""FastAPI 入口：REST API。"""
import json
import os
import pathlib
import shutil
import tempfile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import connectors, db, experts, llm, rag, skills
from .config import settings

app = FastAPI(title="StudyPilot", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UPLOAD_ROOT = pathlib.Path(settings.upload_dir).resolve()


class SpaceIn(BaseModel):
    name: str
    description: str = ""


class ChatIn(BaseModel):
    mode: str = "ask"       # ask / plan / craft
    message: str


class SkillIn(BaseModel):
    skill: str
    params: dict = {}


class McpIn(BaseModel):
    name: str
    command: list[str]


@app.get("/api/health")
def health():
    try:
        models = llm._get_client().get("/models").json()
        llm_ok = True
    except Exception as e:
        models = {"error": str(e)[:200]}
        llm_ok = False
    return {"status": "ok", "llm": llm_ok, "model": settings.llm_model, "models": models}


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
    low = display_name.lower()
    if low.endswith(".pdf"):
        suffix = ".pdf"
    elif low.endswith((".md", ".markdown")):
        suffix = ".md"
    elif low.endswith(".txt"):
        suffix = ".txt"
    else:
        raise HTTPException(400, "仅支持 PDF / TXT / Markdown 文件")
    did = db.new_id()
    fd, tmp_path = tempfile.mkstemp(dir=UPLOAD_ROOT, suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        shutil.copyfileobj(file.file, f)
    db.add_document(sid, display_name, tmp_path, doc_id=did)
    try:
        n = rag.index_document(sid, did)
        return {"id": did, "status": "ready", "chunks": n}
    except Exception as e:
        raise HTTPException(400, f"索引失败: {e}")


# ---------- 聊天 ----------

@app.get("/api/spaces/{sid}/messages")
def api_messages(sid: str):
    return db.list_messages(sid)


@app.post("/api/spaces/{sid}/chat")
def api_chat(sid: str, body: ChatIn):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")
    reply, citations, expert = experts.answer(sid, body.mode, body.message)
    return {"reply": reply, "citations": citations, "expert": expert}


@app.post("/api/spaces/{sid}/chat/stream")
def api_chat_stream(sid: str, body: ChatIn):
    if not db.get_space(sid):
        raise HTTPException(404, "空间不存在")

    def gen():
        yield "data: " + json.dumps({"type": "meta"}) + "\n\n"
        full = []
        expert_key = "qa" if body.mode != "ask" else experts.route_expert(body.message)
        expert_name = experts.EXPERTS.get(expert_key, experts.EXPERTS["qa"])["name"]
        hits = rag.retrieve(sid, body.message)
        context = rag.build_context(hits) if hits else "（知识库暂无相关内容）"
        memory_ctx = experts.build_memory_context(sid)
        system = experts.MODE_SYSTEM.get(body.mode, experts.MODE_SYSTEM["ask"])
        if memory_ctx:
            system += "\n\n学生记忆档案：\n" + memory_ctx
        messages = [{"role": "system", "content": system + f"\n\n【讲义检索片段】\n{context}"},
                    {"role": "user", "content": body.message}]
        for delta in llm.chat_stream(messages):
            full.append(delta)
            yield "data: " + json.dumps({"type": "delta", "text": delta}, ensure_ascii=False) + "\n\n"
        reply = "".join(full).strip()
        citations = [{"index": i + 1, "source": h["source"], "score": round(h["score"], 3),
                      "snippet": h["text"][:120]} for i, h in enumerate(hits)]
        db.add_message(sid, body.mode, "user", body.message)
        db.add_message(sid, body.mode, "assistant", reply, expert=expert_name, citations=citations)
        experts.maybe_update_memory(sid)
        yield "data: " + json.dumps({"type": "done", "expert": expert_name, "citations": citations},
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
        if body.skill == "note.summarize":
            return {"note": skills.note_summarize(sid, p["document_id"])}
        if body.skill == "plan.study":
            return {"plan": skills.plan_study(sid, p.get("goal", ""))}
    except (KeyError, ValueError) as e:
        raise HTTPException(400, f"参数错误: {e}")
    raise HTTPException(400, "未知技能")


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
    connectors.register_mcp(body.name, body.command)
    return {"ok": True}


# ---------- 桌面模式：托管前端构建产物（SPA） ----------

from fastapi.staticfiles import StaticFiles  # noqa: E402

FRONTEND_DIST = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="spa")
