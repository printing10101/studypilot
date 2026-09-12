"""FSRS 调度包装：评分推进、间隔预告、遗忘曲线。"""
import time

from app import fsrs


def _fresh_row() -> dict:
    return {"id": "card-1", "box": 1, "due_at": time.time(), "state": 0,
            "step": None, "stability": 0.0, "difficulty": 0.0,
            "last_review": 0.0, "created_at": time.time()}


def test_review_good_advances_due():
    row = _fresh_row()
    out = fsrs.review(row, fsrs.R_GOOD)
    assert out["due_at"] > time.time()
    assert out["box"] == 2
    assert out["stability"] > 0
    assert out["state"] != 0  # 不再是 New


def test_review_again_resets_box():
    row = _fresh_row()
    row["box"] = 3
    out = fsrs.review(row, fsrs.R_AGAIN)
    assert out["box"] == 1


def test_preview_intervals_ordered():
    row = _fresh_row()
    prev = fsrs.preview_intervals(row)
    assert set(prev) == {"1", "2", "3", "4"}
    assert prev["1"] <= prev["2"] <= prev["3"] <= prev["4"]


def test_retrievability_decays_monotonically():
    s, last = 10.0, time.time() - 86400
    r_now = fsrs.retrievability(s, last, at=time.time())
    r_later = fsrs.retrievability(s, last, at=time.time() + 30 * 86400)
    assert 0.0 < r_later < r_now <= 1.0


def test_retrievability_invalid_state_returns_minus_one():
    assert fsrs.retrievability(0.0, time.time()) == -1.0
    assert fsrs.retrievability(5.0, 0.0) == -1.0
