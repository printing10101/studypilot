"""聊天（Ask/Plan/Craft，同步 + SSE 流式）、消息、用户反馈、三层记忆。"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .. import db, experts, llm
from .common import space_or_404

router = APIRouter()


class ChatIn(BaseModel):
    mode: str = "ask"       # ask / plan / craft
    message: str
    guide: bool = False     # 苏格拉底引导模式（Ask）：先提示思路，不直接给答案


class FeedbackIn(BaseModel):
    message_id: str = ""
    rating: str = ""          # helpful / unhelpful
    understood: int = -1      # 1 听懂 / 0 没听懂
    confusion: str = ""       # 哪里没懂的补充说明


@router.get("/api/spaces/{sid}/messages")
def api_messages(sid: str, limit: int = 200, before: float | None = None):
    # 分页：默认取最近 limit 条；before=更早一批的最后一条时间戳，供「加载更早消息」
    messages, has_more = db.list_messages_paged(sid, limit=min(max(limit, 1), 500), before_ts=before)
    return {"messages": messages, "has_more": has_more}


@router.post("/api/spaces/{sid}/chat")
def api_chat(sid: str, body: ChatIn):
    space_or_404(sid)
    try:
        reply, citations, expert, user_mid, assistant_mid = experts.answer(
            sid, body.mode, body.message, guide=body.guide)
    except RuntimeError as e:
        # 模型通道不可用与技能/手册端点保持一致：502 + 明确原因，而非裸 500
        raise HTTPException(502, f"模型通道失败: {str(e)[:200]}") from e
    return {"reply": reply, "citations": citations, "expert": expert,
            "user_message_id": user_mid, "assistant_message_id": assistant_mid}


@router.post("/api/spaces/{sid}/chat/stream")
def api_chat_stream(sid: str, body: ChatIn):
    space_or_404(sid)

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
            # user_message_id 与非流式响应契约对齐：前端要靠它挂反馈/引用
            yield "data: " + json.dumps({"type": "done", "expert": expert_name, "citations": citations,
                                         "assistant_message_id": assistant_mid,
                                         "user_message_id": user_mid},
                                        ensure_ascii=False) + "\n\n"
        except Exception as e:
            # 明确告知前端失败原因，而不是让流静默断掉（前端显示"正在输入"到天荒地老）
            yield "data: " + json.dumps({"type": "error",
                                         "message": f"生成回答失败：{str(e)[:200]}"},
                                        ensure_ascii=False) + "\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/api/spaces/{sid}/feedback")
def api_feedback(sid: str, body: FeedbackIn):
    space_or_404(sid)
    return experts.record_feedback(sid, body.message_id, body.rating, body.understood, body.confusion)


# ---------- 记忆 ----------

@router.get("/api/spaces/{sid}/memory")
def api_memory(sid: str):
    m = db.list_memory(sid)
    return {
        "l1_count": len(db.list_messages(sid, 20)),
        "l2": [x for x in m if x["level"] == 2],
        "l3": [x for x in m if x["level"] == 3],
    }


@router.delete("/api/spaces/{sid}/memory/{level}")
def api_clear_memory(sid: str, level: int):
    db.clear_memory(sid, level)
    return {"ok": True}
