"""技能系统（WorkBuddy: Skills）：出题 / 判卷 / 总结 / 学习计划 / 薄弱点复习
/ 错题重做 / 错题变式 / 闪卡 / 费曼检验 / 模拟考试。"""
import json
import time

from . import db, experts, llm, rag


# ---------- quiz.generate ----------

def quiz_generate(space_id: str, topic: str, count: int = 5) -> list[dict]:
    hits = rag.retrieve(space_id, topic or "课程核心概念", top_k=8)
    budget = max(2000, experts.settings.max_context_chars - 1500)
    context = rag.build_context(hits, budget=budget) if hits else "（无讲义片段，按通识出题）"
    questions = llm.chat_json([
        {"role": "system", "content": experts.EXPERTS["examiner"]["system"]},
        {"role": "user", "content": (
            f"围绕「{topic or '本课程重点'}」出 {count} 道题（判断/选择/简答混合）。"
            f"输出 JSON 数组：[{{\"id\":\"q1\",\"type\":\"判断|选择|简答\",\"question\":\"...\","
            f"\"options\":[\"A...\",\"B...\",\"C...\",\"D...\"],\"answer\":\"...\",\"knowledge_point\":\"...\"}}]。"
            f"判断/简答题 options 为空数组。\n\n讲义片段：\n{context}")},
    ], temperature=0.5, max_tokens=2600, task="quiz")
    if not isinstance(questions, list) or not questions:
        raise ValueError("出题结果格式异常")
    qid = db.save_quiz(space_id, topic, questions)
    return [{"quiz_id": qid, "questions": questions}]


# ---------- quiz.grade ----------

_VERDICT_TO_MASTERY = {"对": "correct", "部分对": "partial", "错": "wrong"}


def quiz_grade(space_id: str, quiz_id: str, answers: list[dict]) -> dict:
    quizzes = {q["id"]: q for q in db.list_quizzes(space_id)}
    quiz = quizzes.get(quiz_id)
    if not quiz:
        raise ValueError("测验不存在")
    questions = {q["id"]: q for q in quiz["questions"]}
    results = llm.chat_json([
        {"role": "system", "content": experts.EXPERTS["grader"]["system"]},
        {"role": "user", "content": (
            "题目与标准答案：" + json.dumps(quiz["questions"], ensure_ascii=False) +
            "\n学生答案：" + json.dumps(answers, ensure_ascii=False) +
            "\n输出 JSON 数组：[{\"qid\":\"...\",\"verdict\":\"对|错|部分对\","
            "\"error_type\":\"概念误解|计算失误|记忆模糊|审题错误|\","
            "\"analysis\":\"错误根因与正确思路（50字内）\",\"knowledge_point\":\"...\"}]，"
            "答对的题 error_type 为空字符串，不要多余文字。")},
    ], temperature=0.2, max_tokens=1600, task="grade")
    if not isinstance(results, list):
        raise ValueError("判卷结果格式异常")
    # 把用户作答并入判卷结果，供错题本回显
    user_by_qid = {a.get("qid"): (a.get("answer") or a.get("user_answer") or "") for a in answers}
    for r in results:
        r["user_answer"] = user_by_qid.get(r.get("qid"), "")
    db.update_quiz(quiz_id, results)

    # 错题沉淀到 L3 记忆 + 更新知识点掌握度模型（BKT：按题型给蒙对概率 guess）
    for r in results:
        point = r.get("knowledge_point", "")
        verdict = r.get("verdict", "")
        if verdict in _VERDICT_TO_MASTERY and point:
            qtype = (questions.get(r.get("qid")) or {}).get("type", "")
            guess = 0.25 if qtype in ("选择", "判断") else 0.05
            db.adjust_mastery(space_id, point, _VERDICT_TO_MASTERY[verdict], guess=guess)
        if verdict != "对":
            db.add_memory(space_id, 3, f"测验错题（{point}）：{r.get('analysis', '')}", kind="error")
    correct = sum(1 for r in results if r.get("verdict") == "对")
    return {"quiz_id": quiz_id, "results": results, "score": f"{correct}/{len(results)}"}


# ---------- 错题重做 ----------

def wrong_redo(space_id: str, qids: list[str] | None = None) -> list[dict]:
    """把错题（可指定题目 id，默认全部）重组为新测验。"""
    pool = db.wrong_questions(space_id)
    if qids:
        wanted = set(qids)
        pool = [q for q in pool if q["id"] in wanted]
    if not pool:
        raise ValueError("没有可重做的错题")
    questions = [{k: q[k] for k in ("id", "type", "question", "options", "answer", "knowledge_point")}
                 for q in pool]
    qid = db.save_quiz(space_id, f"错题重做（{len(questions)}题）", questions)
    return [{"quiz_id": qid, "questions": questions, "redo_count": len(questions)}]


# ---------- 错题变式（防背答案） ----------

def wrong_variants(space_id: str, qids: list[str] | None = None, per_question: int = 1) -> list[dict]:
    """对错题生成「变式题」：同一知识点，换数字/换情境/换提问角度，检验真理解而非原题记忆。"""
    pool = db.wrong_questions(space_id)
    if qids:
        wanted = set(qids)
        pool = [q for q in pool if q["id"] in wanted]
    if not pool:
        raise ValueError("没有可生成变式的错题")
    pool = pool[:8]
    brief = [{"原题": q["question"], "题型": q["type"], "正确答案": q["answer"],
              "学生答案": q["user_answer"], "错因分析": q["analysis"],
              "知识点": q["knowledge_point"]} for q in pool]
    total = len(pool) * per_question
    questions = llm.chat_json([
        {"role": "system", "content": experts.EXPERTS["examiner"]["system"]},
        {"role": "user", "content": (
            "以下是学生的错题记录。针对每道错题出 1 道「变式题」：考察同一个知识点，"
            "但改变数字、情境或提问角度，难度相当，让学生无法靠记住原题答案做对。"
            "输出 JSON 数组：[{\"id\":\"v1\",\"type\":\"判断|选择|简答\",\"question\":\"...\","
            "\"options\":[\"A...\",\"B...\",\"C...\",\"D...\"],\"answer\":\"...\","
            "\"knowledge_point\":\"与对应原题一致\"}]。判断/简答题 options 为空数组，"
            f"id 依次为 v1 到 v{total}，共 {total} 题，不要多余文字。\n\n错题记录："
            + json.dumps(brief, ensure_ascii=False))},
    ], temperature=0.6, max_tokens=2600, task="quiz")
    if not isinstance(questions, list) or not questions:
        raise ValueError("变式题生成格式异常")
    qid = db.save_quiz(space_id, f"错题变式（{len(questions)}题）", questions)
    return [{"quiz_id": qid, "questions": questions, "variant_count": len(questions),
             "source_points": sorted({q["knowledge_point"] for q in pool if q.get("knowledge_point")})}]


# ---------- review.generate（薄弱点间隔复习） ----------

def review_generate(space_id: str, count: int = 5) -> list[dict]:
    """从到期/最薄弱的知识点出复习题（Leitner 间隔复习调度）。"""
    due = db.due_points(space_id)
    pool = due or db.weak_points(space_id, 5)
    points = [p["point"] for p in pool[:5]]
    topic = "；".join(points) if points else ""
    made = quiz_generate(space_id, topic or "课程核心概念", count)
    made[0]["review_points"] = points
    made[0]["topic"] = f"薄弱点复习：{topic[:60]}" if points else "综合复习"
    db.set_quiz_topic(made[0]["quiz_id"], made[0]["topic"])
    return made


# ---------- 模拟考试 ----------

def exam_mock(space_id: str, count: int = 10, minutes: int = 30) -> list[dict]:
    """按掌握度采样知识点组卷，前端限时作答。"""
    points = [p["point"] for p in db.weak_points(space_id, 8)]
    topic = "、".join(points) if points else "课程核心概念"
    made = quiz_generate(space_id, topic, count)
    db.set_quiz_topic(made[0]["quiz_id"], "模拟考试")
    made[0]["topic"] = "模拟考试"
    made[0]["exam_minutes"] = minutes
    made[0]["coverage"] = points
    return made


# ---------- 闪卡 ----------

def flashcard_generate(space_id: str, topic: str = "", count: int = 10) -> list[dict]:
    """从讲义片段生成问答闪卡；不指定主题时优先覆盖薄弱知识点。"""
    if not topic:
        weak = db.weak_points(space_id, 5)
        topic = "、".join(p["point"] for p in weak) if weak else "课程核心概念"
    hits = rag.retrieve(space_id, topic, top_k=8)
    budget = max(2000, experts.settings.max_context_chars - 1500)
    context = rag.build_context(hits, budget=budget) if hits else "（无讲义片段，按通识生成）"
    cards = llm.chat_json([
        {"role": "system", "content": (
            "你是记忆卡片设计师。依据讲义片段生成问答式闪卡：卡面是一个具体的问题或提示，"
            "卡背是简明答案（50字内），并在卡面覆盖不同的知识点。输出严格 JSON 数组："
            "[{\"front\":\"问题/提示\",\"back\":\"答案\",\"point\":\"知识点(10字内)\"}]，不要多余文字。")},
        {"role": "user", "content": f"生成 {count} 张闪卡，围绕「{topic}」。\n\n讲义片段：\n{context}"},
    ], temperature=0.5, max_tokens=2600, task="quiz")
    if not isinstance(cards, list) or not cards:
        raise ValueError("闪卡生成格式异常")
    cards = [c for c in cards if isinstance(c, dict) and c.get("front") and c.get("back")]
    return db.add_flashcards(space_id, cards[:count])


# ---------- 费曼讲解检验 ----------

def teach_check(space_id: str, topic: str, explanation: str) -> dict:
    """学生用自己的话讲解概念，判卷专家评估理解质量并更新掌握度。"""
    hits = rag.retrieve(space_id, topic, top_k=4)
    context = rag.build_context(hits, budget=2500) if hits else "（无讲义片段）"
    data = llm.chat_json([
        {"role": "system", "content": (
            "你是严谨的学科助教，评估学生用自己的话对概念的讲解（费曼技巧）。"
            "对照标准讲义判断：讲解是否准确、有无遗漏关键点、有无理解错误。"
            "输出严格 JSON：{\"verdict\":\"准确|基本正确|有误解\","
            "\"missed\":[\"遗漏的关键点\"],\"wrong\":[\"理解错误之处\"],"
            "\"analysis\":\"总评与改进建议（80字内）\",\"knowledge_point\":\"标准知识点名(10-20字)\"}，"
            "missed/wrong 没有就给空数组，不要多余文字。")},
        {"role": "user", "content": f"概念主题：{topic}\n\n学生讲解：{explanation[:2000]}\n\n讲义参考：\n{context}"},
    ], temperature=0.2, max_tokens=1200, task="grade")
    verdict_map = {"准确": "correct", "基本正确": "partial", "有误解": "wrong"}
    point = (data.get("knowledge_point") or topic).strip()[:80]
    if point and data.get("verdict") in verdict_map:
        db.adjust_mastery(space_id, point, verdict_map[data["verdict"]])
    summary = (f"费曼检验「{topic}」：{data.get('verdict', '')}。{data.get('analysis', '')}")
    db.add_message(space_id, "craft", "user", f"[费曼讲解] {topic}：{explanation[:500]}")
    db.add_message(space_id, "craft", "assistant", summary, expert="费曼检验")
    return data


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


# ---------- plan.study（结构化任务版） ----------

def plan_study(space_id: str, goal: str) -> dict:
    """生成结构化学习计划：拆为阶段任务（含截止日期）存库可打卡，同时渲染 Markdown 存入对话。"""
    memory_ctx = experts.build_memory_context(space_id) or "（暂无学习记录）"
    today = time.strftime("%Y-%m-%d")
    data = llm.chat_json([
        {"role": "system", "content": experts.EXPERTS["planner"]["system"] +
            "\n输出严格 JSON：{\"summary\":\"总方针(40字内)\",\"phases\":[{\"name\":\"阶段名（含时间范围，如：第1-2周）\","
            "\"goal\":\"阶段目标\",\"tasks\":[{\"content\":\"具体行动（具体到知识点与练习方式）\","
            "\"accept\":\"验收标准\",\"due\":\"截止日期 YYYY-MM-DD（按阶段时间范围从今天起推算）\","
            "\"points\":[\"涉及知识点\"]}]}]}，"
            "3-5 个阶段，每阶段 2-4 条任务，不要多余文字。"},
        {"role": "user", "content": f"今天是 {today}。学习目标：{goal or '系统掌握本课程'}\n\n学生记忆档案：\n{memory_ctx}"},
    ], temperature=0.4, max_tokens=2600, task="plan")

    if isinstance(data, list):  # 模型可能直接输出阶段数组，归一成 {phases:[...]}
        data = {"phases": data}
    if not isinstance(data, dict):
        raise ValueError("计划生成格式异常")
    tasks = []
    for phase in data.get("phases") or []:
        name = phase.get("name", "")
        for t in phase.get("tasks") or []:
            due = (t.get("due") or "").strip()[:10]
            if due:
                try:
                    time.strptime(due, "%Y-%m-%d")
                except ValueError:
                    due = ""
            tasks.append({"phase": name, "content": t.get("content", ""),
                          "accept": t.get("accept", ""), "due_date": due,
                          "points": t.get("points") or []})
    if not tasks:
        raise ValueError("计划生成格式异常")
    db.replace_plan_tasks(space_id, tasks)

    lines = [f"## 学习计划：{goal or '系统掌握本课程'}", f"**总方针**：{data.get('summary', '')}", ""]
    for phase in data.get("phases") or []:
        lines.append(f"### {phase.get('name', '')}——{phase.get('goal', '')}")
        for i, t in enumerate(phase.get("tasks") or [], 1):
            due_cn = f"（{t.get('due_date', '')} 前完成）" if t.get("due_date") else ""
            lines.append(f"{i}. {t.get('content', '')}{due_cn}（验收：{t.get('accept', '')}）")
        lines.append("")
    plan_md = "\n".join(lines)
    db.add_message(space_id, "plan", "user", goal)
    db.add_message(space_id, "plan", "assistant", plan_md, expert="学习规划师")
    return {"summary": data.get("summary", ""), "tasks": db.list_plan_tasks(space_id),
            "markdown": plan_md}


# ---------- graph.build（知识图谱构建：讲义抽取 + 内置课程图谱合并） ----------

def graph_build(space_id: str) -> dict:
    """构建空间的知识点依赖图：LLM 从已有知识点与讲义片段中抽取前置关系，
    再用内置课程图谱模糊匹配补边。BKT 掌握度 + 该图共同驱动缺陷诊断。"""
    from . import defects
    points = [p["point"] for p in db.list_mastery(space_id)]
    if len(points) < 2:
        raise ValueError("空间知识点太少（至少 2 个），先做几次测验或对话反馈")
    valid = set(points)
    hits = rag.retrieve(space_id, "、".join(points[:6]) + " 核心概念 基础 前置", top_k=10)
    context = rag.build_context(hits, budget=3000) if hits else "（无讲义片段）"
    data = llm.chat_json([
        {"role": "system", "content": (
            "你是学科教研专家，梳理知识点的前置依赖关系：如果掌握 A 是学会 B 的前提，"
            "就有一条 A→B 的边。输出严格 JSON：{\"edges\":[{\"from\":\"前置\",\"to\":\"后继\"}]}，"
            "最多 15 条；from/to 只能使用给定知识点列表中的原词，不要编造新知识点，不要多余文字。")},
        {"role": "user", "content": (
            f"知识点列表：{json.dumps(points, ensure_ascii=False)}\n\n讲义片段：\n{context}")},
    ], temperature=0.2, max_tokens=1600, task="extract")
    edges = data.get("edges") if isinstance(data, dict) else data
    import difflib

    def _to_valid(name: str) -> str:
        name = (name or "").strip()
        if name in valid:
            return name
        best, best_r = None, 0.0
        for pt in points:
            r = difflib.SequenceMatcher(None, pt, name).ratio()
            if r > best_r:
                best, best_r = pt, r
        return best if best_r >= 0.5 else ""

    llm_edges = []
    seen = set()
    for e in edges or []:
        if not isinstance(e, dict):
            continue
        f, t = _to_valid(e.get("from")), _to_valid(e.get("to"))
        if f and t and f != t and (f, t) not in seen:
            seen.add((f, t))
            llm_edges.append({"from": f, "to": t})
    n_llm = db.set_space_edges(space_id, llm_edges, "llm")
    n_cur = defects.match_curriculum_edges(space_id)
    return {"llm_edges": n_llm, "curriculum_edges": n_cur,
            "total": len(db.list_edges(space_id)), "points": len(points)}


SKILLS = {
    "quiz.generate": {"name": "出题测验", "fn": quiz_generate},
    "quiz.grade": {"name": "判卷分析", "fn": quiz_grade},
    "review.generate": {"name": "薄弱点复习", "fn": review_generate},
    "note.summarize": {"name": "讲义总结", "fn": note_summarize},
    "plan.study": {"name": "学习计划", "fn": plan_study},
    "exam.mock": {"name": "模拟考试", "fn": exam_mock},
    "wrong.redo": {"name": "错题重做", "fn": wrong_redo},
    "wrong.variants": {"name": "错题变式", "fn": wrong_variants},
    "flashcard.generate": {"name": "生成闪卡", "fn": flashcard_generate},
    "teach.check": {"name": "费曼检验", "fn": teach_check},
    "graph.build": {"name": "构建知识图谱", "fn": graph_build},
}
