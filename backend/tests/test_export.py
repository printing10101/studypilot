"""一键导出报告的模板渲染（零 LLM）。"""
from app import db, export


def _seed_space(sid: str) -> None:
    db.adjust_mastery(sid, "极限", "correct")
    db.adjust_mastery(sid, "连续", "wrong")
    qid = db.save_quiz(sid, "第2章测验", [
        {"id": "q1", "type": "选择", "question": "极限定义?", "options": ["A", "B"], "answer": "A"},
        {"id": "q2", "type": "简答", "question": "叙述ε-δ定义", "answer": "..."},
    ])
    db.update_quiz(qid, [
        {"qid": "q1", "user_answer": "B", "verdict": "错", "analysis": "概念混淆"},
        {"qid": "q2", "user_answer": "略", "verdict": "部分对", "analysis": "不完整"},
    ])
    db.add_plan_task(sid, {"phase": "第1周", "content": "复习极限定义",
                           "accept": "闭卷叙述", "method": "检索"})
    db.add_memory(sid, 3, "对极限概念反复混淆", kind="weakness")


def test_report_md_contains_core_sections(db_space):
    _seed_space(db_space)
    md = export.report_md(db_space)
    assert md.startswith("# 学习报告")
    assert "## 总览" in md
    assert "极限" in md and "连续" in md
    assert "## 测验记录" in md and "第2章测验" in md
    assert "## 记忆档案" in md and "对极限概念反复混淆" in md
    assert "## 学习方法建议" in md


def test_wrong_md_lists_wrong_questions_with_analysis(db_space):
    _seed_space(db_space)
    md = export.wrong_md(db_space)
    assert "# 错题本" in md
    assert "极限定义?" in md
    assert "概念混淆" in md
    # 答对的题（无错题记录时）不出现在错题本
    assert "共 2 道错题" in md  # q1 错、q2 部分对也计入


def test_plan_md_progress_and_methods(db_space):
    _seed_space(db_space)
    md = export.plan_md(db_space)
    assert "# 学习计划" in md
    assert "进度：0/1" in md
    assert "复习极限定义" in md
    assert "验收：闭卷叙述" in md


def test_export_registry_covers_three_kinds():
    assert set(export.EXPORTS) == {"report", "wrong", "plan"}
