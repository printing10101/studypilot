"""目标导向学习计划引擎（学涯规划）：

输入：个人档案（学校/专业/年级）+ 目标（保研/考研/就业/竞赛/出国/期末）+ 当前学期
+ 本学期课程表 + 培养方案（syllabus 合成）+ 跨空间掌握度薄弱点 + 升学政策库检索。

输出：结构化分阶段计划（总方针 + 阶段任务，任务含验收标准与关联课程），
存 career_plans 表可打卡；可一键同步到某课程空间的 plan_tasks 参与每日打卡闭环。

与「成长手册」（handbook.py：升学战略与院校政策）互补——本模块负责把战略翻译成
贴合培养方案与真实课表的学期级行动。
"""
import difflib
import json

from . import db, experts, handbook, llm, syllabus

GOALS = {
    "保研": "保持排名冲击推免资格：绩点保卫、夏令营材料、科研竞赛加成、九月推免与统考兜底",
    "考研": "围绕初试科目（公共课+专业课）三轮复习，兼顾本科课程不挂科与复试背景补强",
    "就业": "实习链条、技术栈/求职技能、项目与作品集、秋招春招节奏",
    "竞赛": "以学科竞赛为核心目标：组队、训练计划、赛程节点、与课程学习互相促进",
    "出国": "GPA+语言考试+科研/实习背景+申请材料时间线",
    "期末": "以本学期期末考试为核心：读课表安排复习优先级、考前三轮（过点-刷题-模拟）",
    "毕业": "完成毕业设计/论文与学分核对，平衡求职或升学过渡",
}


def _term_index(year: str) -> int:
    """把“大一上/大二下/三年级下”之类映射到 1~8 学期序号（解析不出返回 0）。"""
    t = (year or "").strip()
    m = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
    for ch in t:
        if ch in m:
            return max(1, min(m[ch] * 2 - (0 if "下" in t else 1), 8))
    return 0


def _pick_semester_plan(program: dict, year: str) -> list[dict]:
    """从培养方案的分学期序列里，取出当前学期及之后的规划。"""
    plan = program.get("semester_plan") or []
    cur = _term_index(year)
    if cur and len(plan) >= cur:
        return plan[cur - 1:]
    return plan


def _current_courses_ctx(term: str) -> tuple[str, list[str]]:
    if not term:
        return "（未提供本学期课程表，规划不排具体时段）", []
    rows = db.list_schedule(term)
    if not rows:
        return f"（学期“{term}”暂无课程表数据）", []
    day_cn = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}
    lines, names = [], []
    for r in rows:
        if r["course"] not in names:
            names.append(r["course"])
        slot = f"{day_cn.get(r['day'], '')}{('第' + r['period'] + '节') if r['period'] else ''}"
        extra = " / ".join(x for x in (r["weeks"], r["room"], r["teacher"]) if x)
        lines.append(f"- {r['course']}：{slot}{('（' + extra + '）') if extra else ''}")
    return "本学期课表：\n" + "\n".join(lines[:40]), names


def _weak_ctx() -> str:
    """跨空间薄弱点汇总（学涯规划是档案级功能，读全部空间）。"""
    lines = []
    for s in db.list_spaces():
        weak = db.weak_points(s["id"], 5)
        if weak:
            lines.append(f"【{s['name']}】薄弱："
                         + "、".join(f"{w['point']}({int(w['score']*100)}%)" for w in weak))
    if not lines:
        return "（各课程空间暂无掌握度数据——可在计划里预留日常测验与复习动作）"
    return "\n".join(lines[:8])


def _match_space_courses(spaces: list[dict], course_names: list[str]) -> dict[str, str]:
    """把课表课程名匹配到已有课程空间（供“同步到空间”与任务关联提示）。"""
    out = {}
    for c in course_names:
        close = difflib.get_close_matches(c, [s["name"] for s in spaces], n=1, cutoff=0.5)
        if close:
            for s in spaces:
                if s["name"] == close[0]:
                    out[c] = s["id"]
    return out


def generate(school: str, major: str, year: str, goal_type: str,
             target: str, term: str, horizon: str, space_id: str = "") -> dict:
    profile = db.get_student_profile()
    school = (school or "").strip() or profile.get("current_school", "")
    major = (major or "").strip() or profile.get("major", "")
    year = (year or "").strip() or profile.get("year", "")
    goal_type = (goal_type or "").strip() or profile.get("goal_type", "考研")
    target = (target or "").strip() or " ".join(
        x for x in (profile.get("target_school", ""), profile.get("target_major", "")) if x)
    horizon = (horizon or "本学期").strip()

    program = syllabus.program(school, major)
    sem_plan = _pick_semester_plan(program, year)
    courses_ctx, course_names = _current_courses_ctx(term)
    weak_ctx = _weak_ctx()
    goal_desc = GOALS.get(goal_type, goal_type)

    # 升学/就业政策补充（政策库有就注入，标注来源；没有不阻塞）
    policy_hits = handbook.retrieve_policy(f"{goal_type} {target} {school} {major} 时间线", top_k=4)
    policy_ctx = "\n\n".join(f"[政策{i}｜{h['source']}]\n{h['text']}" for i, h in enumerate(policy_hits, 1)) \
        or "（政策库暂无相关条目）"

    prog_ctx = {
        "matched_major": program.get("matched_major"),
        "coverage": program.get("coverage"),
        "degree": program.get("degree"),
        "credits_reference": program.get("credits_reference"),
        "core_courses": program.get("core_courses"),
        "remaining_semester_plan": sem_plan,
        "paths": program.get("paths"),
    }

    data = llm.chat_json([
        {"role": "system", "content": (
            "你是学涯规划教练。基于【培养方案】和【本学期课表】，为学生的目标制定可执行的"
            "分阶段学习计划。要求：\n"
            f"1. 目标导向：每个任务都应能看出它服务于目标（{goal_desc}）；\n"
            "2. 课表现实约束：在读课程按其重要性与目标相关度分配精力（日常任务写明对应课程）；"
            "利用培养方案的先修链安排自学顺序，不要建议跳过前置；\n"
            "3. 每阶段给 2-4 条任务：content 具体到动作与量（如“每周 LeetCode 5 题·数组双指针”），"
            "accept 是可检验的验收标准，course 填关联的在读课程名或“课外”；\n"
            "4. 结合【薄弱点】把补弱动作放进第一阶段；\n"
            "5. 政策相关结论在 markdown 中标注来源如 [政策1]，库里没有的写“需自行核实”；\n"
            "6. 输出严格 JSON：{\"summary\":\"总方针(60字内)\",\"phases\":[{\"name\":\"阶段名(含时间范围)\","
            "\"goal\":\"阶段目标\",\"tasks\":[{\"content\":\"\",\"accept\":\"\",\"course\":\"\"}]}]}，"
            "3-5 个阶段，不要多余文字。")},
        {"role": "user", "content": (
            f"【学生档案】学校：{school or '未填'}｜专业：{major or '未填'}｜当前年级：{year or '未填'}\n"
            f"【目标】{goal_type}｜去向：{target or '未定'}｜规划跨度：{horizon}\n\n"
            f"【培养方案（{program.get('coverage', 'none')}）】\n"
            f"{json.dumps(prog_ctx, ensure_ascii=False)[:6000]}\n\n"
            f"【本学期课表】\n"
            f"{courses_ctx[:2500]}\n\n"
            f"【各空间薄弱点】\n{weak_ctx}\n\n"
            f"【政策依据】\n{policy_ctx[:4000]}")},
    ], temperature=0.4, max_tokens=3000, task="plan")

    if isinstance(data, list):
        data = {"phases": data}
    if not isinstance(data, dict):
        raise ValueError("计划生成格式异常")
    tasks = []
    for phase in data.get("phases") or []:
        name = (phase.get("name") or "").strip()
        for t in phase.get("tasks") or []:
            content = (t.get("content") or "").strip()
            if not content:
                continue
            tasks.append({"id": db.new_id(), "phase": name, "content": content,
                          "accept": (t.get("accept") or "").strip(),
                          "course": (t.get("course") or "").strip()[:40],
                          "done": False, "done_at": 0})
    if not tasks:
        raise ValueError("计划生成格式异常：没有可用任务")

    lines = [f"## 学涯计划：{goal_type}{' → ' + target if target else ''}",
             f"**学校/专业**：{school or '未填'} {major or '未填'}｜**当前年级**：{year or '未填'}"
             f"｜**跨度**：{horizon}", f"**总方针**：{data.get('summary', '')}", ""]
    cur_phase = ""
    for t in tasks:
        if t["phase"] != cur_phase:
            cur_phase = t["phase"]
            lines.append(f"### {cur_phase}")
        lines.append(f"- [ ] {t['content']}" + (f"（验收：{t['accept']}）" if t["accept"] else "")
                     + (f"　关联课程：{t['course']}" if t["course"] else ""))
    lines.append("")
    lines.append(f"> 培养方案来源：{program.get('coverage', 'none')}（{program.get('source_note', '')}）")
    markdown = "\n".join(lines)

    title = f"{goal_type}·{major or '未定专业'}·{horizon}"
    pid = db.save_career_plan(title, {"school": school, "major": major, "goal_type": goal_type,
                                      "target": target, "term": term, "horizon": horizon},
                              data.get("summary", ""), tasks, markdown)
    return {"id": pid, "title": title, "summary": data.get("summary", ""),
            "tasks": tasks, "markdown": markdown,
            "course_spaces": _match_space_courses(db.list_spaces(), course_names)}


def push_to_space(pid: str, space_id: str, replace: bool = False) -> int:
    """把学涯计划的任务同步到课程空间 plan_tasks（默认追加，可选整体替换）。"""
    plan = db.get_career_plan(pid)
    if not plan:
        raise ValueError("计划不存在")
    if not db.get_space(space_id):
        raise ValueError("目标空间不存在")
    tasks = [{"phase": t["phase"], "content": t["content"],
              "accept": t.get("accept", ""), "points": [t.get("course")] if t.get("course") else []}
             for t in plan["tasks"] if not t.get("done")]
    if not tasks:
        raise ValueError("计划中没有未完成任务可同步")
    if replace:
        db.replace_plan_tasks(space_id, tasks)
    else:
        _append_plan_tasks(space_id, tasks)
    return len(tasks)


def _append_plan_tasks(space_id: str, tasks: list[dict]) -> None:
    c = db.get_conn()
    for t in tasks:
        c.execute("INSERT INTO plan_tasks(id,space_id,phase,content,accept,points,created_at) "
                  "VALUES(?,?,?,?,?,?,?)",
                  (db.new_id(), space_id, (t.get("phase") or "").strip()[:80],
                   (t.get("content") or "").strip(), (t.get("accept") or "").strip(),
                   json.dumps(t.get("points") or [], ensure_ascii=False), db.now()))
    c.commit()


def list_plans() -> list[dict]:
    return db.list_career_plans()


def get_plan(pid: str) -> dict | None:
    return db.get_career_plan(pid)


def toggle_task(pid: str, task_id: str, done: bool) -> dict | None:
    return db.toggle_career_task(pid, task_id, done)


def delete_plan(pid: str) -> None:
    db.delete_career_plan(pid)
