"""技能出口的题目脱敏：标准答案不下发、缺省字段补齐。"""
from app import skills


def test_public_questions_strip_answer_and_fill_defaults():
    cleaned = skills._public_questions([
        {"id": "q1", "type": "选择", "question": "1+1?", "options": ["2", "3"], "answer": "2"},
        {"id": "q2", "question": "叙述定义", "answer": "……"},
        {"id": "q3", "type": "简答", "question": "举例"},
    ])
    for q in cleaned:
        assert "answer" not in q
    assert cleaned[0]["options"] == ["2", "3"]
    assert cleaned[1]["type"] == "简答"       # 缺 type 补默认
    assert cleaned[1]["options"] == []        # 缺 options 补空表
    assert cleaned[2]["knowledge_point"] == ""  # 缺知识点补空串


def test_public_questions_empty():
    assert skills._public_questions([]) == []


def test_skills_catalog_entries_have_name():
    assert skills.SKILLS, "技能目录不能为空"
    for sid, meta in skills.SKILLS.items():
        assert meta.get("name"), f"技能 {sid} 缺 name"
