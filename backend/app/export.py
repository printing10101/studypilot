"""一键导出：把学习报告 / 错题本 / 学习计划渲染为 Markdown 文本（纯模板，不调 LLM）。"""
import time

from . import db

_STATUS_CN = {"weak": "薄弱", "learning": "学习中", "mastered": "已掌握"}


def _ts(t: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


def report_md(space_id: str) -> str:
    space = db.get_space(space_id)
    name = space["name"] if space else "课程空间"
    lines = [f"# 学习报告 · {name}", f"> 导出时间：{_ts(time.time())}", ""]

    points = db.list_mastery(space_id)
    if points:
        weak = sum(1 for p in points if p["status"] == "weak")
        mastered = sum(1 for p in points if p["status"] == "mastered")
        due = db.due_points(space_id)
        avg = sum(p["score"] for p in points) / len(points)
        lines += [
            "## 总览",
            f"- 知识点 {len(points)} 个：薄弱 {weak} / 学习中 {len(points) - weak - mastered} / 已掌握 {mastered}",
            f"- 平均掌握度 {int(avg * 100)}%，到期待复习 {len(due)} 个",
            "",
            "| 知识点 | 掌握度 | 状态 | 对/错 | 下次复习 |",
            "|---|---|---|---|---|",
        ]
        for p in points:
            due_cn = "—" if p["status"] == "mastered" else (
                "应复习" if p["due_at"] <= time.time() else _ts(p["due_at"]))
            lines.append(f"| {p['point']} | {int(p['score'] * 100)}% | "
                         f"{_STATUS_CN.get(p['status'], p['status'])} | {p['correct']}/{p['wrong']} | {due_cn} |")
        lines.append("")
    else:
        lines += ["## 总览", "暂无掌握度数据（先做几次测验或对话反馈）。", ""]

    quizzes = db.list_quizzes(space_id)
    graded = [q for q in quizzes if q["answers"]]
    if graded:
        lines += ["## 测验记录", ""]
        for q in graded[:10]:
            good = sum(1 for a in q["answers"] if a.get("verdict") == "对")
            lines.append(f"- {_ts(q['created_at'])}　{q['topic'] or '综合'}　{good}/{len(q['questions'])}")
        lines.append("")

    mem = db.list_memory(space_id)
    l2 = [m for m in mem if m["level"] == 2]
    l3 = [m for m in mem if m["level"] == 3]
    if l2 or l3:
        lines += ["## 记忆档案"]
        for m in l2[-2:]:
            lines += [f"**近期摘要**（{_ts(m['created_at'])}）：{m['content']}"]
        kind_cn = {"weakness": "薄弱", "error": "错题", "mastery": "掌握", "fact": "事实"}
        for m in l3[-15:]:
            lines.append(f"- [{kind_cn.get(m['kind'], m['kind'] or '记录')}] {m['content']}")
        lines.append("")
    return "\n".join(lines)


def wrong_md(space_id: str) -> str:
    wrong = db.wrong_questions(space_id)
    space = db.get_space(space_id)
    name = space["name"] if space else "课程空间"
    lines = [f"# 错题本 · {name}", f"> 导出时间：{_ts(time.time())}　共 {len(wrong)} 道错题", ""]
    if not wrong:
        return "\n".join(lines + ["还没有错题记录，保持住！"])
    current_quiz = None
    for i, q in enumerate(wrong, 1):
        if q["quiz_topic"] != current_quiz:
            current_quiz = q["quiz_topic"]
            lines += [f"## {current_quiz or '综合练习'}", ""]
        lines += [
            f"### {i}. [{q['type']}] {q['question']}",
            f"- **我的答案**：{q.get('user_answer') or '（未记录）'}",
            f"- **参考答案**：{q.get('answer', '')}",
            f"- **判定**：{q.get('verdict', '')}　**知识点**：{q.get('knowledge_point', '')}",
            f"- **错因分析**：{q.get('analysis', '')}",
            "",
        ]
    return "\n".join(lines)


def plan_md(space_id: str) -> str:
    tasks = db.list_plan_tasks(space_id)
    space = db.get_space(space_id)
    name = space["name"] if space else "课程空间"
    lines = [f"# 学习计划 · {name}", f"> 导出时间：{_ts(time.time())}", ""]
    if not tasks:
        return "\n".join(lines + ["还没有生成学习计划（在「学习计划」页生成）。"])
    done = sum(1 for t in tasks if t["done"])
    lines.append(f"进度：{done}/{len(tasks)}　平均掌握度见学习报告")
    lines.append("")
    current = None
    for t in tasks:
        if t["phase"] != current:
            current = t["phase"]
            lines += [f"## {current or '任务'}", ""]
        mark = "x" if t["done"] else " "
        due_cn = f"（{t['due_date']} 前完成）" if t.get("due_date") else ""
        lines.append(f"- [{mark}] {t['content']}{due_cn}")
        if t["accept"]:
            lines.append(f"  - 验收：{t['accept']}")
    return "\n".join(lines)


EXPORTS = {"report": report_md, "wrong": wrong_md, "plan": plan_md}
