"""培养方案数据包与完成度审核主流程（全部走仓内数据，无模型）。"""
from app import audit, syllabus


def test_syllabus_stats_consistent():
    stats = syllabus.stats()
    assert stats["schools"] > 0
    assert stats["programs"] > 0        # 内置专业模板数
    assert stats["official"] >= 0 and stats["custom"] == 0  # 干净库无自定义方案


def test_list_schools_and_majors():
    schools = syllabus.list_schools("", "", "")
    assert schools
    some = schools[0]
    info = syllabus.majors_for_school(some.get("name") or some.get("school") or "")
    assert isinstance(info, dict)
    assert "official_majors" in info or "template_majors" in info


def test_run_audit_program_not_found():
    res = audit.run_audit("不存在的大学", "不存在的专业")
    assert res["program_found"] is False
    assert "培养方案" in res["note"]


def test_run_audit_with_packaged_program(db_space):
    from app import db
    db.save_student_profile({"current_school": "清华大学", "major": "机械工程",
                             "year": "", "rank_hint": "", "flags": [], "goal_type": "考研",
                             "target_school": "", "target_major": "", "timeline": "",
                             "notes": "", "learner_personas": []})
    res = audit.run_audit("清华大学", "机械工程")
    assert res["program_found"] is True
    assert res["requirements"]["total"] > 0
    assert isinstance(res["core_states"], list)
    assert res["credits"]["total_required"] > 0
    # 未修任何课时：全部缺失、绩点为 None
    assert res["requirements"]["missing"] == res["requirements"]["total"]
    assert res["gpa"] is None
