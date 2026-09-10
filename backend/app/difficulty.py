"""ZPD 自适应难度分层（借鉴 OpenTutor difficulty_selector.py）。

基于 Vygotsky 最近发展区理论：根据学生当前掌握度与错因类型，
映射到最优难度层并给出混合出题分布，注入出题官 system prompt。
"""
from dataclasses import dataclass, field

# ZPD 掌握度阈值
_MASTERY_LOW = 0.4    # 低于此 → Layer 1 基础回忆
_MASTERY_HIGH = 0.7   # 高于此 → Layer 3 陷阱边缘

# 各层分布权重 {1: 基础, 2: 应用, 3: 陷阱}
_DIST_FUNDAMENTAL = {1: 0.7, 2: 0.3, 3: 0.0}
_DIST_TRANSFER = {1: 0.2, 2: 0.6, 3: 0.2}
_DIST_TRAP = {1: 0.1, 2: 0.3, 3: 0.6}
_DIST_LOW = {1: 0.6, 2: 0.3, 3: 0.1}
_DIST_MID = {1: 0.2, 2: 0.5, 3: 0.3}
_DIST_HIGH = {1: 0.1, 2: 0.3, 3: 0.6}


@dataclass
class DifficultyRecommendation:
    primary_layer: int
    layer_distribution: dict
    rationale: str
    mastery_score: float
    gap_type: str | None = None


def recommend_difficulty(
    mastery_score: float,
    gap_type: str | None = None,
    fsrs_state: int | None = None,
) -> DifficultyRecommendation:
    """根据掌握度和错因类型推荐难度层。

    gap_type 覆盖掌握度：
    - 概念误解/记忆模糊 → 基础层
    - 计算失误/审题错误 → 应用层
    - 高掌握度但仍有错 → 陷阱层
    fsrs_state=3 (relearning) → 强制基础层
    """
    # FSRS 重学状态：先巩固基础
    if fsrs_state == 3:
        return DifficultyRecommendation(
            primary_layer=1, layer_distribution=_DIST_LOW,
            rationale="知识点处于重学状态，先巩固基础再推进。",
            mastery_score=mastery_score, gap_type=gap_type)

    # 错因类型覆盖掌握度
    if gap_type in ("概念误解", "记忆模糊"):
        return DifficultyRecommendation(
            primary_layer=1, layer_distribution=_DIST_FUNDAMENTAL,
            rationale=f"检测到「{gap_type}」，优先补基础概念。",
            mastery_score=mastery_score, gap_type=gap_type)
    if gap_type in ("计算失误", "审题错误"):
        return DifficultyRecommendation(
            primary_layer=2, layer_distribution=_DIST_TRANSFER,
            rationale=f"检测到「{gap_type}」，侧重应用与迁移练习。",
            mastery_score=mastery_score, gap_type=gap_type)

    # 基于掌握度
    if mastery_score < _MASTERY_LOW:
        return DifficultyRecommendation(
            primary_layer=1, layer_distribution=_DIST_LOW,
            rationale=f"掌握度较低（{mastery_score:.0%}），先打牢基础。",
            mastery_score=mastery_score, gap_type=gap_type)
    if mastery_score < _MASTERY_HIGH:
        return DifficultyRecommendation(
            primary_layer=2, layer_distribution=_DIST_MID,
            rationale=f"掌握度中等（{mastery_score:.0%}），侧重应用与迁移。",
            mastery_score=mastery_score, gap_type=gap_type)
    return DifficultyRecommendation(
        primary_layer=3, layer_distribution=_DIST_HIGH,
        rationale=f"掌握度较高（{mastery_score:.0%}），挑战陷阱与边缘情况。",
        mastery_score=mastery_score, gap_type=gap_type)


def format_for_prompt(rec: DifficultyRecommendation) -> str:
    """格式化为注入出题官 system prompt 的文本。"""
    dist_str = ", ".join(f"难度{k}层: {v:.0%}" for k, v in sorted(rec.layer_distribution.items()))
    layer_names = {1: "基础回忆", 2: "应用迁移", 3: "陷阱边缘"}
    return (
        f"\n\n【自适应难度指导】\n"
        f"建议主难度：第{rec.primary_layer}层（{layer_names[rec.primary_layer]}）\n"
        f"题目分布：{dist_str}\n"
        f"依据：{rec.rationale}\n"
        f"难度定义：第1层=概念回忆与直接套用；第2层=多步应用与情境迁移；第3层=易错陷阱与边界条件。\n"
        f"请按此分布出题，不要全部集中在同一难度。"
    )


def recommend_for_space(space_id: str, topic_points: list[str] | None = None) -> DifficultyRecommendation:
    """综合空间内薄弱知识点的掌握度，给出整体难度建议。

    topic_points 为空时取空间内最薄弱的 3 个知识点取均值。
    """
    from . import db
    if topic_points:
        rows = [db.get_mastery_point(space_id, p) for p in topic_points]
        rows = [r for r in rows if r]
    else:
        rows = db.weak_points(space_id, 3)
    if not rows:
        return recommend_difficulty(0.3)
    avg_score = sum(r["score"] for r in rows) / len(rows)
    # 取最常见的错因
    gap = None
    from collections import Counter
    error_types = []
    for r in rows:
        # 从最近判卷中找错因
        for q in db.list_quizzes(space_id)[-5:]:
            for a in q.get("answers", []):
                if a.get("verdict") != "对" and a.get("error_type"):
                    import difflib
                    if difflib.SequenceMatcher(None, a.get("knowledge_point", ""), r["point"]).ratio() >= 0.5:
                        error_types.append(a["error_type"])
    if error_types:
        gap = Counter(error_types).most_common(1)[0][0]
    fsrs_state = rows[0].get("state", 0) if rows else 0
    return recommend_difficulty(avg_score, gap_type=gap, fsrs_state=fsrs_state)
