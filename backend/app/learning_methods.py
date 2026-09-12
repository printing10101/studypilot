"""证据导向学习方法库 + 个性化推荐。

依据 Dunlosky et al. (2013) 对十种学习策略的效用评估、Roediger & Karpicke 检索练习研究、
Rohrer & Bjork 交错练习、Chi 自我解释、Sweller 认知负荷（样例效应）、
Mayer 双重编码，以及 Learning Scientists 的课堂实践指南。

本模块只做「信号 → 方法」映射与可执行建议文本，不调用 LLM。
上游缺陷诊断、计划生成、今日学习视图共用同一套方法口径。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import db

log = logging.getLogger("studypilot.learning_methods")

# ---------- 方法目录 ----------

@dataclass(frozen=True)
class Method:
    id: str
    name: str
    utility: str          # high | medium
    summary: str          # 一句话原理
    how: str              # 可执行做法（学生能直接照做）
    avoid: str = ""       # 常见误用
    evidence: str = ""    # 简短出处线索


METHODS: dict[str, Method] = {
    "retrieval": Method(
        id="retrieval",
        name="检索练习",
        utility="high",
        summary="先凭记忆作答再对照答案，比反复重读更巩固记忆（测验效应）。",
        how="合上讲义写要点/做题；答完再对答案；错的题标出后次日再检索一次。",
        avoid="只翻答案觉得「我会了」——那是再认，不是回忆。",
        evidence="Roediger & Karpicke；Dunlosky 等高工具性策略",
    ),
    "spacing": Method(
        id="spacing",
        name="间隔重复",
        utility="high",
        summary="同一内容分散在多天复习，遗忘曲线被多次打断，长期留存远高于集中突击。",
        how="新学内容：当天 → 次日 → 3 天 → 1 周 → 2 周；用闪卡/到期复习清单自动排期。",
        avoid="考前一晚连刷三遍同一章——感觉熟练，一周后基本忘光。",
        evidence="Cepeda 等间隔效应综述；FSRS 算法即此原理的工程化",
    ),
    "interleaving": Method(
        id="interleaving",
        name="交错练习",
        utility="medium",
        summary="同一时段混合多个主题/题型，迫使大脑辨识「该用哪种方法」，迁移能力更强。",
        how="刷题时不要只刷同一知识点：3 题 A + 2 题 B + 3 题 C 混排；模拟考按掌握度跨点组卷。",
        avoid="阻塞式连刷 20 道同型题——正确率虚高，考试仍不会选方法。",
        evidence="Rohrer & Taylor；Dunlosky 中等工具性",
    ),
    "elaboration": Method(
        id="elaboration",
        name="精细追问",
        utility="medium",
        summary="不断问「为什么」「和已知怎么连」，把新信息挂到已有知识网上。",
        how="每个定义后自问：为什么这样规定？反例是什么？和前一章哪个概念像/不像？写下来。",
        avoid="只抄定义不加工——抄写对理解几乎无增益。",
        evidence="Dunlosky 等；elaborative interrogation",
    ),
    "self_explain": Method(
        id="self_explain",
        name="自我解释",
        utility="medium",
        summary="每读一步就解释「为什么有这一步」，暴露断层比背结论有效。",
        how="例题不要只看：盖住下一步，自己推并说出理由；错题复盘写「我卡在第几步、为什么」。",
        avoid="默默滑动看完——流畅感≠理解。",
        evidence="Chi 等自我解释研究",
    ),
    "dual_coding": Method(
        id="dual_coding",
        name="双重编码",
        utility="medium",
        summary="语言 + 图像双通道编码，回忆路径更多，抗遗忘。",
        how="概念配一张草图/流程/坐标示意；公式旁画适用场景；笔记左文右图。",
        avoid="抄装饰性插图却不解释图与概念的对应。",
        evidence="Mayer 多媒体学习；Paivio 双重编码",
    ),
    "worked_example": Method(
        id="worked_example",
        name="样例学习",
        utility="medium",
        summary="新手阶段先精读带步骤的完整样例，再逐步自己做，降低无效认知负荷。",
        how="掌握度低时：读 1 个例题并逐步注释 → 仿做 1 题 → 合上做 1 题 → 变式 1 题。",
        avoid="已会之后仍只看不做——会掉进「流畅错觉」。",
        evidence="Sweller 认知负荷理论；样例效应",
    ),
    "generation": Method(
        id="generation",
        name="生成效应",
        utility="medium",
        summary="自己产出（出题、总结、讲给别人听）比被动阅读记得更牢。",
        how="每学完一节：出 2 道自测题；或用费曼把概念讲给「外行」听。",
        avoid="只整理漂亮笔记却从不回看/自测。",
        evidence="Slamecka & Graf；生成效应",
    ),
    "metacognition": Method(
        id="metacognition",
        name="元认知校准",
        utility="medium",
        summary="区分「感觉会了」和「真会了」，用自测校正判断，避免过度自信。",
        how="学习前先预测正确率；学完立刻闭卷自测；对照实际得分，偏差大就下调学习时间预期。",
        avoid="重读两遍后觉得「过得很熟」——流畅感会系统性高估掌握。",
        evidence="Flavell；Dunlosky 学业判断研究",
    ),
    "desirable_difficulty": Method(
        id="desirable_difficulty",
        name="合意困难",
        utility="medium",
        summary="适度吃力（稍难题、变式、延迟反馈）比轻松流畅学得更久。",
        how="正确率稳定 >90% 就上难度/换情境；卡壳 2 次再看提示，不要立刻看答案。",
        avoid="难度过高导致习得性无助——ZPD 外效率为负。",
        evidence="Bjork & Bjork",
    ),
    "feynman": Method(
        id="feynman",
        name="费曼讲解",
        utility="high",
        summary="用最简单的话讲清楚，讲不顺的地方就是知识断层。",
        how="对着空气/同学讲 2 分钟；卡壳处回讲义补上；再用一个生活例子重讲一遍。",
        avoid="堆术语装懂——术语壳不是理解。",
        evidence="生成 + 自我解释的组合拳",
    ),
    "session_structure": Method(
        id="session_structure",
        name="会话结构",
        utility="medium",
        summary="固定「检索热身 → 精学一块 → 交错练习 → 收尾自测」比无目的翻书高效。",
        how="单次 45–50 分钟：前 5 分钟做昨日检索题；中间 25 分钟攻一个点；"
            "再 10 分钟混练；最后 5 分钟闭卷总结 3 句话。",
        avoid="长时间低强度「泡」在书桌前。",
        evidence="时间分配与检索设计的实践共识",
    ),
    "error_analysis": Method(
        id="error_analysis",
        name="错因三维复盘",
        utility="high",
        summary="每道错分知识/策略/认知三层，对症下药而不是笼统「再刷一遍」。",
        how="知识层→回定义+样例；策略层→写标准步骤清单再练；认知层→读题圈关键词、限时慢审。",
        avoid="只抄正确答案不写错因。",
        evidence="判卷归因与迁移学习实践",
    ),
}

# 错因 → 优先方法序列
_ERROR_METHOD_MAP = {
    "概念误解": ["elaboration", "worked_example", "self_explain", "dual_coding"],
    "记忆模糊": ["spacing", "retrieval", "feynman", "generation"],
    "计算失误": ["self_explain", "interleaving", "desirable_difficulty", "error_analysis"],
    "审题错误": ["self_explain", "dual_coding", "error_analysis", "session_structure"],
}

# 诊断信号 → 方法
_SIGNAL_METHOD_MAP = {
    "forgetting": ["spacing", "retrieval"],
    "low_mastery": ["worked_example", "self_explain", "retrieval"],
    "mid_mastery": ["interleaving", "elaboration", "retrieval"],
    "high_but_err": ["desirable_difficulty", "interleaving", "metacognition"],
    "prereq_gap": ["worked_example", "self_explain", "error_analysis"],
    "repeated_wrong": ["error_analysis", "worked_example", "feynman"],
    "fatigue": ["session_structure", "retrieval"],
    "decelerating": ["session_structure", "interleaving", "metacognition"],
    "blocked_practice": ["interleaving", "generation"],
}


@dataclass
class MethodAdvice:
    methods: list[dict] = field(default_factory=list)  # {id,name,how,why,utility}
    tip: str = ""
    focus: str = ""
    persona: dict = field(default_factory=dict)  # 画像摘要（id/name/tip/source）


def method_brief(mid: str, why: str = "") -> dict:
    m = METHODS[mid]
    return {
        "id": m.id,
        "name": m.name,
        "utility": m.utility,
        "summary": m.summary,
        "how": m.how,
        "avoid": m.avoid,
        "evidence": m.evidence,
        "why": why,
    }


def methods_for_error(error_type: str, limit: int = 3) -> list[dict]:
    """由判卷错因类型给出方法序列。"""
    ids = _ERROR_METHOD_MAP.get(error_type or "", [])
    if not ids:
        ids = ["retrieval", "spacing", "error_analysis"]
    return [method_brief(i, why=f"针对错因「{error_type or '综合薄弱'}」") for i in ids[:limit]]


def methods_for_signals(signals: list[str], limit: int = 4) -> list[dict]:
    """由诊断信号列表合并方法（保序去重）。"""
    seen: list[str] = []
    for s in signals:
        for mid in _SIGNAL_METHOD_MAP.get(s, []):
            if mid not in seen:
                seen.append(mid)
    if not seen:
        seen = ["retrieval", "spacing", "session_structure"]
    return [method_brief(i) for i in seen[:limit]]


def format_methods_block(methods: list[dict], title: str = "【学习方法建议】") -> str:
    """注入 LLM prompt 的方法指导块。"""
    if not methods:
        return ""
    lines = [title,
             "只推荐下列已验证方法，任务描述里要写清「怎么做」而不是空喊「多练习」："]
    for i, m in enumerate(methods, 1):
        extra = f"（{m['why']}）" if m.get("why") else ""
        lines.append(f"{i}. {m['name']}{extra}：{m['how']}")
        if m.get("avoid"):
            lines.append(f"   避免：{m['avoid']}")
    return "\n".join(lines)


# ---------- 空间级画像 → 综合建议 ----------

def _dominant_error_types(space_id: str, top: int = 2) -> list[str]:
    from collections import Counter
    stats: Counter[str] = Counter()
    # 取最近 8 次测验的错因（recent_quizzes 新→旧，SQL LIMIT 免全量 JSON 解析）
    for q in db.recent_quizzes(space_id, 8):
        for a in q.get("answers") or []:
            if a.get("verdict") != "对" and a.get("error_type"):
                stats[a["error_type"]] += 1
    return [et for et, _ in stats.most_common(top)]


def space_signals(space_id: str) -> dict:
    """汇总空间当前的学习信号（零 LLM）。"""
    points = db.list_mastery(space_id)
    due = db.due_points(space_id)
    now = db.now()
    signals: list[str] = []
    notes: list[str] = []

    if not points:
        return {"signals": ["low_mastery"], "errors": [],
                "avg_score": 0.0, "due_count": 0, "notes": ["先积累测验数据再个性化推荐"]}

    avg = sum(p["score"] for p in points) / len(points)
    wrong_heavy = sum(1 for p in points if p["wrong"] >= 2 and p["wrong"] >= p["correct"])
    if due:
        signals.append("forgetting")
        notes.append(f"{len(due)} 个知识点到期待复习")
    if avg < 0.4:
        signals.append("low_mastery")
    elif avg < 0.7:
        signals.append("mid_mastery")
    else:
        high_err = [p for p in points if p["score"] >= 0.75 and p["wrong"] > p["correct"]]
        if high_err:
            signals.append("high_but_err")

    # 留存：掌握但很久没复习
    forgetting = 0
    for p in points:
        if p["score"] >= 0.6:
            try:
                r = db.estimate_retention(
                    p["score"], p["box"], p["updated_at"], now,
                    p.get("stability") or 0.0, p.get("last_review") or 0.0)
                if r < 0.5:
                    forgetting += 1
            except Exception:
                log.debug("留存抽样计算失败（point=%s）", p.get("point"), exc_info=True)
    if forgetting >= 2:
        if "forgetting" not in signals:
            signals.append("forgetting")
        notes.append(f"{forgetting} 个曾掌握点遗忘明显，复习优先于新学")

    if wrong_heavy >= 2:
        signals.append("repeated_wrong")

    # 依赖：有前置薄弱（轻量检查，避免 today 接口跑完整诊断）
    try:
        edges = db.list_edges(space_id)
        by_name = {p["point"]: p for p in points}
        prereq_gap = False
        for e in edges:
            src = by_name.get(e["from_point"])
            dst = by_name.get(e["to_point"])
            if not src or not dst:
                continue
            if src["score"] < 0.5 and dst["score"] < 0.8:
                prereq_gap = True
                break
        if prereq_gap:
            signals.append("prereq_gap")
            notes.append("存在前置薄弱拖累后继，先补根因")
    except Exception:
        log.warning("学习方法信号 prereq_gap 计算失败（本次建议缺该信号）", exc_info=True)

    # 趋势
    try:
        from . import velocity
        vel = velocity.compute_velocity(space_id)
        if vel.get("velocity_trend") == "decelerating":
            signals.append("decelerating")
            notes.append("掌握速度在放缓，缩短单次会话并交错复习")
    except Exception:
        log.warning("学习方法信号 decelerating 计算失败（本次建议缺该信号）", exc_info=True)

    # 综合度量：负载 / 校准
    try:
        from . import study_metrics
        load = study_metrics.daily_load(space_id)
        if load.get("band") == "high":
            notes.append(f"今日负载偏高（{load['load_score']}），建议只 {load['suggested_minutes']} 分钟且不开新章")
            signals.append("fatigue")
        cal = study_metrics.calibration(space_id)
        if cal.get("label") == "overconfident":
            signals.append("high_but_err")
            notes.append("自我预测长期高于实际，需强制闭卷自测")
        elif cal.get("label") == "underconfident":
            notes.append("预测常低于实际，可适度上难度建立成功体验")
    except Exception:
        log.warning("学习方法信号 load/calibration 计算失败（本次建议缺该信号）", exc_info=True)

    errors = _dominant_error_types(space_id)
    for et in errors[:1]:
        # 把主错因也翻译成信号补充
        if et == "概念误解":
            signals.append("low_mastery")
        elif et == "记忆模糊":
            signals.append("forgetting")
        elif et in ("计算失误", "审题错误"):
            signals.append("blocked_practice")

    return {
        "signals": signals,
        "errors": errors,
        "avg_score": round(avg, 3),
        "due_count": len(due),
        "notes": notes,
    }


def advise_for_space(space_id: str, limit: int = 4) -> MethodAdvice:
    """空间级个性化方法建议（诊断面板 / 今日学习 / 计划注入共用）。

    在「学习信号 × 错因」基础上叠加学习者人格画像的方法加权与会话/语气适配。
    """
    from . import learner_persona

    sig = space_signals(space_id)
    methods = methods_for_signals(sig["signals"], limit=limit + 2)

    # 主错因方法插到前面
    if sig["errors"]:
        primary = methods_for_error(sig["errors"][0], limit=2)
        merged: list[dict] = []
        seen = set()
        for m in primary + methods:
            if m["id"] not in seen:
                seen.add(m["id"])
                merged.append(m)
        methods = merged

    # 人格画像加权 + 方法效果闭环加权
    profile = learner_persona.resolve_profile(space_id)
    boost = learner_persona.method_boost_map(profile)
    try:
        from . import study_metrics
        for mid, b in study_metrics.efficacy_boost(space_id).items():
            boost[mid] = boost.get(mid, 0.0) + b
    except Exception:
        log.warning("方法效果闭环加权失败（本次仅按画像加权）", exc_info=True)
    methods = learner_persona.apply_boost(methods, boost)[:limit]
    for m in methods:
        if not m.get("why"):
            top = max(boost.items(), key=lambda x: x[1]) if boost else None
            if top and top[0] == m["id"] and top[1] > 0:
                pname = learner_persona.PERSONAS.get(profile.primary)
                if pname:
                    m["why"] = f"匹配画像「{pname.name}」"

    tip_bits = sig["notes"][:2]
    if sig["due_count"]:
        tip_bits.append("今日先清到期复习（检索优先），再开新内容")
    elif sig["avg_score"] < 0.4:
        tip_bits.append("用样例学习降负荷：读例题→仿做→闭卷做，而不是直接刷难题")

    # 考试倒计时
    try:
        from . import study_metrics
        cd = study_metrics.exam_countdown(space_id)
        if cd and 0 < cd.get("days_left", 999) <= 90:
            tip_bits.append(f"距考试约 {cd['days_left']} 天（{cd['phase']}）：{cd['strategy']}")
    except Exception:
        log.warning("建议中的考试倒计时计算失败（tip 缺倒计时）", exc_info=True)

    primary_p = learner_persona.PERSONAS.get(profile.primary)
    if primary_p and primary_p.tip:
        tip_bits.append(primary_p.tip)

    tip = "；".join(tip_bits) if tip_bits else "保持「检索 + 间隔」双核，新学与复习约 6:4"

    focus = ""
    if sig["errors"]:
        focus = sig["errors"][0]
    elif sig["due_count"] >= 3:
        focus = "记忆模糊"
    elif sig["avg_score"] < 0.4:
        focus = "概念误解"

    persona_meta = {
        "primary": profile.primary,
        "name": primary_p.name if primary_p else "",
        "labels": profile.labels(),
        "explicit": profile.explicit,
        "inferred": profile.inferred,
        "evidence": profile.evidence,
        "session": primary_p.session if primary_p else "",
        "tone": primary_p.tone if primary_p else "",
        "tip": primary_p.tip if primary_p else "",
    }
    return MethodAdvice(methods=methods, tip=tip, focus=focus, persona=persona_meta)


def daily_tip(space_id: str) -> str:
    """今日学习页展示的一句方法提示（含画像）。"""
    advice = advise_for_space(space_id, limit=3)
    names = "、".join(m["name"] for m in advice.methods[:3])
    base = f"今日建议侧重：{names}。" if names else ""
    persona_line = ""
    if advice.persona.get("name"):
        detail = advice.persona.get("session") or advice.persona.get("tip") or ""
        persona_line = f"画像「{advice.persona['name']}」"
        if detail:
            persona_line += f"：{detail.rstrip('。')}"
        persona_line += "。"
    return base + persona_line + advice.tip


def planner_prompt_block(space_id: str) -> str:
    """注入学习规划师 system 的方法协议 + 人格适配。"""
    from . import learner_persona

    advice = advise_for_space(space_id, limit=4)
    profile = learner_persona.resolve_profile(space_id)
    block = format_methods_block(advice.methods, title="【证据导向学习方法（必须体现在任务里）】")
    header = (
        "\n\n【学习科学规划原则】\n"
        "1. 每条任务必须写清学习方法与可执行动作，禁止空泛的「复习第三章」「多做题」。\n"
        "2. 复习任务用检索（闭卷回忆/做题）而非重读；新学任务对低掌握点优先样例→仿做→独立做。\n"
        "3. 同一阶段内不同知识点/题型要交错，不要整周只刷一个点。\n"
        "4. 会话结构：每次学习含「昨日检索热身 → 精学 → 交错练 → 闭卷收尾」。\n"
        "5. 错因对症：概念误解→追问/样例；记忆模糊→间隔+检索；计算/审题→自我解释+变式。\n"
        "6. 疲劳或速度放缓时缩短单次时长、提高任务粒度，而不是加量。"
    )
    parts = [header]
    persona_block = learner_persona.persona_tip_block(profile)
    if persona_block:
        parts.append("\n" + persona_block)
    rules = learner_persona.planner_persona_rules(profile)
    if rules:
        parts.append(rules)
    try:
        from . import study_metrics
        cd = study_metrics.exam_countdown(space_id)
        if cd and cd.get("days_left") is not None and cd["days_left"] >= 0:
            parts.append(
                f"\n【考试倒计时】距 {cd['deadline']} 约 {cd['days_left']} 天，"
                f"当前为「{cd['phase']}」：{cd['strategy']}")
        load = study_metrics.daily_load(space_id)
        if load.get("band") == "high":
            parts.append(f"\n【今日负载】偏高，阶段任务粒度控制在 {load['suggested_minutes']} 分钟内，"
                         "优先到期检索，避免再堆新内容。")
    except Exception:
        log.warning("规划协议块中的倒计时/负载注入失败", exc_info=True)
    tip = f"\n当前画像提示：{advice.tip}。" if advice.tip else ""
    parts.append(tip)
    if block:
        parts.append(block)
    return "\n".join(p for p in parts if p)


def grade_followup(result_rows: list[dict], space_id: str = "") -> str:
    """判卷后给学生的短方法跟进（按错题主因，并叠加人格语气）。"""
    from collections import Counter

    from . import learner_persona

    errs = [r.get("error_type") for r in result_rows if r.get("verdict") != "对" and r.get("error_type")]
    profile = learner_persona.resolve_profile(space_id) if space_id else learner_persona.PersonaProfile()
    primary_p = learner_persona.PERSONAS.get(profile.primary)
    tone = primary_p.tone if primary_p else ""

    if not errs:
        msg = "本卷正确率良好：下一步用交错混练与稍难变式做合意困难，巩固迁移。"
        if primary_p and primary_p.id == "overconfident":
            msg += "（仍建议闭卷再抽 2 题验证，避免流畅错觉）"
        if tone:
            msg += f"\n风格提示：{tone}"
        return msg
    primary = Counter(errs).most_common(1)[0][0]
    recs = methods_for_error(primary, limit=2)
    # 画像可能替换/前置更匹配的方法
    if space_id:
        boost = learner_persona.method_boost_map(profile)
        ids = [m["id"] for m in recs]
        for mid, b in sorted(boost.items(), key=lambda x: -x[1]):
            if b >= 1.0 and mid in METHODS and mid not in ids:
                recs.insert(0, method_brief(mid, why=f"匹配画像「{primary_p.name if primary_p else ''}」"))
                break
        recs = recs[:2]
    parts = [f"主错因「{primary}」。"]
    if primary_p:
        parts.append(f"画像「{primary_p.name}」：{primary_p.tip}")
    for m in recs:
        parts.append(f"· {m['name']}：{m['how']}")
    if tone:
        parts.append(f"风格：{tone}")
    return "\n".join(parts)


def list_catalog() -> list[dict]:
    """方法全目录（供前端「方法卡」或文档导出）。"""
    out = []
    for m in METHODS.values():
        out.append({
            "id": m.id, "name": m.name, "utility": m.utility,
            "summary": m.summary, "how": m.how, "avoid": m.avoid, "evidence": m.evidence,
        })
    order = {"high": 0, "medium": 1}
    out.sort(key=lambda x: (order.get(x["utility"], 9), x["name"]))
    return out
