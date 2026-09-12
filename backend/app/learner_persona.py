"""学习者人格画像：显式勾选 + 行为推断 → 方法调制。

刻意不用已被证伪的 VARK「学习风格」，改用可操作的个体差异维度
（拖延启动、过度自信、冲动速答、焦虑易疲劳、冲刺突击、完美卡住、
概念深挖、刷题程序型、依赖外部结构、好奇发散）。

画像只调制「怎么教/怎么排期/语气」，不改变高工具性方法本身
（检索与间隔对所有画像都有效）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import db, fatigue


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    blurb: str                 # 一句话画像
    # 方法 id → 加分（正数前置，负数后置）
    method_boost: dict[str, float] = field(default_factory=dict)
    tip: str = ""              # 画像专属提示句
    session: str = ""          # 会话结构建议
    planner_rules: str = ""    # 注入规划师的额外规则
    tone: str = ""             # 语气/反馈风格


PERSONAS: dict[str, Persona] = {
    "crammer": Persona(
        id="crammer",
        name="冲刺突击型",
        blurb="习惯考前集中轰炸，平时欠复习债，短期会了长期易忘。",
        method_boost={"spacing": 1.2, "session_structure": 0.8, "metacognition": 0.5, "retrieval": 0.4},
        tip="把周末 4 小时突击拆成 6 天×40 分钟：每天只清当日到期，比考前连刷更稳。",
        session="每天固定 40 分钟：10 分钟到期检索 → 20 分钟一个新点 → 10 分钟闭卷回忆。",
        planner_rules="任务必须写成可每日打卡的小步（≤40 分钟），禁止「本周复习完第三章」这类周末一次性大块。",
        tone="强调「债要每天还一点」，避免只在考前施压。",
    ),
    "procrastinator": Persona(
        id="procrastinator",
        name="拖延启动型",
        blurb="不是学不会，而是迟迟开不了桌；一旦开始往往能推进。",
        method_boost={"session_structure": 1.0, "generation": 0.6, "worked_example": 0.5, "spacing": 0.3},
        tip="用「5 分钟启动仪式」：只承诺做 1 道检索题或读 1 个例题，开始后再决定是否继续。",
        session="前 5 分钟必须产出可见物（1 题/1 句总结）；总时长先定 25 分钟，完成后再加。",
        planner_rules="每阶段第一条任务必须小到 10 分钟内可完成（启动钩子），后续再上量。",
        tone="降低启动门槛，多用「先做最小一步」而不是「必须完成整章」。",
    ),
    "overconfident": Persona(
        id="overconfident",
        name="过度自信型",
        blurb="重读几遍就觉得会了，自测正确率常低于自我评估。",
        method_boost={"metacognition": 1.2, "retrieval": 1.0, "desirable_difficulty": 0.6, "interleaving": 0.4},
        tip="学完先闭卷自测再翻书：预测正确率写下来，和实际分对照，偏差>20% 就降低「已会」判断。",
        session="每学一块立刻 3 题闭卷自测；未达 80% 不进入下一块。",
        planner_rules="验收标准必须是闭卷得分/能讲清楚，禁止「看懂了」「过一遍」这类主观验收。",
        tone="温和但坚定地要求证据，避免顺从其「我会了」的判断。",
    ),
    "impulsive": Persona(
        id="impulsive",
        name="冲动速答型",
        blurb="做得快但审题/计算失误多，策略选择常一步到位选错。",
        method_boost={"self_explain": 1.2, "error_analysis": 1.0, "session_structure": 0.7, "interleaving": 0.5},
        tip="做题强制「读题圈关键词 → 写关键步骤 → 再算」；错题先写错因层再改答案。",
        session="单次 40 分钟：前半慢审 2 题（逐步自我解释），后半交错 4 题限时。",
        planner_rules="任务里写明检查步骤（圈条件/验量纲/代回），验收含「零审题失误」。",
        tone="强调减速与检查，不要只夸速度。",
    ),
    "anxious": Persona(
        id="anxious",
        name="焦虑易疲劳型",
        blurb="挫败信号多、容易学崩；需要小步正反馈与可控难度。",
        method_boost={"session_structure": 1.0, "worked_example": 0.7, "retrieval": 0.5, "spacing": 0.5},
        tip="单次控制在 25–30 分钟；先做 1 道预测正确率≈75% 的 ZPD 题建立成功体验。",
        session="25 分钟一轮：热身会的题 → 一个样例 → 一道自测；累了立刻停，不加量。",
        planner_rules="阶段目标写「最小可完成」；避免连续高难任务；每阶段留缓冲日。",
        tone="先共情再给下一步，禁止「别人都能完成」式施压。",
    ),
    "perfectionist": Persona(
        id="perfectionist",
        name="完美卡住型",
        blurb="不做到「全懂」不愿推进，易在一个点上死磕过久。",
        method_boost={"desirable_difficulty": 0.8, "interleaving": 0.8, "session_structure": 0.6, "worked_example": 0.4},
        tip="时间盒：同一难点 20 分钟到点就交错到下一题，记下卡点次日再攻——间隔常比死磕有效。",
        session="20 分钟时间盒 × 2，盒间强制换知识点；收尾允许「80% 理解即可过」。",
        planner_rules="任务写明「到点切换」与「允许 80% 过关」，禁止无限加练同一题。",
        tone="正常化「暂时不完美」，把推进本身算作完成。",
    ),
    "concept_digger": Persona(
        id="concept_digger",
        name="概念深挖型",
        blurb="爱追问为什么、理论扎实，但计算与应试迁移偏弱。",
        method_boost={"interleaving": 1.0, "retrieval": 0.8, "generation": 0.5, "desirable_difficulty": 0.4},
        tip="追问之后必须跟 1 道计算/应用题：把「为什么」落到「怎么算/怎么选方法」。",
        session="40% 精读与追问 + 60% 交错应用题；每概念至少 1 道变式计算。",
        planner_rules="理论任务旁强制配应用验收（算出结果/做出选择），禁止只写读书笔记。",
        tone="肯定深度，同时温和要求输出可检验结果。",
    ),
    "procedure_drill": Persona(
        id="procedure_drill",
        name="刷题程序型",
        blurb="步骤题刷得多，但概念一换情境就不会，迁移差。",
        method_boost={"elaboration": 1.0, "feynman": 0.9, "dual_coding": 0.6, "interleaving": 0.5},
        tip="每 5 道程序题插入 1 次「为什么这样做」的口述/费曼；变式题优先于原题重刷。",
        session="刷题块里混 1 道概念简答或反例辨析，避免整晚同型题。",
        planner_rules="练习任务写明「含变式/含概念口述」，验收不只对答案还要求说理。",
        tone="从「多刷」转向「刷一道讲清楚一道」。",
    ),
    "structure_seeker": Persona(
        id="structure_seeker",
        name="依赖结构型",
        blurb="有清晰清单与截止日就稳，否则容易漂。",
        method_boost={"session_structure": 1.0, "spacing": 0.7, "metacognition": 0.3, "retrieval": 0.3},
        tip="每天开工只看「今日学习」清单，按到期复习→今日任务顺序做完即走，不临时加计划。",
        session="严格按清单顺序：到期检索 → 计划任务 → 可选拓展。",
        planner_rules="任务必须有明确截止日与可勾选验收；阶段边界清晰。",
        tone="强调清单闭环与打卡进度。",
    ),
    "curious": Persona(
        id="curious",
        name="好奇发散型",
        blurb="兴趣驱动、易被旁支吸引，主线进度飘忽。",
        method_boost={"interleaving": 0.7, "generation": 0.6, "session_structure": 0.8, "elaboration": 0.5},
        tip="发散时间盒：主线 30 分钟完成后，允许 10 分钟把旁支好奇记进「停车场」清单。",
        session="主线 30 分钟必须先完成到期/任务，再开探索块；探索结束前写 2 句回扣主线。",
        planner_rules="每阶段含「主线必做」与「可选探索」两类任务，探索不得挤占到期复习。",
        tone="保护好奇心，但用时间盒守住主线。",
    ),
}


@dataclass
class PersonaProfile:
    explicit: list[str] = field(default_factory=list)   # 档案勾选
    inferred: list[str] = field(default_factory=list)   # 行为推断
    evidence: list[str] = field(default_factory=list)   # 推断依据（可展示）
    primary: str = ""
    all_ids: list[str] = field(default_factory=list)

    def labels(self) -> list[str]:
        out = []
        for pid in self.all_ids:
            p = PERSONAS.get(pid)
            if p:
                out.append(p.name)
        return out


def list_catalog() -> list[dict]:
    return [{
        "id": p.id, "name": p.name, "blurb": p.blurb,
        "tip": p.tip, "session": p.session,
    } for p in PERSONAS.values()]


# ---------- 行为推断（零 LLM） ----------

def _error_mix(space_id: str) -> dict[str, int]:
    from collections import Counter
    stats: Counter[str] = Counter()
    # 取最近 10 次测验的错因（recent_quizzes 新→旧，SQL LIMIT 免全量 JSON 解析）
    for q in db.recent_quizzes(space_id, 10):
        for a in q.get("answers") or []:
            if a.get("verdict") != "对" and a.get("error_type"):
                stats[a["error_type"]] += 1
    return dict(stats)


def _fatigue_from_messages(space_id: str) -> float:
    try:
        msgs = db.recent_messages(space_id, 16)
        scores = [fatigue.detect_fatigue(m.get("content") or "") for m in msgs if m.get("role") == "user"]
        return max(scores) if scores else 0.0
    except Exception:
        return 0.0


def infer_personas(space_id: str) -> tuple[list[str], list[str]]:
    """从本空间行为推断画像 id 列表与证据说明。"""
    ids: list[str] = []
    evidence: list[str] = []
    points = db.list_mastery(space_id)
    if not points:
        return ids, evidence

    due = db.due_points(space_id)
    quizzes = [q for q in db.list_quizzes(space_id) if q.get("answers")]
    errs = _error_mix(space_id)
    total_err = sum(errs.values()) or 1

    # 冲刺/拖延：大量到期堆积
    if len(due) >= 5:
        ids.append("crammer")
        evidence.append(f"{len(due)} 个知识点积压到期，呈现突击/拖欠节奏")
    elif len(due) >= 3 and len(points) >= 8:
        ids.append("procrastinator")
        evidence.append("到期任务未及时清，启动偏迟")

    # 冲动速答：审题+计算占错因大头
    careless = errs.get("审题错误", 0) + errs.get("计算失误", 0)
    if careless / total_err >= 0.5 and careless >= 2:
        ids.append("impulsive")
        evidence.append("审题/计算失误占错因主因")

    # 概念型 vs 程序型
    concept_err = errs.get("概念误解", 0) + errs.get("记忆模糊", 0)
    if concept_err / total_err >= 0.6 and concept_err >= 2:
        ids.append("procedure_drill")
        evidence.append("概念/记忆类错因偏多，需从刷题转向说理")

    # 过度自信：测验少但薄弱点多，或测验正确率明显低于掌握分
    if points:
        avg = sum(p["score"] for p in points) / len(points)
        graded_acc = None
        if quizzes:
            hits = tot = 0
            for q in quizzes[:5]:
                for a in q.get("answers") or []:
                    tot += 1
                    if a.get("verdict") == "对":
                        hits += 1
            if tot >= 8:
                graded_acc = hits / tot
        if graded_acc is not None and avg - graded_acc >= 0.2:
            ids.append("overconfident")
            evidence.append(f"自我掌握分 {avg:.0%} 明显高于近测正确率 {graded_acc:.0%}")
        elif len(quizzes) <= 2 and avg >= 0.55 and len(points) >= 6:
            ids.append("overconfident")
            evidence.append("测验很少但掌握分偏高，可能高估自己")

    # 焦虑：疲劳信号
    fat = _fatigue_from_messages(space_id)
    if fat >= 0.4:
        ids.append("anxious")
        evidence.append(f"近期对话疲劳分 {fat:.1f}，需短会话与可控难度")

    # 完美主义：错题极多但尝试集中（反复改同一类）——用 wrong>=3 且 correct 少
    stuck = sum(1 for p in points if p["wrong"] >= 3 and p["correct"] <= 1)
    if stuck >= 2:
        ids.append("perfectionist")
        evidence.append("多个点反复错、推进停滞，可能卡点死磕")

    # 依赖结构：有计划任务且完成率尚可
    try:
        tasks = db.list_plan_tasks(space_id)
        if len(tasks) >= 4:
            done = sum(1 for t in tasks if t.get("done"))
            if done / len(tasks) >= 0.4:
                ids.append("structure_seeker")
                evidence.append("计划打卡参与度较高，适合清单驱动")
    except Exception:
        pass

    # 保序去重
    seen: list[str] = []
    for i in ids:
        if i not in seen:
            seen.append(i)
    return seen[:4], evidence[:5]


def resolve_profile(space_id: str = "") -> PersonaProfile:
    """合并档案勾选与行为推断；显式优先，推断补充。"""
    try:
        prof = db.get_student_profile()
    except Exception:
        prof = {}
    raw = prof.get("learner_personas") or []
    if isinstance(raw, str):
        raw = [raw]
    explicit = [p for p in raw if p in PERSONAS]

    inferred: list[str] = []
    evidence: list[str] = []
    if space_id:
        try:
            inferred, evidence = infer_personas(space_id)
        except Exception:
            inferred, evidence = [], []

    all_ids: list[str] = []
    for pid in explicit + inferred:
        if pid not in all_ids:
            all_ids.append(pid)

    # 主画像：显式第一个，否则推断第一个，否则默认结构型（温和）
    primary = explicit[0] if explicit else (inferred[0] if inferred else "structure_seeker")
    if not all_ids:
        all_ids = [primary]
    return PersonaProfile(explicit=explicit, inferred=[i for i in inferred if i not in explicit],
                          evidence=evidence, primary=primary, all_ids=all_ids)


def method_boost_map(profile: PersonaProfile) -> dict[str, float]:
    boost: dict[str, float] = {}
    for i, pid in enumerate(profile.all_ids):
        p = PERSONAS.get(pid)
        if not p:
            continue
        weight = 1.0 if i == 0 else 0.55  # 主画像权重更高
        for mid, v in p.method_boost.items():
            boost[mid] = boost.get(mid, 0.0) + v * weight
    return boost


def apply_boost(methods: list[dict], boost: dict[str, float]) -> list[dict]:
    """按画像加权重排方法；强推且未入选时补入首位。"""
    from . import learning_methods as lm

    def key(item: tuple[int, dict]):
        i, m = item
        return (-boost.get(m["id"], 0.0), i)

    ordered = [m for _, m in sorted(enumerate(methods), key=key)]
    existing = {m["id"] for m in ordered}
    for mid, b in sorted(boost.items(), key=lambda x: -x[1]):
        if b >= 1.0 and mid not in existing and mid in lm.METHODS:
            ordered.insert(0, lm.method_brief(mid, why="匹配你的学习者画像"))
            break
    return ordered


def persona_tip_block(profile: PersonaProfile) -> str:
    if not profile.all_ids:
        return ""
    lines = ["【学习者画像】"]
    for pid in profile.all_ids:
        p = PERSONAS.get(pid)
        if not p:
            continue
        src = "档案" if pid in profile.explicit else "行为"
        lines.append(f"- {p.name}（{src}）：{p.blurb}")
        if p.tip:
            lines.append(f"  建议：{p.tip}")
    if profile.evidence:
        lines.append("推断依据：" + "；".join(profile.evidence[:3]))
    return "\n".join(lines)


def planner_persona_rules(profile: PersonaProfile) -> str:
    rules = []
    for pid in profile.all_ids:
        p = PERSONAS.get(pid)
        if p and p.planner_rules:
            rules.append(f"- {p.name}：{p.planner_rules}")
    if not rules:
        return ""
    return "\n\n【人格画像适配（任务写法）】\n" + "\n".join(rules)


def daily_persona_line(profile: PersonaProfile) -> str:
    p = PERSONAS.get(profile.primary)
    if not p:
        return ""
    return f"画像「{p.name}」：{p.tip}"
