"""完成度审核的纯规则：课程名归一化、绩点折算、成绩单文本规则解析。"""
from app import audit


def test_norm_name_strips_parens_and_space():
    assert audit.norm_name("高等数学（上）") == audit.norm_name("高等数学(上)")
    assert audit.norm_name("高等数学 （与XX二选一） ") == "高等数学"
    assert audit.norm_name("  Linear  Algebra ") == "linearalgebra"
    assert audit.norm_name("") == ""


def test_grade_to_gpa_percent_scale():
    assert audit.grade_to_gpa("92") == 4.0
    assert audit.grade_to_gpa("85") == 3.7
    assert audit.grade_to_gpa("60") == 1.0
    assert audit.grade_to_gpa("50") == 0.0


def test_grade_to_gpa_words_and_letters():
    assert audit.grade_to_gpa("优秀") == 4.0
    assert audit.grade_to_gpa("良好") == 3.0
    assert audit.grade_to_gpa("A-") == 3.7
    assert audit.grade_to_gpa("合格") == audit.grade_to_gpa("及格")


def test_grade_to_gpa_4_scale_passthrough_and_unknown():
    assert audit.grade_to_gpa("3.7") == 3.7
    assert audit.grade_to_gpa("4.5") == 3.5  # 五级分制 4.5 → 折算
    assert audit.grade_to_gpa("") == -1.0
    assert audit.grade_to_gpa("nothing") == -1.0


def test_parse_courses_text_full_rows():
    text = "高等数学 5 92 2023-2024-1\n大学物理 4 85 大一上\n体育 1 及格"
    rows = audit.parse_courses_text(text)
    assert len(rows) == 3
    first = rows[0]
    assert "高等数学" in first["name"]
    assert first["credit"] == 5.0
    assert first["grade"] == "92"
    assert first["semester"] == "2023-2024-1"
    assert first["status"] == "done"
    assert rows[1]["semester"] == "大一上"
    assert rows[2]["grade"] == "及格"


def test_parse_courses_text_taking_status_and_skip_blank():
    text = "数据结构 4 88 本学期\n\n   \n"
    rows = audit.parse_courses_text(text)
    assert len(rows) == 1
    assert rows[0]["status"] == "taking"


def test_import_courses_text_persists(db_space):
    from app import db
    res = audit.import_courses_text("高等数学 5 92 2023-2024-1\n大学物理 4 85 大一上")
    assert res["added"] == 2
    assert res["method"] == "rules"
    names = [c["name"] for c in db.list_taken_courses()]
    assert any("高等数学" in n for n in names)
