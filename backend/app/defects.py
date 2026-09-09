"""知识缺陷诊断引擎。

算法构成：
1. BKT 掌握度（db.adjust_mastery）：每次测验/反馈证据经贝叶斯知识追踪更新 P(已掌握)；
2. 遗忘衰减（db.estimate_retention）：按复习盒对应的半衰期估算"此刻还记得多少"；
3. 前置依赖风险传播：知识点依赖边（来自讲义抽取或内置课程图谱）上做松弛传播——
   前置薄弱会拖累后继的有效掌握度，缺陷沿依赖链向下游传播；
4. 修复顺序：在薄弱子图上按依赖拓扑 + 有效掌握度升序排出生效最高的补漏顺序
   （先补根因，再回到被拖累的后继）。
"""
import difflib
import json
import os

from . import db

CURRICULUM_DIR = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "curriculum"))

_PREREQ_CONTAGION = 0.6   # 前置缺陷向后继传播的强度系数
_RELAX_PASSES = 3         # 风险传播松弛轮数（覆盖链式依赖）


# ---------- 内置课程知识点图谱 ----------

def list_curriculums() -> list[dict]:
    out = []
    if os.path.isdir(CURRICULUM_DIR):
        for name in sorted(os.listdir(CURRICULUM_DIR)):
            if name.endswith(".json"):
                try:
                    data = json.loads(open(os.path.join(CURRICULUM_DIR, name), encoding="utf-8").read())
                    out.append({"file": name, "course": data.get("course", name),
                                "concepts": len(data.get("concepts", []))})
                except (ValueError, OSError):
                    continue
    return out


def load_curriculum(name: str) -> dict:
    p = os.path.realpath(os.path.join(CURRICULUM_DIR, name))
    if not p.startswith(CURRICULUM_DIR + os.sep) or not os.path.isfile(p):
        raise ValueError("课程图谱不存在")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _match_point(concept: str, points: list[str], cache: dict) -> str | None:
    """把内置图谱的概念名模糊匹配到空间已有知识点（子串包含或相似度≥0.55）。"""
    if concept in cache:
        return cache[concept]
    best, best_r = None, 0.0
    for p in points:
        if concept in p or p in concept:
            best, best_r = p, 1.0
            break
        r = difflib.SequenceMatcher(None, p, concept).ratio()
        if r > best_r:
            best, best_r = p, r
    hit = best if best_r >= 0.55 else None
    cache[concept] = hit
    return hit


def match_curriculum_edges(space_id: str) -> int:
    """把内置课程图谱与空间知识点模糊匹配，落入 curriculum 来源的依赖边。幂等。"""
    points = [p["point"] for p in db.list_mastery(space_id)]
    if not points:
        return 0
    cache: dict = {}
    edges = []
    seen = set()
    for info in list_curriculums():
        data = load_curriculum(info["file"])
        for con in data.get("concepts", []):
            to = _match_point(con.get("point", ""), points, cache)
            if not to:
                continue
            for pre in con.get("prereqs", []):
                frm = _match_point(pre, points, cache)
                if not frm or frm == to:
                    continue
                key = (frm, to)
                if key not in seen:
                    seen.add(key)
                    edges.append({"from": frm, "to": to})
    return db.set_space_edges(space_id, edges, "curriculum")


# ---------- 缺陷诊断 ----------

def _prereq_map(edges: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in edges:
        out.setdefault(e["to_point"], []).append(e["from_point"])
    return out


def _downstream_map(edges: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for e in edges:
        out.setdefault(e["from_point"], []).append(e["to_point"])
    return out


def _error_type_stats(space_id: str, point: str) -> dict[str, int]:
    """从历史判卷结果里聚合该知识点的错因类型（错题记录中 knowledge_point 模糊匹配）。"""
    stats: dict[str, int] = {}
    for q in db.list_quizzes(space_id):
        for a in q["answers"]:
            kp = a.get("knowledge_point", "")
            if a.get("verdict") == "对" or not kp:
                continue
            if difflib.SequenceMatcher(None, kp, point).ratio() >= 0.5:
                et = (a.get("error_type") or "").strip()
                if et:
                    stats[et] = stats.get(et, 0) + 1
    return stats


def diagnose(space_id: str) -> dict:
    points = db.list_mastery(space_id)
    edges = db.list_edges(space_id)
    prereqs = _prereq_map(edges)
    downstream = _downstream_map(edges)
    by_name = {p["point"]: p for p in points}
    t = db.now()

    # 有效掌握度松弛传播：eff = p_known × (1 - 0.6 × max(1 - eff(前置)))
    eff = {p["point"]: p["score"] for p in points}
    for _ in range(_RELAX_PASSES):
        new_eff = dict(eff)
        for name in eff:
            ups = [eff[u] for u in prereqs.get(name, []) if u in eff]
            if ups:
                inherited = 1.0 - min(ups)
                new_eff[name] = eff[name] * (1 - _PREREQ_CONTAGION * inherited)
        eff = {k: max(0.0, min(1.0, v)) for k, v in new_eff.items()}

    diagnosed = []
    for p in points:
        if p["status"] == "mastered":
            continue
        name = p["point"]
        ups = [u for u in prereqs.get(name, []) if u in eff]
        inherited = (1.0 - min(eff[u] for u in ups)) if ups else 0.0
        p_known = p["score"]
        retention = db.estimate_retention(p_known, p["box"], p["updated_at"], t)
        risk = 1.0 - p_known * (1 - _PREREQ_CONTAGION * inherited)
        weak_ups = [{"point": u, "p_known": by_name[u]["score"], "status": by_name[u]["status"],
                     "eff": round(eff[u], 3)} for u in ups if eff[u] < 0.75]
        hit_down = [d for d in downstream.get(name, [])
                    if d in by_name and by_name[d]["status"] != "mastered"]
        note_parts = []
        if weak_ups:
            worst = min(weak_ups, key=lambda x: x["p_known"])
            note_parts.append(f"前置「{worst['point']}」薄弱（{int(worst['p_known'] * 100)}%），先补根因")
        if retention < 0.5 and p_known >= 0.6:
            note_parts.append("遗忘明显，安排一次复习比学新内容收益更高")
        if p["wrong"] >= 2 and p["wrong"] >= p["correct"]:
            note_parts.append(f"已错 {p['wrong']} 次，进入重点盯防")
        diagnosed.append({
            "point": name,
            "p_known": round(p_known, 3),
            "eff_known": round(eff[name], 3),
            "retention": retention,
            "risk": round(risk, 3),
            "inherited_risk": round(inherited, 3),
            "prereqs": weak_ups,
            "downstream": hit_down,
            "evidence": {
                "attempts": p["attempts"], "wrong": p["wrong"], "correct": p["correct"],
                "box": p["box"], "due_in_hours": round((p["due_at"] - t) / 3600.0, 1),
                "error_types": _error_type_stats(space_id, name),
            },
            "note": "；".join(note_parts),
        })

    diagnosed.sort(key=lambda d: (-d["risk"], d["p_known"]))
    diagnosed = diagnosed[:15]

    # 修复顺序：薄弱子图上按依赖拓扑 + 有效掌握度升序（根因优先）
    weak_names = {d["point"] for d in diagnosed}
    done, order = set(), []
    while weak_names - done:
        candidates = [n for n in weak_names - done
                      if all(u not in weak_names or u in done for u in prereqs.get(n, []))]
        if not candidates:  # 依赖成环：按有效掌握度最低打破僵局
            candidates = list(weak_names - done)
        nxt = min(candidates, key=lambda n: eff.get(n, 0))
        order.append(nxt)
        done.add(nxt)

    # 依赖链：沿"最薄弱前置"向上回溯，展示缺陷的根因路径
    chains = []
    for d in diagnosed[:8]:
        chain, cur, guard = [d["point"]], d["point"], 0
        while guard < 5:
            ups = [u for u in prereqs.get(cur, []) if u in eff and eff[u] < 0.75]
            if not ups:
                break
            cur = min(ups, key=lambda u: eff[u])
            if cur in chain:
                break
            chain.append(cur)
            guard += 1
        if len(chain) > 1:
            chains.append(list(reversed(chain)))

    return {
        "has_graph": bool(edges),
        "edge_count": len(edges),
        "repair_order": order,
        "chains": chains,
        "points": diagnosed,
    }
