"""成长手册引擎：真实院校政策库 × 情况模板 × 用户档案 → 个性化成长路径。

- 政策情报库：policy/ 目录下的策划文档（每条事实带官方来源 URL），启动后首次调用时
  解析 → 分块 → 向量化建立全局检索索引；
- 情况模板：重修逆袭 / 保研冲刺 / 跨考 / 竞赛特长等骨架，按用户档案自动匹配；
- 生成：政策检索结果 + 模板骨架 + 用户掌握度数据 → LLM 综合成结构化成长手册（Markdown），
  政策相关结论必须引用来源，未提供的信息标注"需核实"，不允许编造。
"""
import os

import numpy as np

from . import db, llm

POLICY_DIR = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy"))


# ---------- 政策情报库索引 ----------

def _policy_files() -> list[str]:
    files = []
    for name in sorted(os.listdir(POLICY_DIR)):
        p = os.path.realpath(os.path.join(POLICY_DIR, name))
        if name.endswith(".md") and p.startswith(POLICY_DIR + os.sep) and os.path.isfile(p):
            files.append(p)
    return files


def _read(path: str) -> str:
    fd = os.open(path, os.O_RDONLY)
    with os.fdopen(fd, encoding="utf-8") as f:
        return f.read()


def _chunk(text: str, size: int = 600) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = max(text.rfind("\n\n", start, end), text.rfind("。", start, end))
            if cut > start + size // 2:
                end = cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = end - 80
    return chunks


_index: list[dict] | None = None


def _get_index() -> list[dict]:
    global _index
    if _index is not None:
        return _index
    entries = []
    for path in _policy_files():
        title = os.path.basename(path)[:-3]
        text = _read(path)
        for chunk in _chunk(text):
            entries.append({"text": chunk, "source": title, "vec": None})
    if entries:
        vecs = llm.embed([e["text"] for e in entries])
        for e, v in zip(entries, vecs):
            e["vec"] = np.array(v, dtype=np.float32)
    _index = entries
    return _index


def retrieve_policy(query: str, top_k: int = 10) -> list[dict]:
    entries = _get_index()
    if not entries:
        return []
    q = np.array(llm.embed([query])[0], dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-9)
    scored = []
    for e in entries:
        v = e["vec"] / (np.linalg.norm(e["vec"]) + 1e-9)
        scored.append((float(q @ v), e))
    scored.sort(key=lambda x: -x[0])
    return [{"text": e["text"], "source": e["source"], "score": round(s, 3)} for s, e in scored[:top_k]]


# ---------- 情况模板 ----------

SITUATIONS = {
    "retake": {
        "label": "重修/挂科逆袭",
        "match": lambda p: bool({"重修", "挂科", "补考"} & set(p.get("flags", []))),
        "skeleton": (
            "0. 现状止损：核对毕业与学位双证要求，列出剩余重修/补考课程与时间窗（保毕业是第一优先级）；"
            "1. 路线判定：本校推免口径若按正考成绩排名，重修后保研概率极低 → 主攻考研统考线，"
            "复试短板用竞赛/科研/论文对冲；"
            "2. 成绩趋势重建：此后每学期打造'高分趋势'（大面积 85+ 课程），复试审查时用趋势说明成长性；"
            "3. 初试护城河：数学与专业课提前一轮启动，用初试高分对冲复试成绩单劣势；"
            "4. 复试对冲杠杆：进本校课题组 + 高价值竞赛 + 1 篇论文/专利在投。"),
    },
    "baoyan": {
        "label": "保研/推免冲刺",
        "match": lambda p: ("前10%" in p.get("rank_hint", "") or "前20%" in p.get("rank_hint", "")
                            or "推免" in p.get("goal_type", "")),
        "skeleton": (
            "0. 推免资格核对：对照本校推免细则的排名口径/外语/学期成绩硬门槛，逐条自检；"
            "1. 排名保卫：剩余学期选课策略与分数策略；"
            "2. 夏令营路线：大三暑期目标院校夏令营申请材料（成绩单+排名证明+英语+论文/竞赛）；"
            "3. 预推免与九月推免双保险；"
            "4. 统考兜底：若推免失败，无缝转入考研复习（公共课提前铺垫）。"),
    },
    "cross": {
        "label": "跨考补课",
        "match": lambda p: bool({"跨考", "跨专业"} & set(p.get("flags", []))),
        "skeleton": (
            "0. 专业课差距清单：对照目标专业核心课程（力学/机械/控制平台）列补修清单；"
            "1. 辅修/选修对冲：本校辅修 2-3 门核心课；"
            "2. 项目对冲：用已有能力（软件/AI）做目标专业的交叉项目；"
            "3. 专业课初试提前一轮；"
            "4. 复试专业素养呈现策略。"),
    },
    "default": {
        "label": "稳健统考",
        "match": lambda p: True,
        "skeleton": (
            "0. 目标拆解：初试科目与分数线、招生人数、复试权重；"
            "1. 三轮复习节奏（基础→强化→真题）；"
            "2. 竞赛与科研按边际收益选择性参与；"
            "3. 复试材料提前半年集成。"),
    },
}


def _pick_situations(profile: dict) -> list[dict]:
    hits = [t for k, t in SITUATIONS.items() if k != "default" and t["match"](profile)]
    if not hits:
        hits = [SITUATIONS["default"]]
    hits.append(SITUATIONS["default"])
    return hits


# ---------- 生成 ----------

def _weak_context(space_id: str) -> str:
    if not space_id or not db.get_space(space_id):
        return "（未关联课程空间，无法读取学习状态）"
    weak = db.weak_points(space_id, 8)
    m = db.list_mastery(space_id)
    if not m:
        return "（该空间暂无掌握度数据）"
    status_cn = {"weak": "薄弱", "learning": "学习中", "mastered": "已掌握"}
    lines = [f"- {w['point']}（掌握度 {int(w['score']*100)}%，{status_cn.get(w['status'], w['status'])}）" for w in weak]
    due = db.due_points(space_id)
    if due:
        lines.append("- 到期待复习：" + "、".join(p["point"] for p in due[:6]))
    return "\n".join(lines)


def generate(space_id: str, profile: dict) -> dict:
    # 请求留空的字段自动回填已保存的个人档案（「个人档案」页维护）
    saved = db.get_student_profile()
    profile = dict(profile)
    for key in ("current_school", "major", "year", "rank_hint",
                "goal_type", "target_school", "target_major", "timeline", "notes"):
        if not (profile.get(key) or "").strip():
            profile[key] = saved.get(key, "")
    if not [f for f in (profile.get("flags") or []) if f and f.strip()]:
        profile["flags"] = saved.get("flags", [])

    current_school = (profile.get("current_school") or "").strip() or "本校"
    target_school = (profile.get("target_school") or "").strip() or "目标院校"
    target_major = (profile.get("target_major") or "").strip()
    year = (profile.get("year") or "").strip()
    rank_hint = (profile.get("rank_hint") or "").strip()
    flags = [f.strip() for f in (profile.get("flags") or []) if f and f.strip()]
    goal_type = (profile.get("goal_type") or "").strip()
    timeline = (profile.get("timeline") or "").strip()
    notes = (profile.get("notes") or "").strip()

    query = " ".join([current_school, year, " ".join(flags), target_school, target_major,
                      goal_type, "重修 推免 招生 复试 竞赛 科研"])
    try:
        hits = retrieve_policy(query, top_k=10)
    except Exception:
        hits = []  # 嵌入模型不可用时降级为无政策上下文，不阻塞手册生成
    policy_ctx = "\n\n".join(
        f"[政策{i}｜来源: {h['source']}]\n{h['text']}" for i, h in enumerate(hits, 1)) \
        or "（政策库检索暂不可用，政策相关结论请自行核实官方来源）"
    situations = _pick_situations({"flags": flags, "rank_hint": rank_hint, "goal_type": goal_type})
    skeleton = "\n".join(f"【{t['label']}】骨架：\n{t['skeleton']}" for t in situations)
    weak_ctx = _weak_context(space_id)

    system = (
        "你是严谨的升学战略顾问。基于【政策依据】中的真实院校规则（含官方来源文件名）为用户生成"
        "《成长手册》。要求：\n"
        "1. 政策相关的每个关键结论后必须标注来源，如 [政策2]；政策依据中没有的信息不得编造，"
        "标注为（需自行核实：去哪里查、查什么）；\n"
        "2. 按【模板骨架】的路线逻辑组织，但行动项必须具体到学期/月份；\n"
        "3. 结合【当前学习状态】把薄弱知识点融入前两阶段的行动；\n"
        "4. 输出 Markdown，结构：一、现状诊断 / 二、路线判定（含依据） / 三、分阶段行动路线"
        "（按学期，含每阶段验收标准） / 四、竞争力补强清单（竞赛/科研/英语/材料） / "
        "五、风险与对冲 / 六、定期核对清单（要盯的官方信息与网址线索）。")
    user = (
        f"【用户档案】\n本科院校：{current_school}\n专业：{profile.get('major') or '未填'}\n"
        f"年级：{year or '未填'}\n成绩排名线索：{rank_hint or '未填'}\n"
        f"情况标签：{'、'.join(flags) if flags else '无'}\n"
        f"升学类型：{goal_type or '考研'}\n目标院校/专业：{target_school} {target_major}\n"
        f"关键时间线：{timeline or '未填'}\n补充说明：{notes or '无'}\n\n"
        f"【模板骨架】\n{skeleton}\n\n【当前学习状态（StudyPilot 掌握度）】\n{weak_ctx}\n\n"
        f"【政策依据】\n{policy_ctx}")

    content = llm.chat([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], temperature=0.4, max_tokens=4000, task="plan")

    title = f"{current_school}→{target_school}{target_major}成长手册"
    hid = db.save_handbook(title, profile, content, space_id if space_id and db.get_space(space_id) else "")
    return {"id": hid, "title": title, "content": content,
            "sources": sorted({h["source"] for h in hits})}


def list_handbooks() -> list[dict]:
    return db.list_handbooks()


def get_handbook(hid: str) -> dict | None:
    return db.get_handbook(hid)


def delete_handbook(hid: str) -> None:
    db.delete_handbook(hid)
