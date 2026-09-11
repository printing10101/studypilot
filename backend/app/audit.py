"""培养方案完成度审核（degree audit）。

把学生已修课程对照培养方案做三态核对（已修/修读中/缺失），全部确定性规则、无模型依赖：
- 要求课程集：官方课程组（含学分）→ 专业核心课 → 先修链课程，同名去重按优先级；
- 课程匹配：归一化精确 → 包含 → difflib 模糊（去括号说明后比对，容"（上）""（与XX二选一）"类漂移）；
- 学分进度：已修学分 / 毕业总学分；课程组含"（25学分必修）"字样时给出分组学分进度；
- 先修审核：修了后继但先修未修 → 违规清单；先修齐备但课程未修 → 「下学期可修」建议。
"""
from __future__ import annotations

import difflib
import re
from typing import Any

from . import db, syllabus

# 百分制 → 4.0 制绩点（常见口径，各校细则略有差异，仅供审核参考）
_PERCENT_GPA = [(90, 4.0), (85, 3.7), (82, 3.3), (78, 3.0), (75, 2.7),
                (72, 2.3), (68, 2.0), (64, 1.5), (60, 1.0)]
_GRADE_WORDS = {"优秀": 4.0, "优": 4.0, "良好": 3.0, "良": 3.0, "中等": 2.0, "中": 2.0,
                "及格": 1.0, "合格": 1.0, "通过": 1.0, "不及格": 0.0, "不合格": 0.0,
                "免修": 4.0, "通过免修": 4.0}
_LETTER_GPA = {"A+": 4.0, "A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0, "B-": 2.7,
               "C+": 2.3, "C": 2.0, "C-": 1.7, "D+": 1.3, "D": 1.0, "F": 0.0}


def norm_name(name: str) -> str:
    """课程名归一化：去括号说明、去空白、小写——"高等数学（上）"与"高等数学"可对上，
    但保留差异信息由调用方决定是否使用。"""
    t = re.sub(r"[（(][^（）()]*[）)]", "", name or "")
    t = re.sub(r"[\s·・]", "", t).lower()
    return t.strip()


def grade_to_gpa(grade: str) -> float:
    """成绩文本 → 4.0 制绩点；无法识别返回 -1。"""
    g = (grade or "").strip()
    if not g:
        return -1.0
    if g in _GRADE_WORDS:
        return _GRADE_WORDS[g]
    if g.upper() in _LETTER_GPA:
        return _LETTER_GPA[g.upper()]
    m = re.search(r"\d+(?:\.\d+)?", g)
    if m:
        raw = m.group()
        v = float(raw)
        if v <= 4.0:
            return round(v, 2)  # 4.0 制绩点原值（3.7 / 3.5 / 3）
        if v <= 5.0:
            # >4 不可能是 4.0 制绩点：按五级分制折算（优5/良4/中3/及格2 → 4/3/2/1）
            return round(min(v - 1.0, 4.0), 2)
        if 0 <= v <= 100:
            for floor, gpa in _PERCENT_GPA:
                if v >= floor:
                    return gpa
            return 0.0
    return -1.0


def _requirements(prog: dict) -> list[dict[str, Any]]:
    """从培养方案提取"要求课程集" [{name, base, category, credit, expected_term, source}]。
    同一课程以更权威来源为准：官方课程组 > 专业核心 > 先修链。"""
    reqs: dict[str, dict[str, Any]] = {}
    for g in prog.get("course_groups") or []:
        gname = (g.get("group") or "课程组").strip()
        m = re.search(r"(\d+(?:\.\d+)?)\s*学分", gname)
        gcredit = float(m.group(1)) if m else 0.0
        for c in g.get("courses") or []:
            n = (c.get("name") or "").strip()
            if not n:
                continue
            key = norm_name(n)
            if key and key not in reqs:
                reqs[key] = {"name": n, "base": key, "category": gname,
                             "credit": float(c.get("credit") or 0),
                             "group_credit": gcredit, "source": "groups"}
    for n in prog.get("core_courses") or []:
        key = norm_name(n)
        if key and key not in reqs:
            reqs[key] = {"name": n, "base": key, "category": "专业核心", "credit": 0.0,
                         "group_credit": 0.0, "source": "core"}
    for n in (prog.get("course_prereqs") or {}):
        key = norm_name(n)
        if key and key not in reqs:
            reqs[key] = {"name": n, "base": key, "category": "先修链基础课", "credit": 0.0,
                         "group_credit": 0.0, "source": "prereq"}
    term_expect: dict[str, str] = {}
    for sp in prog.get("semester_plan") or []:
        for n in sp.get("key_courses") or []:
            term_expect.setdefault(norm_name(n), (sp.get("term") or "").strip())
    for k, r in reqs.items():
        r["expected_term"] = term_expect.get(k, "")
    return list(reqs.values())


def _match_req(taken_name: str, reqs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """把已修课程名匹配到要求课程：精确（归一化）→ 相互包含 → 模糊 ≥0.65。"""
    q = norm_name(taken_name)
    if not q:
        return None
    for r in reqs:  # 精确
        if r["base"] == q:
            return r
    for r in reqs:  # 包含（"大学物理" 命中 "大学物理B(1)" 的基名）
        if r["base"] and (r["base"] in q or q in r["base"]):
            return r
    close = difflib.get_close_matches(q, [r["base"] for r in reqs if r["base"]], n=1, cutoff=0.65)
    if close:
        for r in reqs:
            if r["base"] == close[0]:
                return r
    return None


def run_audit(school: str = "", major: str = "") -> dict[str, Any]:
    """执行完成度审核。学校/专业缺省时回退个人档案。"""
    profile = db.get_student_profile() or {}
    school = (school or profile.get("current_school") or "").strip()
    major = (major or profile.get("major") or "").strip()

    prog = syllabus.program(school, major) if school and major else {}
    if not prog or prog.get("coverage") == "none":
        return {"program_found": False, "school": school, "major": major,
                "note": "没有可用的培养方案（可在上方选校/选专业或导入本校手册后再审核）",
                "taken_count": len(db.list_taken_courses())}

    reqs = _requirements(prog)
    taken = db.list_taken_courses()

    matched: dict[str, dict[str, Any]] = {}   # req base -> taken row
    unmatched: list[dict[str, str]] = []
    for t in taken:
        r = _match_req(t["name"], reqs)
        if r is None:
            unmatched.append({"name": t["name"], "credit": t["credit"],
                              "grade": t["grade"], "status": t["status"]})
            continue
        prev = matched.get(r["base"])
        # 同一要求多门已修（如重修/多学期）：已修优先，取成绩更好的
        if prev is None or (t["status"] == "done" and prev["status"] != "done"):
            matched[r["base"]] = t

    done_bases = {b for b, t in matched.items() if t["status"] == "done"}
    taking_bases = {b for b, t in matched.items() if t["status"] == "taking"}

    # ---- 核心要求三态 ----
    def _state(b: str) -> str:
        if b in done_bases:
            return "done"
        if b in taking_bases:
            return "taking"
        return "missing"

    core_states = [{"name": r["name"], "category": r["category"], "state": _state(r["base"]),
                    "expected_term": r["expected_term"],
                    "credit": (matched[r["base"]]["credit"] or r["credit"]) if r["base"] in matched else r["credit"],
                    "grade": matched[r["base"]]["grade"] if r["base"] in matched else ""}
                   for r in reqs]
    order = {"done": 0, "taking": 1, "missing": 2}
    core_states.sort(key=lambda x: (order[x["state"]], x["expected_term"] == "", x["expected_term"], x["name"]))

    # ---- 学分进度 ----
    credits_ref = prog.get("credits_reference") or {}
    total_required = float(credits_ref.get("毕业总学分") or 0)
    total_earned = 0.0
    for r in reqs:
        t = matched.get(r["base"])
        if t and t["status"] == "done":
            total_earned += float(t["credit"] or r["credit"] or 0)
    # 未匹配到要求课程的已修学分也计入总进度（通识/选修大量存在，不能丢）
    for u in unmatched:
        if u.get("status") != "taking":
            total_earned += float(u.get("credit") or 0)

    by_category: list[dict[str, Any]] = []
    seen_groups: dict[str, float] = {}
    for r in reqs:
        if r["source"] == "groups" and r["group_credit"]:
            seen_groups.setdefault(r["category"], r["group_credit"])
    for gname, gneed in seen_groups.items():
        earned = sum((matched[r["base"]]["credit"] or r["credit"] or 0)
                     for r in reqs if r["category"] == gname and r["base"] in done_bases)
        by_category.append({"category": gname, "required": gneed,
                            "earned": round(earned, 1),
                            "done": sum(1 for r in reqs if r["category"] == gname and r["base"] in done_bases),
                            "total": sum(1 for r in reqs if r["category"] == gname)})

    # ---- 先修审核 ----
    prereqs_map = prog.get("course_prereqs") or {}
    violations: list[dict[str, Any]] = []
    for r in reqs:
        pres = prereqs_map.get(r["name"]) or []
        if not pres or r["base"] not in done_bases:
            continue
        missing = []
        for p in pres:
            pb = norm_name(p)
            pr = _match_req(p, reqs)
            pb2 = pr["base"] if pr else pb
            if pb2 not in done_bases and pb2 not in taking_bases:
                missing.append(p)
        if missing:
            violations.append({"course": r["name"], "missing_prereqs": missing})

    # ---- 下学期可修：缺失且先修已齐 ----
    term_order = {sp.get("term", ""): i for i, sp in enumerate(prog.get("semester_plan") or [])}
    ready_next = []
    for r in reqs:
        if r["base"] in done_bases or r["base"] in taking_bases:
            continue
        pres = prereqs_map.get(r["name"]) or []
        missing_pres = []
        for p in pres:
            pr = _match_req(p, reqs)
            pb = pr["base"] if pr else norm_name(p)
            if pb not in done_bases and pb not in taking_bases:
                missing_pres.append(p)
        if not missing_pres:
            ready_next.append({"name": r["name"], "expected_term": r["expected_term"],
                               "credit": r["credit"]})
    ready_next.sort(key=lambda x: (term_order.get(x["expected_term"], 99), x["name"]))
    ready_next = ready_next[:12]

    # ---- GPA ----
    gpa_pairs = [(float(t["gpa"]), float(t["credit"] or r["credit"] or 0))
                 for b, t in matched.items()
                 if t["status"] == "done" and float(t.get("gpa") or -1) >= 0]
    for u in unmatched:
        if u.get("status") == "taking":  # 在修课无最终成绩，不计入 GPA
            continue
        g = grade_to_gpa(u.get("grade") or "")
        if g >= 0 and float(u.get("credit") or 0) > 0:
            gpa_pairs.append((g, float(u["credit"])))
    gpa = None
    if gpa_pairs and sum(c for _, c in gpa_pairs) > 0:
        gpa = round(sum(g * c for g, c in gpa_pairs) / sum(c for _, c in gpa_pairs), 2)

    counts = {"done": sum(1 for c in core_states if c["state"] == "done"),
              "taking": sum(1 for c in core_states if c["state"] == "taking"),
              "missing": sum(1 for c in core_states if c["state"] == "missing")}

    return {
        "program_found": True,
        "school": school, "major": prog.get("major") or major,
        "coverage": prog.get("coverage", ""),
        "taken_count": len(taken),
        "requirements": {"total": len(reqs), **counts},
        "core_states": core_states,
        "credits": {"total_required": total_required,
                    "total_earned": round(total_earned, 1),
                    "progress": round(total_earned / total_required, 3) if total_required else None,
                    "by_category": by_category},
        "gpa": gpa,
        "prereq_violations": violations,
        "ready_next": ready_next,
        "unmatched": unmatched[:20],
    }


# ---------- 成绩文本批量导入 ----------

_GRADE_TOKENS = {"优秀": 4.0, "优": 4.0, "良好": 3.0, "良": 3.0, "中等": 2.0, "中": 2.0,
                 "及格": 1.0, "合格": 1.0, "通过": 1.0, "不及格": 0.0, "不合格": 0.0,
                 "免修": 4.0, "A+": 4.0, "A": 4.0, "A-": 3.7, "B+": 3.3, "B": 3.0,
                 "B-": 2.7, "C+": 2.3, "C": 2.0, "C-": 1.7, "D": 1.0, "F": 0.0}
_STATUS_TOKENS = ("必修", "选修", "任选", "限选", "已修", "重修", "在修", "修读中", "通过", "主修")


def parse_courses_text(text: str) -> list[dict[str, Any]]:
    """规则解析粘贴的成绩单文本：每行一门课，token 分类。

    兼容「课程名 学分 成绩 学期」「课程名 成绩」「课程名 成绩 等级」等常见排布：
    学期用严格模式（2023-2024-1 / 大一上 / 第3学期）整体摘出，避免吃到课名；
    数字 token 按值域分账（≤10 的小数→学分，其余 0-100→成绩；两个数字时小的当学分）。
    """
    out = []
    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw.strip())
        if not line:
            continue
        status = "taking" if re.search(r"修读中|在修|进行中|本学期", line) else "done"

        # 1) 学期（严格模式，整体摘出）
        semester = ""
        for p in (r"\d{4}\s*[-–~]\s*\d{4}(?:\s*[-–~]\s*\d{1,2})?(?:学期)?",
                  r"大\s*[一二三四五六]\s*[上下](?:学期)?",
                  r"第\s*[一二三四五六七八九十\d]+\s*学期"):
            m = re.search(p, line)
            if m:
                semester = re.sub(r"\s+", "", m.group())
                line = (line[:m.start()] + " " + line[m.end():]).strip()
                break

        # 2) 逐 token 分类
        numbers: list[float] = []
        credit = 0.0
        grade = ""
        name_tokens: list[str] = []
        for tok in line.split(" "):
            tok = tok.strip(" ,，、;；.。|｜*×")
            if not tok:
                continue
            m = re.fullmatch(r"(\d+(?:\.\d+)?)学分", tok)
            if m:  # 「5学分」连写
                credit = float(m.group(1))
                continue
            if re.fullmatch(r"\d+(?:\.\d+)?", tok):
                numbers.append(float(tok))
                continue
            if tok in _GRADE_TOKENS and not grade:
                grade = tok
                continue
            if tok in _STATUS_TOKENS or tok in ("学分", "成绩"):
                continue
            name_tokens.append(tok)

        # 3) 数字分账：≤10 的小数优先当学分；两个数字时小者学分、另一者成绩
        nums = list(numbers)
        decimals = [v for v in nums if 0 < v <= 10 and not v.is_integer()]
        if decimals:
            credit = decimals[0]
            nums.remove(decimals[0])
        elif len(nums) >= 2:
            smalls = [v for v in nums if 0 < v <= 10]
            if smalls:
                credit = smalls[0]
                nums.remove(smalls[0])
        if not grade and nums and 0 <= nums[0] <= 100:
            v = nums[0]
            grade = str(int(v)) if v.is_integer() else str(v)
            nums = nums[1:]
        if not credit:
            for v in nums:  # 成绩已定后的剩余小数字当学分（如「马原 良好 3」）
                if 0 < v <= 10:
                    credit = v
                    break

        # 4) 名字重组：CJK 相邻不加空格，其余以空格连接
        name = ""
        for tok in name_tokens:
            if name and re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]+", tok) \
                    and re.fullmatch(r"[\u4e00-\u9fff]", name[-1]) \
                    and re.fullmatch(r"[\u4e00-\u9fff]", tok[0]):
                name += tok
            else:
                name += (" " if name else "") + tok
        name = name.strip()
        if len(name) < 2:
            continue
        out.append({"name": name[:100], "credit": credit, "grade": grade,
                    "semester": semester, "status": status})
    return out


def import_courses_text(text: str) -> dict[str, Any]:
    """批量导入已修课程：规则优先，解析少于 2 门时 LLM 兜底。返回 {added, method}。"""
    rows = parse_courses_text(text)
    method = "rules"
    if len(rows) < 2:
        try:
            from . import llm
            data = llm.chat_json([
                {"role": "system", "content": (
                    "你是大学成绩单解析器。从文本中抽取全部已修/在修课程。"
                    "输出严格 JSON：{\"courses\":[{\"name\":\"课程名\",\"credit\":学分数字(未知填0),"
                    "\"grade\":\"成绩原文(如 92/优秀/A-，未知填空)\",\"semester\":\"学期(未知填空)\","
                    "\"status\":\"done或taking\"}]}，不要编造，不要多余文字。")},
                {"role": "user", "content": text[:12000]},
            ], temperature=0.1, max_tokens=2600, task="extract")
            courses = data.get("courses") if isinstance(data, dict) else data
            rows = [{"name": str(r.get("name") or "").strip(), "credit": float(r.get("credit") or 0),
                     "grade": str(r.get("grade") or "").strip(), "semester": str(r.get("semester") or "").strip(),
                     "status": "taking" if str(r.get("status") or "") == "taking" else "done"}
                    for r in (courses or []) if isinstance(r, dict) and (r.get("name") or "").strip()]
            method = "llm"
        except Exception:
            pass
    if not rows:
        raise ValueError("没有解析出课程：每行写「课程名 学分 成绩 学期」，如「高等数学 5 92 大一上」")
    added = 0
    for r in rows:
        try:
            db.add_taken_course(**r)
            added += 1
        except (ValueError, TypeError):
            continue
    return {"added": added, "method": method}
