"""技能执行（同步 + SSE 流式）与题库查询。"""
import json
import queue
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db, skills, visual

router = APIRouter()


class SkillIn(BaseModel):
    skill: str
    params: dict = {}


@router.get("/api/skills")
def api_list_skills():
    return [{"id": k, "name": v["name"]} for k, v in skills.SKILLS.items()]


@router.post("/api/spaces/{sid}/skills")
def api_run_skill(sid: str, body: SkillIn):
    if body.skill not in skills.SKILLS:
        raise HTTPException(404, "技能不存在")
    p = dict(body.params)
    try:
        return dispatch_skill(body.skill, sid, p)
    except (KeyError, ValueError) as e:
        # ValueError 携带具体业务原因（"没有可重做的错题"/"出题结果格式异常"…），直接透传
        raise HTTPException(400, str(e)) from e
    except RuntimeError as e:
        # 模型通道不可用属于上游故障，不要伪装成用户的参数错误
        raise HTTPException(502, f"模型通道失败: {str(e)[:200]}") from e


def dispatch_skill(skill: str, sid: str, p: dict, progress=None):
    """技能分发（同步端点与 SSE 流式端点共用）；progress 仅由流式端点注入。"""
    def _count(default: int) -> int:
        # 数量钳制：过大的 count 会让出题 prompt 超出 max_tokens 直接报废，过小/负数无意义
        return max(1, min(int(p.get("count", default) or default), 20))

    if skill == "quiz.generate":
        return skills.quiz_generate(sid, p.get("topic", ""), _count(5), progress=progress)
    if skill == "quiz.grade":
        return skills.quiz_grade(sid, p["quiz_id"], p["answers"])
    if skill == "review.generate":
        return skills.review_generate(sid, _count(5), progress=progress)
    if skill == "note.summarize":
        return {"note": skills.note_summarize(sid, p["document_id"])}
    if skill == "plan.study":
        return {"plan": skills.plan_study(sid, p.get("goal", ""), progress=progress)}
    if skill == "exam.mock":
        return skills.exam_mock(sid, _count(10), int(p.get("minutes", 30)), progress=progress)
    if skill == "wrong.redo":
        return skills.wrong_redo(sid, p.get("qids") or None)
    if skill == "wrong.variants":
        return skills.wrong_variants(sid, p.get("qids") or None)
    if skill == "flashcard.generate":
        return skills.flashcard_generate(sid, p.get("topic", ""), _count(10), progress=progress)
    if skill == "teach.check":
        return skills.teach_check(sid, p["topic"], p["explanation"])
    if skill == "graph.build":
        return skills.graph_build(sid, progress=progress)
    if skill == "daily.question":
        # 此前 SKILLS 目录广播了 12 个技能、分发器只认 11 个，通用端点调用必 400
        return skills.daily_question(sid)
    if skill == "concept.visualize":
        return visual.concept_visualize(sid, p.get("topic", ""), progress=progress)
    raise KeyError(skill)


@router.post("/api/spaces/{sid}/skills/stream")
async def api_run_skill_stream(sid: str, body: SkillIn):
    """SSE 版技能执行：worker 线程跑技能，把阶段进度（检索/生成/入库）实时推给前端。
    客户端中途断开时 worker 仍会执行完毕并入库——重新进页面即可看到结果，与同步版一致。"""
    if body.skill not in skills.SKILLS:
        raise HTTPException(404, "技能不存在")
    q: queue.Queue[tuple[str, object]] = queue.Queue()

    def progress(label: str):
        q.put(("phase", label))

    def worker():
        try:
            q.put(("done", dispatch_skill(body.skill, sid, dict(body.params), progress)))
        except (KeyError, ValueError) as e:
            q.put(("error", str(e)))
        except RuntimeError as e:
            q.put(("error", f"模型通道失败: {str(e)[:200]}"))
        except Exception as e:  # 兜底：任何异常都要终结 SSE 流，不能让前端干等
            q.put(("error", str(e)))

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        yield f"data: {json.dumps({'type': 'start', 'skill': body.skill}, ensure_ascii=False)}\n\n"
        while True:
            try:
                kind, payload = q.get(timeout=15)
            except queue.Empty:
                yield ": ping\n\n"  # SSE 心跳注释：长任务期间保持连接不被中间层掐断
                continue
            if kind == "phase":
                yield f"data: {json.dumps({'type': 'phase', 'label': payload}, ensure_ascii=False)}\n\n"
            elif kind == "done":
                yield f"data: {json.dumps({'type': 'done', 'result': payload}, ensure_ascii=False, default=str)}\n\n"
                return
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': payload}, ensure_ascii=False)}\n\n"
                return

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/api/spaces/{sid}/quizzes")
def api_quizzes(sid: str):
    # 出口统一补齐缺省字段（题库旧行可能缺 options），并剥掉标准答案
    quizzes = db.list_quizzes(sid)
    for q in quizzes:
        q["questions"] = skills._public_questions(q.get("questions") or [])
    return quizzes


# ---------- 概念可视化存档 ----------

@router.get("/api/spaces/{sid}/visuals")
def api_list_visuals(sid: str):
    return db.list_visuals(sid)


@router.get("/api/spaces/{sid}/visuals/{vid}")
def api_get_visual(sid: str, vid: str):
    """可视化详情：按当前模板版本从规格实时渲染 HTML（库里只存小规格，
    模板升级后旧存档也能吃到新样式）。"""
    v = db.get_visual(vid)
    if not v or v["space_id"] != sid:
        raise HTTPException(404, "可视化存档不存在")
    try:
        v["html"] = visual.render_visual_html(v["spec"])
    except Exception:
        # 规格意外损坏时不让详情页 500：给一个可读的错误页
        v["html"] = ("<html><body><p>该存档的规格数据损坏，无法渲染。"
                     "</p><p>建议删除后重新生成。</p></body></html>")
    return v


@router.delete("/api/spaces/{sid}/visuals/{vid}")
def api_delete_visual(sid: str, vid: str):
    v = db.get_visual(vid)
    if not v or v["space_id"] != sid:
        raise HTTPException(404, "可视化存档不存在")
    db.delete_visual(vid)
    return {"ok": True}
