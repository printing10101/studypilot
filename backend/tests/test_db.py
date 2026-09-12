"""SQLite 持久化层：空间/文档判重/掌握度/计划任务/备份的核心行为。"""
import os

import pytest

from app import db


def test_space_crud_roundtrip():
    sp = db.create_space("高等数学", "大一上")
    sid = sp["id"]
    assert db.get_space(sid)["name"] == "高等数学"
    assert [s["id"] for s in db.list_spaces()] == [sid]
    db.delete_space(sid)
    assert db.get_space(sid) is None


def test_document_dedup_by_content_hash(db_space):
    sid = db_space
    did = db.new_id()
    db.add_document(sid, "讲义A.pdf", "/tmp/a.pdf", doc_id=did, content_hash="abc123")
    # 判重只认已就绪文档：pending/error 的不算（索引未完成的重复上传应允许）
    assert db.find_doc_by_hash(sid, "abc123") is None
    db.update_document(did, status="ready")
    dup = db.find_doc_by_hash(sid, "abc123")
    assert dup and dup["id"] == did
    assert db.find_doc_by_hash(sid, "other") is None


def test_document_dedup_scoped_by_space(db_space):
    sid = db_space
    other = db.create_space("别的空间")["id"]
    did = db.new_id()
    db.add_document(sid, "a.pdf", "/tmp/a.pdf", doc_id=did, content_hash="h1")
    db.update_document(did, status="ready")
    assert db.find_doc_by_hash(sid, "h1") is not None
    assert db.find_doc_by_hash(other, "h1") is None  # 判重按空间隔离


def test_adjust_mastery_transitions(db_space):
    sid = db_space
    row = db.adjust_mastery(sid, "泰勒展开", "correct")
    assert row is not None and row["attempts"] == 1
    assert row["correct"] == 1
    # 非法 verdict 被拒绝
    assert db.adjust_mastery(sid, "泰勒展开", "不知道") is None
    # 答错：score 下降、wrong 计数增长
    before = db.get_mastery_point(sid, "泰勒展开")["score"]
    after = db.adjust_mastery(sid, "泰勒展开", "wrong")["score"]
    assert after < before
    assert db.get_mastery_point(sid, "泰勒展开")["wrong"] == 1


def test_mastery_includes_weak_and_due_listing(db_space):
    sid = db_space
    db.adjust_mastery(sid, "极限", "wrong")
    assert db.weak_points(sid, 5)
    # 刚评分的点未到期（FSRS 推进了 due_at）
    assert db.due_points(sid) == []


def test_plan_task_date_validation(db_space):
    sid = db_space
    tid = db.add_plan_task(sid, {"phase": "第1周", "content": "复习极限",
                                 "accept": "能闭卷叙述定义", "due_date": "", "method": "检索"})
    updated = db.set_plan_task_date(sid, tid, "2026-12-01")
    assert updated["due_date"] == "2026-12-01"
    with pytest.raises(ValueError):
        db.set_plan_task_date(sid, tid, "12月1号")
    with pytest.raises(ValueError):
        db.set_plan_task_date(sid, tid, "2026-2-30")
    # 空串清除
    assert db.set_plan_task_date(sid, tid, "")["due_date"] == ""


def test_toggle_plan_task(db_space):
    sid = db_space
    tid = db.add_plan_task(sid, {"phase": "第1周", "content": "做错题变式"})
    assert db.list_plan_tasks(sid)[0]["done"] == 0
    row = db.toggle_plan_task(sid, tid, True)
    assert row["done"]  # 返回带完成态的行
    assert db.list_plan_tasks(sid)[0]["done"] == 1
    assert db.toggle_plan_task(sid, "no-such-task", True) is None


def test_backup_database_creates_file(db_space):
    dest = db.backup_database(keep=2)
    assert dest and os.path.exists(dest)
    again = db.backup_database(keep=2)
    assert again and os.path.exists(again)


def test_taken_courses_crud(db_space):
    row = db.add_taken_course("高等数学", 5.0, "92", "大一上", "done")
    assert row["name"] == "高等数学"
    assert db.list_taken_courses()[0]["credit"] == 5.0
    assert db.delete_taken_course(row["id"])
    assert db.list_taken_courses() == []
    assert db.delete_taken_course("missing") is False
