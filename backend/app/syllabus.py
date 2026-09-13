"""培养方案库（学涯规划）：

- 院校名录：syllabus/schools.json 收录全国 985/211 高校（含城市/地区/层次/优势专业）；
- 专业培养方案：syllabus/programs/*.json 收录主流专业的通用培养方案框架
  （学分结构 / 核心课先修链 / 分学期路径 / 保研考研就业竞赛出口），
  依据教育部教学质量国家标准与多校公开培养方案整理；
- 官方方案层：syllabus/overrides/*.json 收录已获官方全文的学校专业培养方案
  （文件名"学校-专业.json"，来源 URL 与 handbooks/ 下的全文文本一并记录），
  合并优先级高于通用模板；
- 本校校准：用户上传本校培养手册（PDF/图片/文本），LLM 抽取结构化培养方案存库
  （syllabus_custom 表），优先级最高——查看时按 模板 → 官方层 → 用户导入 逐层合并，
  上层有值的字段覆盖下层，`coverage` 字段明示数据构成。

扩展方式：仿照现有文件在 programs/ 增加专业 JSON、overrides/ 增加校级方案，
或直接在应用里导入本校手册，无需改代码。
"""
import difflib
import json
import os
import re

from . import db, llm

SYLLABUS_DIR = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "syllabus"))
PROGRAM_DIR = os.path.join(SYLLABUS_DIR, "programs")
OVERRIDE_DIR = os.path.join(SYLLABUS_DIR, "overrides")
HANDBOOK_DIR = os.path.join(SYLLABUS_DIR, "handbooks")

_PROGRAMS: dict[str, dict] | None = None
_SCHOOLS: list[dict] | None = None
_OVERRIDES: list[dict] | None = None


def _safe_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def _load_programs() -> dict[str, dict]:
    global _PROGRAMS
    if _PROGRAMS is None:
        progs = {}
        if os.path.isdir(PROGRAM_DIR):
            for name in sorted(os.listdir(PROGRAM_DIR)):
                if not name.endswith(".json"):
                    continue
                p = os.path.realpath(os.path.join(PROGRAM_DIR, name))
                if not p.startswith(PROGRAM_DIR + os.sep):
                    continue
                d = _safe_json(p)
                if d.get("major"):
                    progs[d["major"]] = d
        _PROGRAMS = progs
    return _PROGRAMS


def _load_overrides() -> list[dict]:
    """官方方案层：文件名"学校-专业.json"。返回 [{school, major, **data}]。"""
    global _OVERRIDES
    if _OVERRIDES is None:
        out = []
        if os.path.isdir(OVERRIDE_DIR):
            for name in sorted(os.listdir(OVERRIDE_DIR)):
                if not name.endswith(".json") or "-" not in name:
                    continue
                p = os.path.realpath(os.path.join(OVERRIDE_DIR, name))
                if not p.startswith(OVERRIDE_DIR + os.sep):
                    continue
                d = _safe_json(p)
                if d.get("school") and d.get("major"):
                    out.append(d)
        _OVERRIDES = out
    return _OVERRIDES


def _load_schools() -> list[dict]:
    global _SCHOOLS
    if _SCHOOLS is None:
        try:
            with open(os.path.join(SYLLABUS_DIR, "schools.json"), encoding="utf-8") as f:
                _SCHOOLS = json.load(f)["schools"]
        except (ValueError, OSError, KeyError):
            _SCHOOLS = []
    return _SCHOOLS


def _norm(text: str) -> str:
    """检索归一化：去空白/括号注记/专业(类/方向)后缀，全角转半角。"""
    t = (text or "").strip().lower()
    t = t.replace("（", "(").replace("）", ")")
    t = re.sub(r"\(.*?\)", "", t)
    t = re.sub(r"\s+", "", t)
    t = re.sub(r"(专业|类|方向)", "", t)
    return t


def stats() -> dict:
    schools = _load_schools()
    return {
        "schools": len(schools),
        "schools_985": sum(1 for s in schools if s.get("tier") == "985"),
        "programs": len(_load_programs()),
        "official": len(_load_overrides()),
        "custom": len(db.list_syllabus_custom()),
    }


def official_sources() -> list[dict]:
    """已收录官方培养方案层的学校专业清单（含来源与版本）。

    has_fulltext 如实标记全文文件是否就位：handbooks/ 目录需要用户按 source_url
    自行获取后放入，缺文件时不应向用户宣称"已收录官方全文"。"""
    out = []
    for o in _load_overrides():
        path = os.path.join(HANDBOOK_DIR, o.get("source_file") or "")
        has = bool(o.get("source_file") and os.path.realpath(path).startswith(HANDBOOK_DIR + os.sep)
                   and os.path.isfile(path))
        out.append({"school": o["school"], "major": o["major"],
                    "source_version": o.get("source_version", ""),
                    "source_url": o.get("source_url", ""),
                    "has_fulltext": has,
                    "sections": o.get("official_sections", [])})
    return out


# ---------- 院校查询 ----------

def list_schools(query: str = "", region: str = "", tier: str = "") -> list[dict]:
    q = _norm(query)
    out = []
    for s in _load_schools():
        if region and s.get("region") != region:
            continue
        if tier and s.get("tier") != tier:
            continue
        if q and q not in _norm(s["name"]) and not any(q in _norm(x) for x in s.get("strong", [])):
            continue
        out.append(s)
    return out


def _abbr_candidates(name: str) -> set[str]:
    """自动生成中文简称候选：如 四川大学→川大、华中科技大学→华科/华大…"""
    base = re.sub(r"(大学|学院|校区)$", "", (name or "").strip())
    base = re.sub(r"[（(].*?[)）]", "", base)
    if len(base) < 2:
        return set()
    cands = {base[0] + base[-1], base[:2]}
    cands |= {base[0] + c for c in base[1:]}
    if (name or "").strip().endswith("大学"):
        cands.add(base[0] + "大")  # 川大/天大/兰大/湖大…
    # 带类别后缀的常见形态：哈工大 / 西电 / 北邮 不完全覆盖，人工 abbr 兜底
    for kw in ("科技", "工业", "理工", "交通", "电子", "师范", "农业", "林业", "海洋", "矿业", "石油", "地质", "财经", "中医药"):
        if kw in base:
            cands.add(base[0] + kw[0])
    return {c for c in cands if len(c) >= 2}


_ABBR_MAP: dict[str, dict] | None = None


def _abbr_map() -> dict[str, dict]:
    """简称 → 学校（人工 abbr 优先覆盖自动候选）。"""
    global _ABBR_MAP
    if _ABBR_MAP is None:
        m: dict[str, dict] = {}
        for s in _load_schools():
            for c in _abbr_candidates(s["name"]):
                m.setdefault(c, s)  # 先到先得（985 在列表前部，优先占位）
            for c in s.get("abbr", []):
                m[c.strip().lower()] = s
        _ABBR_MAP = m
    return _ABBR_MAP


def find_school(name: str) -> dict | None:
    """按名称找学校：精确 → 简称/abbr → 去括号 → 模糊。"""
    if not (name or "").strip():
        return None
    schools = _load_schools()
    q = _norm(name)
    for s in schools:
        if _norm(s["name"]) == q:
            return s
    hit = _abbr_map().get((name or "").strip()) or _abbr_map().get((name or "").strip().lower())
    if hit:
        return hit
    stripped = _norm(re.sub(r"[（(].*?[)）]", "", name))
    for s in schools:
        if _norm(re.sub(r"[（(].*?[)）]", "", s["name"])) == stripped:
            return s
    close = difflib.get_close_matches(q, [_norm(s["name"]) for s in schools], n=1, cutoff=0.75)
    if close:
        for s in schools:
            if _norm(s["name"]) == close[0]:
                return s
    return None


# ---------- 专业匹配 ----------

def _match_program(major: str) -> tuple[str, dict] | tuple[None, None]:
    """把用户输入的专业名匹配到培养方案模板。返回 (模板主名, 模板)。"""
    if not (major or "").strip():
        return None, None
    progs = _load_programs()
    q = _norm(major)
    # 1) 主名精确
    for name, p in progs.items():
        if _norm(name) == q:
            return name, p
    # 2) 别名精确
    for name, p in progs.items():
        for a in p.get("aliases", []):
            if _norm(a) == q:
                return name, p
    # 3) 包含（“机械设计制造及其自动化”包含“机械工程”不成立，但“计算机科学与技术（拔尖）”包含成立）
    for name, p in progs.items():
        pn = _norm(name)
        if pn and (pn in q or q in pn):
            return name, p
    for name, p in progs.items():
        for a in p.get("aliases", []):
            an = _norm(a)
            if an and (an in q or q in an):
                return name, p
    # 4) 模糊
    close = difflib.get_close_matches(q, [_norm(n) for n in progs], n=1, cutoff=0.6)
    if close:
        for name, p in progs.items():
            if _norm(name) == close[0]:
                return name, p
    return None, None


def _match_override(school_name: str, major: str) -> dict | None:
    """在官方方案层里按学校+专业模糊匹配（专业名精确 → 别名 → 包含 → 模糊）。"""
    if not (major or "").strip():
        return None
    pool = [o for o in _load_overrides()
            if _norm(o["school"]) == _norm(school_name or "")]
    if not pool:
        return None
    q = _norm(major)
    for o in pool:  # 主名精确
        if _norm(o["major"]) == q:
            return o
    for o in pool:  # 别名精确
        for a in o.get("aliases", []):
            if _norm(a) == q:
                return o
    for o in pool:  # 包含
        on = _norm(o["major"])
        if on and (on in q or q in on):
            return o
        for a in o.get("aliases", []):
            an = _norm(a)
            if an and (an in q or q in an):
                return o
    close = difflib.get_close_matches(q, [_norm(o["major"]) for o in pool], n=1, cutoff=0.6)
    if close:
        for o in pool:
            if _norm(o["major"]) == close[0]:
                return o
    return None


# ---------- 培养方案合成 ----------

def program(school: str, major: str) -> dict:
    """合成某校某专业的培养方案，三层合并：通用模板 → 官方方案层 → 用户导入。

    上层有值的字段覆盖下层；`coverage` 明示数据构成，官方层带 source_url 可溯源，
    `has_fulltext` 表示附有官方全文文本（GET /api/syllabus/fulltext 读取）。
    """
    school_info = find_school(school)
    school_name = school_info["name"] if school_info else (school or "").strip()
    tpl_name, tpl = _match_program(major)
    major_name = major or (tpl_name or "")
    override = _match_override(school_name, major_name) if school_name and major_name else None
    custom = db.get_syllabus_custom(school_name, major_name) if school_name and major_name else None
    custom_data = (custom or {}).get("data") or {}
    custom_data.pop("aliases", None)  # 内部字段，不参与培养方案合并输出

    if not tpl and not override and not custom_data:
        out = {
            "school": school_name, "school_tier": (school_info or {}).get("tier", ""),
            "major": major_name, "matched_major": None, "coverage": "none",
            "note": "暂无该专业的结构化培养方案。可在下方导入本校培养手册（PDF/截图/文本），"
                    "系统会抽取学分结构、核心课程与学期安排；通用建议可先参考相近专业的规划逻辑。",
            "source_note": "",
        }
        if school_info:
            out["school_strong"] = school_info.get("strong", [])
        return out

    merged = dict(tpl or {})
    for layer in (override or {}, custom_data):  # 上层有值字段覆盖下层
        for k, v in layer.items():
            if v not in (None, "", [], {}):
                merged[k] = v
    merged["major"] = major_name or merged.get("major", "")
    merged["school"] = school_name
    merged["school_tier"] = (school_info or {}).get("tier", "")
    merged["matched_major"] = tpl_name
    flags = []
    if override:
        flags.append("official")
    if custom_data:
        flags.append("custom")
    if not override and not custom_data:
        flags.append("template")
    merged["coverage"] = "+".join(flags)
    merged["custom_source"] = (custom or {}).get("source", "") if custom_data else ""
    merged["official_source"] = bool(override)
    merged["has_fulltext"] = bool(override and _fulltext_path(override))
    if school_info:
        merged.setdefault("paths", {})
        merged["school_strong"] = school_info.get("strong", [])
    return merged


def _fulltext_path(override: dict) -> str | None:
    """解析官方方案全文路径：必须在 handbooks/ 目录内（source_file 含 .. 时拒绝）。"""
    src = override.get("source_file") or ""
    if not src:
        return None
    path = os.path.join(HANDBOOK_DIR, src)
    if not os.path.realpath(path).startswith(HANDBOOK_DIR + os.sep) or not os.path.isfile(path):
        return None
    return path


def full_text(school: str, major: str) -> dict:
    """读取官方方案层附带的全文文本（handbooks/<source_file>）。"""
    school_info = find_school(school)
    school_name = school_info["name"] if school_info else (school or "").strip()
    override = _match_override(school_name, major) if school_name else None
    if not override:
        return {}
    path = _fulltext_path(override)
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        text = f.read()
    return {"school": override["school"], "major": override["major"],
            "source_version": override.get("source_version", ""),
            "source_url": override.get("source_url", ""),
            "source_note": override.get("source_note", ""),
            "chars": len(text), "text": text}


def majors_for_school(school: str) -> dict:
    """某校可用的专业列表：官方层 + 模板覆盖 + 已导入的自定义专业 + 该校优势专业。"""
    school_info = find_school(school)
    school_name = school_info["name"] if school_info else school
    tpl_names = sorted(_load_programs().keys())
    override_majors = sorted(o["major"] for o in _load_overrides()
                             if _norm(o["school"]) == _norm(school_name or ""))
    custom = [r["major"] for r in db.list_syllabus_custom(school_name)]
    return {
        "school": school_name,
        "tier": (school_info or {}).get("tier", ""),
        "official_majors": override_majors,
        "template_majors": tpl_names,
        "custom_majors": custom,
        "strong": (school_info or {}).get("strong", []),
    }


def all_majors() -> list[str]:
    return sorted(_load_programs().keys())


# ---------- 导入本校培养手册 ----------

_IMPORT_FIELDS = ("major", "category", "degree", "duration_years", "credits_reference",
                  "training_goal", "core_courses", "course_prereqs", "semester_plan", "paths")


def import_handbook(school: str, major: str, text: str, source: str = "") -> dict:
    """把本校培养手册文本交给 LLM 抽取为结构化培养方案并入库。

    LLM 只负责抽取手册中出现的事实；抽取不到的字段留空，查看时回落通用模板。
    """
    school_info = find_school(school)
    school_name = school_info["name"] if school_info else (school or "").strip()
    if not school_name:
        raise ValueError("请先填写学校名称")
    text = (text or "").strip()
    if len(text) < 80:
        raise ValueError("手册文本太短（不足 80 字），无法可靠抽取培养方案")
    tpl_name, tpl = _match_program(major)
    major_hint = tpl_name or (major or "未知专业")

    data = llm.chat_json([
        {"role": "system", "content": (
            "你是教务处培养方案解析器。从给定培养手册文本中抽取结构化培养方案。要求：\n"
            "1. 只抽取文本中明确出现的信息，手册里没有的字段填 null，不要编造；\n"
            "2. credits_reference 是 {\"分类名\": 学分数字} 的扁平对象；\n"
            "3. core_courses 是核心课程名列表（保持手册原文命名）；\n"
            "4. course_prereqs 是 {\"后继课程\": [\"前置课程\", ...]}；\n"
            "5. semester_plan 是 [{\"term\":\"学期名\", \"key_courses\":[课程], "
            "\"milestone\":\"该学期要点\"}]，按手册实际的学期/学年安排来；\n"
            "6. paths 是保研/考研/就业/竞赛/出国相关的培养要求摘录，结构不限；\n"
            "7. 输出严格 JSON，键固定为：" + ", ".join(_IMPORT_FIELDS) + "，不要多余文字。")},
        {"role": "user", "content": (
            f"学校：{school_name}\n专业：{major_hint}\n\n【培养手册文本（可截断）】\n{text[:18000]}")},
    ], temperature=0.1, max_tokens=3000, task="extract")
    if not isinstance(data, dict):
        raise ValueError("培养方案抽取格式异常，请重试或换更清晰的文本")

    clean = {k: data.get(k) for k in _IMPORT_FIELDS}
    clean["major"] = (clean.get("major") or major_hint).strip() or major_hint
    clean["school"] = school_name
    # 记录用户原始输入与模板名作为别名：LLM 抽取的专业名可能与用户查询表述不一致，
    # 没有别名映射时会出现"导入成功但查询不生效"
    user_major = (major or "").strip()
    clean["aliases"] = sorted({user_major, tpl_name or ""} - {clean["major"], ""})
    clean["source_note"] = (f"由用户导入的本校培养手册抽取（{source or '手动粘贴'}），"
                            "字段仅含手册中明确出现的信息，未覆盖字段将在查看时回落通用模板。")
    db.save_syllabus_custom(school_name, clean["major"], clean, source=source)
    return {"school": school_name, "major": clean["major"],
            "coverage": "custom", "fields_found": [k for k in _IMPORT_FIELDS if clean.get(k) not in (None, "", [], {})]}
