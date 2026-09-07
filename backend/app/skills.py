"""技能系统（WorkBuddy: Skills）：出题 / 判卷 / 总结 / 学习计划。"""
import json

from . import db, experts, llm, rag


# ---------- quiz.generate ----------

def quiz_generate(space_id: str, topic: str, count: int = 5) -> list[dict]:
    hits = rag.retrieve(space_id, topic or "课程核心概念", top_k=8)
    context = rag.build_context(hits) if hits else "（无讲义片段，按通识出题）"
    raw = llm.chat([
        {"role": "system", "content": experts.EXPERTS["examiner"]["system"]},
        {"role": "user", "content": (
            f"围绕「{topic or '本课程重点'}」出 {count} 道题（判断/选择/简答混合）。"
            f"输出 JSON 数组：[{{\"id\":\"q1\",\"type\":\"判断|选择|简答\",\"question\":\"...\","
            f"\"options\":[\"A...\",\"B...\",\"C...\",\"D...\"],\"answer\":\"...\",\"knowledge_point\":\"...\"}}]。"
            f"判断/简答题 options 为空数组。\n\n讲义片段：\n{context}")},
    ], temperature=0.5)
    questions = json.loads(raw[raw.find("["): raw.rfind("]") + 1])
    qid = db.save_quiz(space_id, topic, questions)
    return [{"quiz_id": qid, "questions": questions}]


# ---------- quiz.grade ----------

def quiz_grade(space_id: str, quiz_id: str, answers: list[dict]) -> dict:
    quizzes = {q["id"]: q for q in db.list_quizzes(space_id)}
    quiz = quizzes.get(quiz_id)
    if not quiz:
        raise ValueError("测验不存在")
    questions = {q["id"]: q for q in quiz["questions"]}
    raw = llm.chat([
        {"role": "system", "content": experts.EXPERTS["grader"]["system"]},
        {"role": "user", "content": (
            "题目与标准答案：" + json.dumps(quiz["questions"], ensure_ascii=False) +
            "\n学生答案：" + json.dumps(answers, ensure_ascii=False) +
            "\n输出 JSON 数组：[{\"qid\":\"...\",\"verdict\":\"对|错|部分对\",\"analysis\":\"错误根因与正确思路（50字内）\",\"knowledge_point\":\"...\"}]")},
    ], temperature=0.2)
    results = json.loads(raw[raw.find("["): raw.rfind("]") + 1])
    db.update_quiz(quiz_id, results)

    # 错题沉淀到 L3 记忆
    for r in results:
        if r.get("verdict") != "对":
            db.add_memory(space_id, 3, f"测验错题（{r.get('knowledge_point', '')}）：{r.get('analysis', '')}", kind="error")
    correct = sum(1 for r in results if r.get("verdict") == "对")
    return {"quiz_id": quiz_id, "results": results, "score": f"{correct}/{len(results)}"}


# ---------- note.summarize ----------

def note_summarize(space_id: str, document_id: str) -> str:
    doc = db.get_document(document_id)
    if not doc:
        raise ValueError("文档不存在")
    from . import rag as rag_mod
    text = rag_mod.parse_file(doc["path"], doc["filename"])
    chunks = rag_mod.chunk_text(text)
    # 分段摘要后合并（长文档 map-reduce）
    partials = []
    for i in range(0, min(len(chunks), 12), 4):
        part = "\n".join(chunks[i:i + 4])
        partials.append(llm.chat([
            {"role": "system", "content": "把讲义片段整理成要点笔记，保留公式与定义，用 Markdown。"},
            {"role": "user", "content": part[:4000]},
        ], temperature=0.3))
    merged = llm.chat([
        {"role": "system", "content": "把多段笔记合并为一份结构化讲义总结（Markdown）：核心概念、关键公式、易混淆点、典型例题思路。"},
        {"role": "user", "content": "\n\n".join(partials)},
    ], temperature=0.3)
    db.add_message(space_id, "craft", "assistant", merged, expert="笔记总结")
    return merged


# ---------- plan.study ----------

def plan_study(space_id: str, goal: str) -> str:
    memory_ctx = experts.build_memory_context(space_id) or "（暂无学习记录）"
    reply = llm.chat([
        {"role": "system", "content": experts.EXPERTS["planner"]["system"]},
        {"role": "user", "content": f"学习目标：{goal or '系统掌握本课程'}\n\n学生记忆档案：\n{memory_ctx}"},
    ])
    db.add_message(space_id, "plan", "user", goal)
    db.add_message(space_id, "plan", "assistant", reply, expert="学习规划师")
    return reply


SKILLS = {
    "quiz.generate": {"name": "出题测验", "fn": quiz_generate},
    "quiz.grade": {"name": "判卷分析", "fn": quiz_grade},
    "note.summarize": {"name": "讲义总结", "fn": note_summarize},
    "plan.study": {"name": "学习计划", "fn": plan_study},
}
