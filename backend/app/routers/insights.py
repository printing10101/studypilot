"""学习分析洞察：缺陷诊断、依赖图谱、学习方法、画像、指标、校准、报告导出。"""
import urllib.parse

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from .. import db, defects, export, learner_persona, learning_methods, study_metrics, velocity
from .common import space_or_404

router = APIRouter()


class PredictIn(BaseModel):
    predicted: float        # 0~1，交卷前自我预测正确率


@router.get("/api/spaces/{sid}/defects")
def api_defects(sid: str):
    space_or_404(sid)
    return defects.diagnose(sid)


@router.get("/api/spaces/{sid}/graph")
def api_graph(sid: str):
    space_or_404(sid)
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


@router.get("/api/curriculum")
def api_curriculums():
    return defects.list_curriculums()


@router.get("/api/transfer-opportunities")
def api_transfer_opportunities():
    """跨空间迁移检测：已掌握概念可加速学习的关联概念。"""
    return velocity.detect_cross_space_transfer()


@router.get("/api/learning-methods")
def api_learning_methods():
    """证据导向学习方法目录。"""
    return {"methods": learning_methods.list_catalog()}


@router.get("/api/spaces/{sid}/methods")
def api_space_methods(sid: str):
    """空间个性化学习方法建议（诊断信号 × 学习者画像 → 方法映射，零 LLM）。"""
    space_or_404(sid)
    advice = learning_methods.advise_for_space(sid, limit=5)
    return {
        "tip": advice.tip,
        "focus": advice.focus,
        "methods": advice.methods,
        "persona": advice.persona,
        "signals": learning_methods.space_signals(sid),
        "inferred": learner_persona.infer_personas(sid),
    }


@router.get("/api/learner-personas")
def api_learner_personas():
    """学习者画像目录。"""
    return {"personas": learner_persona.list_catalog()}


@router.get("/api/spaces/{sid}/persona")
def api_space_persona(sid: str):
    """当前空间解析出的学习者画像（档案勾选 + 行为推断）。"""
    space_or_404(sid)
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


@router.get("/api/spaces/{sid}/metrics")
def api_space_metrics(sid: str):
    """一致性 / 负载 / 校准 / 方法效果 / 考试倒计时。"""
    space_or_404(sid)
    return study_metrics.space_metrics(sid)


@router.post("/api/spaces/{sid}/quiz/{qid}/predict")
def api_quiz_predict(sid: str, qid: str, body: PredictIn):
    """交卷前记录自我预测正确率（0~1），用于校准过度/不足自信。"""
    space_or_404(sid)
    try:
        return study_metrics.set_quiz_prediction(qid, body.predicted)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/api/study-load")
def api_study_load():
    """跨课程今日负载统筹。"""
    return {"spaces": study_metrics.cross_space_load()}


# ---------- 一键导出 ----------

@router.get("/api/spaces/{sid}/export")
def api_export(sid: str, kind: str = "report"):
    space_or_404(sid)
    fn = export.EXPORTS.get(kind)
    if not fn:
        raise HTTPException(400, "kind 必须是 report / wrong / plan")
    md = fn(sid)
    fname = urllib.parse.quote(f"studypilot-{kind}.md")
    return PlainTextResponse(
        md, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"})
