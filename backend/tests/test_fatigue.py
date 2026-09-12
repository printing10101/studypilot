"""疲劳检测信号与提示分级。"""
from app import fatigue


def test_empty_and_neutral_messages():
    assert fatigue.detect_fatigue("") == 0.0
    assert fatigue.detect_fatigue("今天我们讲一下泰勒公式的应用") <= 0.2


def test_frustrated_message_scores_high():
    # 命中三个信号组（看不懂/学不会 + 太难了 + 好烦）→ 明显疲劳
    msg = "看不懂，太难了，好烦啊，不想学了"
    score = fatigue.detect_fatigue(msg)
    assert score >= 0.7
    assert "疲劳" in fatigue.fatigue_hint(score)


def test_score_clamped_to_unit_interval():
    msg = "看不懂 太难了 好烦 放弃 崩溃 累了 " * 10
    score = fatigue.detect_fatigue(msg)
    assert 0.7 <= score <= 1.0  # 重复命中同一信号组不叠加，总量封顶 1.0


def test_hint_thresholds():
    assert fatigue.fatigue_hint(0.2) == ""
    assert fatigue.fatigue_hint(0.5) != ""
    assert fatigue.fatigue_hint(0.9) != ""
