"""课程表导入与解析（学涯规划）：

支持三种来源，统一产出 [{course, day(1-7), period, weeks, teacher, room, kind}]：
- 图片（教务系统截图）：RapidOCR 离线识别 → 文本行解析；
- Excel/CSV（教务系统导出）：识别“周一~周日”表头网格，按列归日、按行归节次；
- 粘贴文本：逐行正则解析。

解析策略：规则优先（无模型依赖、可解释）；解析出少于 2 门课时尝试 LLM 兜底抽取；
全部结果在前端以可编辑周课表呈现，用户可以修正任何字段后保存。
"""
import csv
import re

from . import db, llm

DAYS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
DAY_RE = re.compile(r"(?:周|星期)([一二三四五六日天])")
PERIOD_RE = re.compile(r"(?:第\s*)?(\d{1,2}(?:\s*[-–~]\s*\d{1,2})?)\s*节")
WEEKS_RE = re.compile(r"第?\s*(\d{1,2}\s*[-–~]\s*\d{1,2}|\d{1,2})\s*周|(单周|双周)")
# 教室：楼栋前缀(1~5字，可带连字符) + 3~4 位数字（教三-301 / A101 / 东九A102 / 2-207）
ROOM_RE = re.compile(r"([\u4e00-\u9fa5A-Za-z]{1,5}[-–—]?)\s?(\d{3,4})(?:室|楼|厅|教)?(?![节周\d])")
NOISE = ("上午", "下午", "晚上", "课程名称", "课程表", "课表", "时间表", "第几节", "教师", "教室",
         "节次", "周次", "星期", "校区", "班级", "学分", "上课时间", "地点")
KINDS = ("必修", "选修", "实验", "实践")


def _norm_line(line: str) -> str:
    """轻清洗：统一全角括号/冒号、压缩多余空白；保留词间空格（分词与教室识别都依赖它）。"""
    t = (line or "").strip()
    t = t.replace("（", "(").replace("）", ")").replace("：", ":").replace("\u3000", " ")
    return re.sub(r"\s+", " ", t)


def parse_cell(text: str, day: int | None = None, period_hint: str = "") -> dict | None:
    """解析单个单元格/单行文本 → 一门课。解析不出课程名返回 None。"""
    t = _norm_line(text)
    if not t:
        return None
    rest = t

    day_m = DAY_RE.search(rest)
    if day_m:
        day = DAYS[day_m.group(1)]
        rest = rest[:day_m.start()] + rest[day_m.end():]

    period = period_hint
    p_m = PERIOD_RE.search(rest)
    if p_m:
        period = p_m.group(1).replace(" ", "").replace("–", "-").replace("~", "-")
        rest = rest[:p_m.start()] + rest[p_m.end():]

    weeks = ""
    w_m = WEEKS_RE.search(rest)
    if w_m:
        weeks = (w_m.group(1).replace(" ", "").replace("–", "-").replace("~", "-") + "周") if w_m.group(1) else w_m.group(2)
        rest = rest[:w_m.start()] + rest[w_m.end():]

    room = ""
    r_m = ROOM_RE.search(rest)
    if r_m:
        room = (r_m.group(1) + r_m.group(2)).replace(" ", "")
        rest = rest[:r_m.start()] + rest[r_m.end():]

    kind = next((k for k in KINDS if k in rest), "")
    if kind:
        # 课程性质词从行文中移除，避免被下面的教师名正则误认领（"数据结构 必修 王伟"）
        rest = rest.replace(kind, "", 1)

    # 剩余部分按空格分词：课程名取最长的有效词；教师名取另一段 2~4 字中文
    rest = rest.strip(" ,;，；.。:：/、|-")
    tokens = [x.strip(" ,;，；.。:：/、|-") for x in rest.split()]
    tokens = [x for x in tokens if x]
    name = ""
    for cand in sorted(tokens, key=len, reverse=True):
        if len(cand) < 2 or any(n in cand for n in NOISE):
            continue
        if re.fullmatch(r"[()（）0-9一二三四五六七八九十]+", cand):
            continue
        name = cand
        break
    if not name:
        return None
    teacher = ""
    for tok in tokens:
        if tok == name or len(tok) < 2 or any(n in tok for n in NOISE) or tok in KINDS:
            continue
        if re.fullmatch(r"[\u4e00-\u9fa5]{2,4}(?:老师|教授)?", tok):
            teacher = tok
            break
    return {"course": name, "day": day or 0, "period": period, "weeks": weeks,
            "teacher": teacher, "room": room, "kind": kind}


def parse_text(text: str) -> list[dict]:
    """逐行解析：星期列在 OCR 输出中经常整列连续出现，未知行沿用最近一次的星期。"""
    out, last_day = [], None
    for raw in re.split(r"[\n;；]+", text or ""):
        item = parse_cell(raw, day=last_day)
        if not item:
            continue
        if DAY_RE.search(_norm_line(raw)):
            last_day = item["day"]
        out.append(item)
    # 去重键含周次：单双周同节次的同名课是两条安排，不能合并（与 _dedupe 口径一致）
    return _dedupe(out)


# ---------- Excel / CSV 网格 ----------

def _day_of_header(text: str) -> int | None:
    m = DAY_RE.search(_norm_line(text))
    return DAYS[m.group(1)] if m else None


def parse_grid(rows: list[list[str]]) -> list[dict]:
    """解析二维表格：找到“周一..周日”表头行后按列归日；首列形如“1-2节”作为节次提示。"""
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [list(r) + [""] * (width - len(r)) for r in rows]

    header_row, day_cols = -1, {}
    for i, row in enumerate(rows[:8]):
        cols = {j: _day_of_header(c) for j, c in enumerate(row)}
        cols = {j: d for j, d in cols.items() if d}
        if len(cols) >= 3:
            header_row, day_cols = i, cols
            break

    out = []
    if header_row < 0:
        # 没有表头：把整表拍平成文本走逐行解析
        for row in rows:
            out.extend(parse_text(" ".join(str(c) for c in row if c)))
        return _dedupe(out)

    for i, row in enumerate(rows):
        if i <= header_row:
            continue
        period_hint = ""
        p_m = PERIOD_RE.search(_norm_line(str(row[0]))) if row else None
        if p_m:
            period_hint = p_m.group(1).replace(" ", "").replace("–", "-").replace("~", "-")
        for j, cell in enumerate(row):
            if j not in day_cols or not str(cell).strip():
                continue
            # 单元格内可能纵向堆 2 门课（大节/单双周分行）
            for part in re.split(r"[\n;；]{1,2}", str(cell)):
                item = parse_cell(part, day=day_cols[j], period_hint=period_hint)
                if item:
                    out.append(item)
    return _dedupe(out)


def parse_xlsx(path: str) -> list[dict]:
    try:
        import openpyxl
    except ImportError as e:
        raise ValueError("读取 Excel 需要 openpyxl（backend 目录取 uv sync 安装）") from e
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = [[("" if c is None else str(c)) for c in row] for row in ws.iter_rows(values_only=True)]
    wb.close()
    return parse_grid(rows)


def parse_csv(path: str) -> list[dict]:
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with open(path, encoding=enc, newline="") as f:
                return parse_grid([row for row in csv.reader(f)])
        except (UnicodeDecodeError, ValueError):
            continue
    raise ValueError("CSV 编码无法识别（支持 UTF-8 / GBK）")


# ---------- WakeUp 课程表格式直连（社区通用导入/备份格式） ----------

_WAKEUP_JSON_KEYS = ("courseName", "name", "课程名", "course")


def parse_wakeup_rows(rows: list[list[str]]) -> list[dict] | None:
    """WakeUp CSV 行解析：`课程名,星期(1-7),开始节次,结束节次,教师,地点,周次`。

    带表头（课程名称/星期/…，含「节次」合并列写法）或无表头均可。
    返回 None 表示不是 WakeUp 行格式（交回通用网格解析）。
    """
    if not rows:
        return None

    def _col(headers: list[str], *keys: str) -> int:
        for k in keys:
            for j, h in enumerate(headers):
                if k in h:
                    return j
        return -1

    start, colmap = 0, {}
    head = [_norm_line(str(c)) for c in rows[0]]
    if any("课程名称" in h or h == "课程名" for h in head):
        start = 1
        colmap = {
            "name": _col(head, "课程名称", "课程名", "name"),
            "day": _col(head, "星期", "周几"),
            "start": _col(head, "开始节次", "start"),
            "end": _col(head, "结束节次", "end"),
            "period": _col(head, "节次"),      # 合并列（如 "1-2节"）
            "teacher": _col(head, "教师", "老师"),
            "room": _col(head, "教室", "地点", "上课地点"),
            "weeks": _col(head, "周次"),
        }

    out = []
    for row in rows[start:]:
        cells = [str(c).strip() for c in row]
        while cells and not cells[-1]:
            cells.pop()
        if not cells or not cells[0]:
            continue

        def _at(key: str, default_idx: int, cells: list[str] = cells) -> str:
            j = colmap.get(key, -1) if colmap else default_idx
            return cells[j] if 0 <= j < len(cells) else ""

        name = _at("name", 0)
        if not name:
            continue
        day_s, period = _at("day", 1), ""
        start_s, end_s = _at("start", 2), _at("end", 3)
        if colmap.get("period", -1) >= 0 and not (start_s and end_s):
            period = _at("period", 2)          # 合并列兜底
        try:
            dm = re.search(r"\d+", day_s)
            if dm:
                day = int(dm.group())
            else:
                dmy = re.search(r"(?:周|星期)([一二三四五六日天])", day_s)
                day = DAYS[dmy.group(1)] if dmy else 0
            if not period:
                start_p = int(re.search(r"\d+", start_s).group())
                end_p = int(re.search(r"\d+", end_s).group()) if end_s else start_p
            else:
                pm = re.search(r"(\d{1,2})\s*[-–~]\s*(\d{1,2})", period)
                if not pm:
                    pm = re.search(r"\d{1,2}", period)
                    start_p = end_p = int(pm.group())
                else:
                    start_p, end_p = int(pm.group(1)), int(pm.group(2))
        except (AttributeError, ValueError):
            continue
        if not (1 <= day <= 7 and 1 <= start_p <= 15 and start_p <= end_p <= 15):
            continue
        weeks = _at("weeks", 6) or ""
        out.append({"course": name[:80], "day": day,
                    "period": f"{start_p}-{end_p}", "weeks": weeks[:40],
                    "teacher": _at("teacher", 4)[:40], "room": _at("room", 5)[:40],
                    "kind": ""})
    return out or None


def parse_wakeup_json(text: str) -> list[dict] | None:
    """WakeUp JSON 备份格式：[{courseName, day, startNode, endNode, teacher,
    classRoom, startWeek, endWeek, type}]（type: 1全部/2单/3双）。"""
    import json
    try:
        data = json.loads(text or "")
    except ValueError:
        return None
    if isinstance(data, dict):
        data = data.get("courses") or data.get("courseList") or []
    if not isinstance(data, list) or not data:
        return None
    first = data[0]
    if not isinstance(first, dict) or not any(k in first for k in _WAKEUP_JSON_KEYS):
        return None
    out = []
    for r in data:
        name = str(r.get("courseName") or r.get("name") or r.get("课程名")
                   or r.get("course") or "").strip()
        if not name:
            continue
        try:
            day = int(r.get("day") or 0)
            start_p = int(r.get("startNode") or r.get("startSection") or 0)
            end_p = int(r.get("endNode") or r.get("endSection") or start_p)
        except (TypeError, ValueError):
            continue
        sw = r.get("startWeek")
        ew = r.get("endWeek")
        try:
            weeks = f"{int(sw)}-{int(ew)}周" if sw and ew else ""
        except (TypeError, ValueError):
            weeks = ""
        wtype = str(r.get("type") or "")
        if wtype in ("2", "单", "单周"):
            weeks = (weeks + "单") if weeks else "单周"
        elif wtype in ("3", "双", "双周"):
            weeks = (weeks + "双") if weeks else "双周"
        out.append({"course": name[:80], "day": min(7, max(0, day)),
                    "period": f"{start_p}-{end_p}" if start_p else "",
                    "weeks": weeks[:40],
                    "teacher": str(r.get("teacher") or "").strip()[:40],
                    "room": str(r.get("classRoom") or r.get("room") or r.get("地点") or "").strip()[:40],
                    "kind": ""})
    return out or None


def _dedupe(items: list[dict]) -> list[dict]:
    seen, uniq = set(), []
    for it in items:
        key = (it["course"], it["day"], it["period"], it["weeks"])
        if key not in seen:
            seen.add(key)
            uniq.append(it)
    return uniq


# ---------- LLM 兜底 ----------

def _llm_parse(text: str) -> list[dict]:
    try:
        data = llm.chat_json([
            {"role": "system", "content": (
                "你是课程表解析器。从 OCR/复制的课程表文本中抽取全部课程安排。"
                "输出严格 JSON：{\"courses\":[{\"course\":\"课程名\",\"day\":1到7(周一=1),"
                "\"period\":\"节次如1-2\",\"weeks\":\"周次\",\"teacher\":\"教师\",\"room\":\"教室\"}]}，"
                "无法确定的字段填空字符串，不要编造，不要多余文字。")},
            {"role": "user", "content": text[:12000]},
        ], temperature=0.1, max_tokens=2600, task="extract")
    except Exception:
        return []
    rows = data.get("courses") if isinstance(data, dict) else data
    out = []
    for r in rows or []:
        if not isinstance(r, dict) or not (r.get("course") or "").strip():
            continue
        try:
            day = min(7, max(0, int(r.get("day") or 0)))  # 0 = 星期未定，与规则解析口径一致
        except (TypeError, ValueError):
            day = 0
        out.append({"course": str(r["course"]).strip()[:80], "day": day,
                    "period": str(r.get("period") or "").strip()[:20],
                    "weeks": str(r.get("weeks") or "").strip()[:40],
                    "teacher": str(r.get("teacher") or "").strip()[:40],
                    "room": str(r.get("room") or "").strip()[:40], "kind": ""})
    return out


# ---------- 入口 ----------

def import_from_text(text: str) -> dict:
    """文本 → 解析结果（不落库，由调用方确认后 replace_schedule 保存）。"""
    text = (text or "").strip()
    if len(text) < 4:
        raise ValueError("课程表文本为空")
    if text[0] in "[{":  # WakeUp JSON 备份直连
        wk = parse_wakeup_json(text)
        if wk:
            return {"courses": _dedupe(wk), "method": "wakeup-json"}
    courses = parse_text(text)
    method = "rules"
    if len(courses) < 2:
        alt = _llm_parse(text)
        if len(alt) > len(courses):
            courses, method = alt, "llm"
    if not courses:
        raise ValueError("没有解析出任何课程：请确认文本包含课程名（可与“周X / 第X节 / 教室”混排）")
    return {"courses": courses, "method": method}


def import_from_file(path: str, filename: str) -> dict:
    from . import ingest, rag
    ext = ingest.ext_of(filename)
    if ext in ingest.IMAGE_EXTS:
        text = rag._read_image(path)
        courses, method, raw = parse_text(text), "ocr+rules", text
    elif ext == ".xlsx":
        courses, method, raw = parse_xlsx(path), "xlsx-grid", ""
    elif ext == ".csv":
        for enc in ("utf-8-sig", "utf-8", "gb18030"):  # WakeUp CSV 优先直连
            try:
                with open(path, encoding=enc, newline="") as f:
                    rows = [row for row in csv.reader(f)]
                break
            except (UnicodeDecodeError, ValueError):
                continue
        else:
            raise ValueError("CSV 编码无法识别（支持 UTF-8 / GBK）")
        wk = parse_wakeup_rows(rows)
        if wk:
            return {"courses": _dedupe(wk), "method": "wakeup-csv"}
        courses, method, raw = parse_grid(rows), "csv-grid", ""
    elif ext == ".json":
        text = rag._read_text(path)
        wk = parse_wakeup_json(text)
        if wk:
            return {"courses": _dedupe(wk), "method": "wakeup-json"}
        courses, method, raw = parse_text(text), "rules", text
    elif ext in (".txt", ".md", ".markdown"):
        text = rag._read_text(path)
        courses, method, raw = parse_text(text), "rules", text
    else:
        raise ValueError("课程表支持：截图(png/jpg/webp/bmp) / Excel(.xlsx) / CSV / JSON(WakeUp) / 文本(txt/md)")
    if len(courses) < 2 and raw:
        alt = _llm_parse(raw)
        if len(alt) > len(courses):
            courses, method = alt, method + "+llm"
    if not courses:
        raise ValueError("没有从文件中解析出课程：请截图清晰些，或改用粘贴文本方式")
    return {"courses": courses, "method": method}


def save(term: str, courses: list[dict]) -> int:
    term = (term or "").strip()[:40]
    if not term:
        raise ValueError("请填写学期（如 2025-2026-1 或 大二上）")
    return db.replace_schedule(term, courses)
