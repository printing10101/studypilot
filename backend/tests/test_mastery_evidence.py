"""知识点判定溯源（point_evidence）：调分行吸附、模糊匹配、时间线合并。"""
import json

from app import db


def _mk_quiz(space_id, topic, answers, created_at):
    """直接插一份带判卷答案的测验（绕过 LLM 出题）。"""
    c = db.get_conn()
    qid = db.new_id()
    c.execute("INSERT INTO quiz_records(id,space_id,topic,questions,answers,created_at) "
              "VALUES(?,?,?,?,?,?)",
              (qid, space_id, topic, "[]", json.dumps(answers, ensure_ascii=False), created_at))
    c.commit()
    return qid


def test_point_evidence_pairs_quiz_with_score(db_space):
    # 知识点「泰勒公式」：先做一次判卷记录（带 answers），再走 adjust_mastery 产生 history
    db.adjust_mastery(db_space, "泰勒公式", "wrong")
    db.adjust_mastery(db_space, "泰勒公式", "correct")
    r = db.point_evidence(db_space, "泰勒公式")
    assert r and r["mastery"]["attempts"] == 2
    kinds = [e["kind"] for e in r["events"]]
    assert set(kinds) == {"adjust"}  # 还没有卷子时全是 adjust 事件
    assert r["events"][0]["score_after"] < r["events"][-1]["score_after"]  # 错→对 分数上行


def test_quiz_answer_fuzzy_match_and_score_after(db_space):
    import json
    # 卷子里 knowledge_point 写法有漂移（「泰勒公式的展开」），应被 0.65 阈值召回
    ts = db.now()
    db.save_quiz(db_space, "第三章 测验", [{"id": "q1", "type": "简答", "question": "展开 e^x",
                                            "options": [], "answer": "x", "knowledge_point": "泰勒公式"}])
    c = db.get_conn()
    c.execute("UPDATE quiz_records SET answers=?, created_at=? WHERE space_id=?",
              (json.dumps([{"qid": "q1", "user_answer": "ln(1+x)", "verdict": "错",
                            "analysis": "混淆了泰勒与对数展开", "knowledge_point": "泰勒公式的展开",
                            "error_type": "概念误解"}], ensure_ascii=False), ts, db_space))
    c.commit()
    db.adjust_mastery(db_space, "泰勒公式", "wrong")
    r = db.point_evidence(db_space, "泰勒公式")
    quiz_events = [e for e in r["events"] if e["kind"] == "quiz"]
    assert len(quiz_events) == 1
    ev = quiz_events[0]
    assert ev["topic"] == "第三章 测验" and ev["verdict"] == "错"
    assert ev["error_type"] == "概念误解"
    assert ev["score_after"] is not None  # 就近吸附到 adjust 行
    # adjust 行已被吸附，不再单列
    assert all(e["kind"] != "adjust" for e in r["events"])


def test_point_evidence_no_record_returns_none(db_space):
    assert db.point_evidence(db_space, "从未学过") is None
    assert db.point_evidence(db_space, "  ") is None


def test_point_evidence_wrong_space_isolated(db_space):
    other = db.create_space("另一个空间")["id"]
    db.adjust_mastery(other, "泰勒公式", "wrong")
    assert db.point_evidence(db_space, "泰勒公式") is None
