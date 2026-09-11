"""学习速度追踪 + 完成度预测 + 跨空间迁移检测。

借鉴 OpenTutor velocity_tracker.py / completion_forecaster.py / transfer_detector.py。
"""
import time
from datetime import datetime, timedelta

from . import db

_MASTERY_THRESHOLD = 0.75  # 视为"已掌握"的分数线


def compute_velocity(space_id: str, window_days: int = 14) -> dict:
    """滑动窗口内计算学习速度：每天新掌握几个知识点、趋势。"""
    t = db.now()
    window_start = t - window_days * 86400
    history = db.list_mastery_history(space_id)
    # 按知识点取窗口内首次达到 threshold 的时间（首次达标即视为掌握日）
    first_mastered: dict[str, float] = {}
    for h in history:
        if h["created_at"] < window_start:
            continue
        if h["score"] >= _MASTERY_THRESHOLD:
            pt = h["point"]
            if pt not in first_mastered:
                first_mastered[pt] = h["created_at"]
    mastered_in_window = len(first_mastered)
    # 窗口内按天统计，算日均与趋势
    daily: dict[str, int] = {}
    for ts in first_mastered.values():
        day = time.strftime("%Y-%m-%d", time.localtime(ts))
        daily[day] = daily.get(day, 0) + 1
    days_active = max(1, len(daily))
    # 分母用有效天数：空间建库不满一个窗口时按 14 天算会系统性低估日均速度、
    # 把完成日期预测得偏晚
    if history:
        span_days = min(float(window_days),
                        max(1.0, (t - min(h["created_at"] for h in history)) / 86400 + 1))
    else:
        span_days = float(window_days)
    cpd = mastered_in_window / max(span_days, 1)
    # 趋势：前半段 vs 后半段
    sorted_days = sorted(daily.keys())
    mid = len(sorted_days) // 2
    first_half = sum(daily[d] for d in sorted_days[:mid]) if mid > 0 else 0
    second_half = sum(daily[d] for d in sorted_days[mid:])
    if second_half > first_half * 1.2:
        trend = "accelerating"
    elif second_half < first_half * 0.8:
        trend = "decelerating"
    else:
        trend = "stable"
    # 当前总览
    all_points = db.list_mastery(space_id)
    total = len(all_points)
    mastered = sum(1 for p in all_points if p["score"] >= _MASTERY_THRESHOLD)
    return {
        "window_days": window_days,
        "effective_days": round(span_days, 1),
        "mastered_in_window": mastered_in_window,
        "concepts_per_day": round(cpd, 3),
        "velocity_trend": trend,
        "concepts_total": total,
        "concepts_mastered": mastered,
        "concepts_remaining": total - mastered,
        "daily": daily,
    }


def forecast_completion(space_id: str) -> dict:
    """基于学习速度预测课程完成日期（乐观/期望/悲观三档）。"""
    vel = compute_velocity(space_id)
    total = vel["concepts_total"]
    mastered = vel["concepts_mastered"]
    remaining = total - mastered
    if total == 0:
        return {"is_complete": False, "concepts_remaining": 0, "confidence": "low"}
    if remaining == 0:
        return {"is_complete": True, "concepts_remaining": 0, "confidence": "high"}
    # 未掌握知识点的平均差距
    weak = [p for p in db.list_mastery(space_id) if p["score"] < _MASTERY_THRESHOLD]
    avg_unmastered = sum(p["score"] for p in weak) / len(weak) if weak else 0
    avg_gap = _MASTERY_THRESHOLD - avg_unmastered
    cpd = vel["concepts_per_day"]
    if cpd <= 0:
        return {
            "is_complete": False, "concepts_remaining": remaining,
            "avg_gap": round(avg_gap, 3), "confidence": "low",
            "optimistic_days": None, "expected_days": None, "pessimistic_days": None,
            "optimistic_date": None, "expected_date": None, "pessimistic_date": None,
        }
    expected_days = remaining / cpd
    optimistic_days = expected_days * 0.6
    pessimistic_days = expected_days * 1.8
    if vel["velocity_trend"] == "accelerating":
        optimistic_days *= 0.8
        expected_days *= 0.9
    elif vel["velocity_trend"] == "decelerating":
        expected_days *= 1.2
        pessimistic_days *= 1.3
    confidence = "medium"
    if cpd > 0 and mastered >= 5:
        confidence = "high"
    elif mastered < 2:
        confidence = "low"
    now_dt = datetime.now()
    return {
        "is_complete": False,
        "concepts_remaining": remaining,
        "avg_gap": round(avg_gap, 3),
        "concepts_per_day": vel["concepts_per_day"],
        "velocity_trend": vel["velocity_trend"],
        "optimistic_days": round(optimistic_days, 1),
        "expected_days": round(expected_days, 1),
        "pessimistic_days": round(pessimistic_days, 1),
        "optimistic_date": (now_dt + timedelta(days=optimistic_days)).strftime("%Y-%m-%d"),
        "expected_date": (now_dt + timedelta(days=expected_days)).strftime("%Y-%m-%d"),
        "pessimistic_date": (now_dt + timedelta(days=pessimistic_days)).strftime("%Y-%m-%d"),
        "confidence": confidence,
    }


def detect_cross_space_transfer() -> list[dict]:
    """跨空间迁移检测：课程 A 的概念已掌握 → 课程 B 的相关概念未掌握 → 推荐优先学 B。

    用概念名模糊匹配（difflib ≥ 0.55）找跨空间同名/近名知识点。
    """
    import difflib
    spaces = db.list_spaces()
    if len(spaces) < 2:
        return []
    # 收集所有空间的掌握度
    all_mastery: list[dict] = []
    for sp in spaces:
        for p in db.list_mastery(sp["id"]):
            all_mastery.append({**p, "space_id": sp["id"], "space_name": sp["name"]})
    mastered = [p for p in all_mastery if p["score"] >= _MASTERY_THRESHOLD]
    unmastered = [p for p in all_mastery if p["score"] < _MASTERY_THRESHOLD]
    if not mastered or not unmastered:
        return []
    recommendations = []
    seen = set()
    for m in mastered:
        for u in unmastered:
            if m["space_id"] == u["space_id"]:
                continue
            ratio = difflib.SequenceMatcher(None, m["point"], u["point"]).ratio()
            if ratio >= 0.55 or m["point"] in u["point"] or u["point"] in m["point"]:
                key = (m["point"], u["point"], u["space_id"])
                if key in seen:
                    continue
                seen.add(key)
                recommendations.append({
                    "source_concept": m["point"],
                    "source_space": m["space_name"],
                    "source_mastery": round(m["score"], 2),
                    "target_concept": u["point"],
                    "target_space": u["space_name"],
                    "target_space_id": u["space_id"],
                    "target_mastery": round(u["score"], 2),
                    "similarity": round(ratio, 2),
                    "recommendation": (
                        f"你在「{m['space_name']}」中已掌握「{m['point']}」（{int(m['score']*100)}%），"
                        f"可以加速学习「{u['space_name']}」中的「{u['point']}」（当前 {int(u['score']*100)}%）。"
                    ),
                })
    recommendations.sort(key=lambda r: r["target_mastery"])
    return recommendations[:15]


def pick_zpd_question(space_id: str) -> dict | None:
    """今日一题：从薄弱知识点中选一道 ZPD 最优（预测正确率最接近 0.75）的题。

    优先从错题本选已有的题；没有则返回 None 由调用方生成。
    """
    import difflib
    weak = db.weak_points(space_id, 5)
    if not weak:
        return None
    # ZPD 目标：P(correct) ≈ 0.75；BKT 预测 P(correct) = P(L)*(1-slip) + (1-P(L))*guess
    slip, guess = 0.10, 0.15
    best_point = None
    best_dist = 999
    for p in weak:
        p_correct = p["score"] * (1 - slip) + (1 - p["score"]) * guess
        dist = abs(p_correct - 0.75)
        if dist < best_dist:
            best_dist = dist
            best_point = p
    if not best_point:
        return None
    # 从错题本找该知识点的已有题目
    wrongs = db.wrong_questions(space_id)
    for w in wrongs:
        if difflib.SequenceMatcher(None, w.get("knowledge_point", ""), best_point["point"]).ratio() >= 0.5:
            return {"source": "wrong_book", "point": best_point["point"],
                    "question": w, "p_correct": round(best_point["score"] * (1 - slip) + (1 - best_point["score"]) * guess, 3)}
    return {"source": "generate", "point": best_point["point"],
            "p_correct": round(best_point["score"] * (1 - slip) + (1 - best_point["score"]) * guess, 3)}
