"""专家团 + 三层记忆（L1 镜像 / L2 摘要 / L3 长期综合）+ 模式(Ask/Plan/Craft)编排。"""
import json

from . import db, llm, rag

# ---------- 专家团（WorkBuddy: 专家 agents） ----------

EXPERTS = {
    "qa": {
        "name": "讲义答疑专家",
        "description": "基于课程讲义精准答疑，回答附引用来源",
        "system": "你是严谨的课程助教。只依据提供的讲义片段回答问题；片段中没有的内容要明确说明讲义未覆盖，不要编造。回答用中文，关键结论给出来源片段编号，如 [片段2]。",
    },
    "examiner": {
        "name": "出题官",
        "description": "根据讲义出测试题，考察理解而非背诵",
        "system": "你是资深的课程出题官。依据讲义片段出题，覆盖不同难度，注重概念理解与应用。输出严格 JSON，不要多余文字。",
    },
    "grader": {
        "name": "判卷助教",
        "description": "逐题判卷、给出错误原因分析",
        "system": "你是耐心的判卷助教。逐题判断学生答案是否正确（概念近似正确算对），对错误给出根因分析和正确思路。输出严格 JSON，不要多余文字。",
    },
    "planner": {
        "name": "学习规划师",
        "description": "结合掌握状态生成学习计划",
        "system": "你是学习规划师。根据学生的记忆档案（薄弱点、易错点）和讲义目录，给出可执行的分阶段学习计划，具体到知识点和练习方式。用 Markdown 输出。",
    },
}

MODE_SYSTEM = {
    "ask": EXPERTS["qa"]["system"],
    "plan": EXPERTS["planner"]["system"],
    "craft": "你是学习产出助手，帮学生把讲义内容整理成结构化笔记、错题本或总结，用 Markdown 输出，重要概念加粗，附来源片段编号。",
}


def route_expert(question: str) -> str:
    """简单路由：根据问题特征选择专家（WorkBuddy 式任务分派的最小实现）。"""
    if any(k in question for k in ("出题", "考考我", "测试", "练习题")):
        return "examiner"
    if any(k in question for k in ("计划", "规划", "怎么学", "安排")):
        return "planner"
    return "qa"


def build_memory_context(space_id: str) -> str:
    l2 = db.latest_l2(space_id)
    l3 = db.list_memory(space_id, level=3)
    parts = []
    if l2:
        parts.append(f"【近期学习摘要】{l2}")
    if l3:
        lines = [f"- ({m['kind']}) {m['content']}" for m in l3[-30:]]
        parts.append("【长期记忆档案】\n" + "\n".join(lines))
    return "\n".join(parts)


def _l1_block(space_id: str) -> str:
    msgs = db.recent_messages(space_id, 12)
    return "\n".join(f"{m['role']}: {m['content'][:300]}" for m in msgs)


# ---------- 聊天（Ask/Plan/Craft 共用，RAG + 记忆注入） ----------

def answer(space_id: str, mode: str, question: str) -> tuple[str, list[dict], str]:
    """返回 (回答, 引用, 专家名)。"""
    expert_key = "qa" if mode != "ask" else route_expert(question)
    expert_name = EXPERTS.get(expert_key, EXPERTS["qa"])["name"]

    hits = rag.retrieve(space_id, question)
    context = rag.build_context(hits) if hits else "（知识库暂无相关内容，可提示用户先上传讲义）"
    memory_ctx = build_memory_context(space_id)

    system = MODE_SYSTEM.get(mode, MODE_SYSTEM["ask"])
    if memory_ctx:
        system += "\n\n以下是该学生的记忆档案，回答时结合其薄弱点个性化作答：\n" + memory_ctx

    messages = [
        {"role": "system", "content": system + f"\n\n【讲义检索片段】\n{context}"},
        {"role": "user", "content": question},
    ]
    reply = llm.chat(messages)

    citations = [{"index": i + 1, "source": h["source"], "score": round(h["score"], 3),
                  "snippet": h["text"][:120]} for i, h in enumerate(hits)]

    db.add_message(space_id, mode, "user", question)
    db.add_message(space_id, mode, "assistant", reply, expert=expert_name, citations=citations)
    maybe_update_memory(space_id)
    return reply, citations, expert_name


# ---------- 三层记忆 ----------

def maybe_update_memory(space_id: str, every_n_msgs: int = 8) -> None:
    """消息数达到阈值时：L1 镜像已在库里；压缩为 L2 摘要并沉淀 L3。"""
    c = db.get_conn()
    n = c.execute("SELECT COUNT(*) AS n FROM messages WHERE space_id=?", (space_id,)).fetchone()["n"]
    if n == 0 or n % every_n_msgs != 0:
        return
    l1 = _l1_block(space_id)
    if not l1:
        return
    summary = llm.chat([
        {"role": "system", "content": "把以下学习对话压缩成不超过200字的中文事实摘要，只保留知识点、易错点、学习进度。直接输出摘要。"},
        {"role": "user", "content": l1},
    ], temperature=0.2)
    db.clear_memory(space_id, level=2)
    db.add_memory(space_id, 2, summary, kind="summary")

    l3_raw = llm.chat([
        {"role": "system", "content": (
            "根据摘要和历史档案，提取学生当前的知识点掌握状态变化。"
            "输出严格 JSON 数组，每项 {\"kind\":\"mastery|weakness|error\",\"content\":\"...\"}，最多5条，不要多余文字。")},
        {"role": "user", "content": f"近期摘要：{summary}\n现有档案：{json.dumps(db.list_memory(space_id, 3), ensure_ascii=False)}"},
    ], temperature=0.2)
    try:
        text = l3_raw[l3_raw.find("["): l3_raw.rfind("]") + 1]
        for item in json.loads(text):
            db.add_memory(space_id, 3, item.get("content", ""), kind=item.get("kind", ""))
    except (ValueError, json.JSONDecodeError):
        pass
