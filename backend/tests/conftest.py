"""测试环境初始化：必须在任何 app 模块导入之前执行。

- 把 DATA_DIR / UPLOAD_DIR 重定向到一次性临时目录（环境变量优先于 .env），
  测试绝不读写真实 data/ 与 uploads/；
- 单测只覆盖确定性逻辑（规则/解析/存储/调度），不调模型；
- 每个用例结束后清空全部业务表（字面量 DELETE 清单；末尾三张是懒建表，
  不存在时跳过）。新增表时需同步维护本清单。
"""
import os
import sqlite3
import tempfile

import pytest

_TMP_ROOT = tempfile.mkdtemp(prefix="studypilot-test-")
os.environ["DATA_DIR"] = os.path.join(_TMP_ROOT, "data")
os.environ["UPLOAD_DIR"] = os.path.join(_TMP_ROOT, "uploads")


@pytest.fixture
def db_space():
    """一个全新课程空间的 id。"""
    from app import db
    return db.create_space("测试空间")["id"]


@pytest.fixture(autouse=True)
def _clean_db():
    yield
    from app import db
    conn = db.get_conn()
    conn.execute("DELETE FROM vectors")
    conn.execute("DELETE FROM documents")
    conn.execute("DELETE FROM book_documents")
    conn.execute("DELETE FROM books")
    conn.execute("DELETE FROM messages")
    conn.execute("DELETE FROM quiz_records")
    conn.execute("DELETE FROM question_bank")
    conn.execute("DELETE FROM memory")
    conn.execute("DELETE FROM feedback")
    conn.execute("DELETE FROM mastery")
    conn.execute("DELETE FROM mastery_history")
    conn.execute("DELETE FROM flashcards")
    conn.execute("DELETE FROM plan_tasks")
    conn.execute("DELETE FROM concept_edges")
    conn.execute("DELETE FROM meta")
    conn.execute("DELETE FROM handbooks")
    conn.execute("DELETE FROM student_profile")
    conn.execute("DELETE FROM course_schedule")
    conn.execute("DELETE FROM career_plans")
    conn.execute("DELETE FROM syllabus_custom")
    conn.execute("DELETE FROM taken_courses")
    conn.execute("DELETE FROM campus_items")
    conn.execute("DELETE FROM spaces")
    try:
        conn.execute("DELETE FROM llm_calls")
    except sqlite3.OperationalError:
        pass  # 懒建表尚未创建，自然无行可清
    try:
        conn.execute("DELETE FROM method_events")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("DELETE FROM quiz_predictions")
    except sqlite3.OperationalError:
        pass
    conn.commit()
