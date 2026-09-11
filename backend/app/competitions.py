"""竞赛规划引擎：目标导向的竞赛推荐与分析（内置目录，零 LLM 也可用）。

- 内置竞赛目录：收录高校认可度高、信息稳定的主流竞赛（级别 / 举办窗口 / 备赛周期 /
  专业匹配 / 对 考研·推免·就业·出国 四条路径的价值评分）。
  窗口为常见惯例，用户以当年官方通知为准（界面明示）。
- 目标分析（零 LLM）：档案（专业 / 目标 / 时间线）→ 目标路径 → 按
  路径价值 × 专业匹配 × 时间可行性 排序，回答"至少要参加哪几个"：
  tier1 = 至少参加（强烈推荐），tier2 = 有余力值得考虑，tier3 = 谨慎投入（时间或回报不匹配）。
- LLM 增强：可选把结构化清单 + 档案交给模型生成个性化备赛策略（Markdown）。
  只允许基于清单内信息组织计划，不编造具体院校加分政策；失败不影响结构化推荐。
"""
import datetime
import re

from . import db, llm

# ---------- 内置竞赛目录 ----------
# goals 数值 1-5：该路径下此竞赛的回报价值（5 = 该路径硬通货）
# majors 关键词命中任意一个即算专业对口；含 "通用" 的对所有专业对口
# cadence: yearly 每年 / odd 奇数年 / even 偶数年；hold_month 为主赛事月份（以官方通知为准）
# result_weeks：赛后到出结果的大致周数（判断能否赶在复试/提交材料前拿奖）
CATALOG: list[dict] = [
    {
        "id": "cumcm", "name": "全国大学生数学建模竞赛", "abbr": "数模国赛",
        "tier": "国家级", "organizer": "中国工业与应用数学学会",
        "window_label": "每年 9 月（赛区评审后 12 月前后评国奖）",
        "hold_month": 9, "cadence": "yearly", "team": "3 人组队",
        "prep_weeks": 8, "result_weeks": 10,
        "majors": ["通用"],
        "goals": {"考研": 5, "推免": 5, "就业": 4, "出国": 4},
        "why": "几乎所有院校复试/推免面试都认的通用硬通货；建模-编程-写作的分工训练还能直接迁移到毕业论文与科研入门。",
    },
    {
        "id": "mcm", "name": "美国大学生数学建模竞赛（MCM/ICM）", "abbr": "美赛",
        "tier": "国际", "organizer": "COMAP",
        "window_label": "每年 2 月（寒假备赛）",
        "hold_month": 2, "cadence": "yearly", "team": "3 人组队",
        "prep_weeks": 6, "result_weeks": 8,
        "majors": ["通用"],
        "goals": {"考研": 3, "推免": 4, "就业": 3, "出国": 5},
        "why": "出国/中外合办项目认可度高；与数模国赛同一套能力，参加一次国赛后再打美赛边际成本很低。",
    },
    {
        "id": "cisc", "name": "中国国际大学生创新大赛（原「互联网+」）", "abbr": "国创赛",
        "tier": "国家级", "organizer": "教育部等部委",
        "window_label": "校赛 5-6 月 → 省赛 7-8 月 → 国赛 10 月前后",
        "hold_month": 10, "cadence": "yearly", "team": "团队（建议 4-6 人，跨专业）",
        "prep_weeks": 10, "result_weeks": 6,
        "majors": ["通用"],
        "goals": {"考研": 4, "推免": 5, "就业": 5, "出国": 3},
        "why": "最高规格的创新创业赛事；进省赛即有简历分量，项目经历在就业面试里可讲性最强。",
    },
    {
        "id": "challenge_cup", "name": "「挑战杯」全国大学生课外学术科技作品竞赛", "abbr": "挑战杯（大挑）",
        "tier": "国家级", "organizer": "共青团中央等",
        "window_label": "奇数年为主：省赛春季 → 国赛秋季",
        "hold_month": 10, "cadence": "odd", "team": "团队 + 指导教师",
        "prep_weeks": 12, "result_weeks": 6,
        "majors": ["通用"],
        "goals": {"考研": 4, "推免": 5, "就业": 4, "出国": 3},
        "why": "学术科技作品赛道最贴近科研：有论文/专利产出的项目在推免面试和复试里说服力极强。",
    },
    {
        "id": "challenge_bp", "name": "「挑战杯」大学生创业计划竞赛（小挑）", "abbr": "挑战杯（小挑）",
        "tier": "国家级", "organizer": "共青团中央等",
        "window_label": "偶数年为主：省赛春季 → 国赛秋季",
        "hold_month": 10, "cadence": "even", "team": "团队",
        "prep_weeks": 10, "result_weeks": 6,
        "majors": ["通用"],
        "goals": {"考研": 3, "推免": 4, "就业": 5, "出国": 2},
        "why": "创业计划赛道，商业计划书与路演训练对求职面试加成明显，学术场景价值低于大挑。",
    },
    {
        "id": "icpc", "name": "ACM-ICPC / CCPC 程序设计竞赛", "abbr": "ACM/CCPC",
        "tier": "国际/国家级", "organizer": "ICPC 基金会 / 中国大学生程序设计竞赛组委会",
        "window_label": "网络预赛 8-9 月 → 区域赛 10-11 月",
        "hold_month": 10, "cadence": "yearly", "team": "3 人组队",
        "prep_weeks": 16, "result_weeks": 4,
        "majors": ["计算机", "软件", "人工智能", "信息", "数据科学", "网络工程", "数学"],
        "goals": {"考研": 4, "推免": 5, "就业": 5, "出国": 4},
        "why": "大厂技术岗认可度第一的竞赛；奖牌直接对应算法能力证明。备赛周期长，需要长期刷题积累。",
    },
    {
        "id": "lanqiao", "name": "蓝桥杯全国软件和信息技术专业人才大赛", "abbr": "蓝桥杯",
        "tier": "省级起步/国家级", "organizer": "工信部人才交流中心",
        "window_label": "省赛 4 月 → 国赛 5-6 月",
        "hold_month": 4, "cadence": "yearly", "team": "个人",
        "prep_weeks": 6, "result_weeks": 4,
        "majors": ["计算机", "软件", "人工智能", "信息", "电子", "自动化", "数据"],
        "goals": {"考研": 3, "推免": 3, "就业": 3, "出国": 2},
        "why": "入门最友好的编程赛事：个人参赛、省奖易得，适合作为 ACM 之前的第一个奖项建立信心。",
    },
    {
        "id": "4c", "name": "中国大学生计算机设计大赛", "abbr": "4C",
        "tier": "国家级", "organizer": "高校计算机教育研究团体",
        "window_label": "省赛 5-6 月 → 国赛 7-8 月",
        "hold_month": 7, "cadence": "yearly", "team": "1-3 人",
        "prep_weeks": 8, "result_weeks": 6,
        "majors": ["计算机", "软件", "人工智能", "数字媒体", "信息"],
        "goals": {"考研": 3, "推免": 4, "就业": 4, "出国": 3},
        "why": "作品型赛道（AI 应用/媒体/软件应用），门槛低于 ACM，成果可视化强，适合答辩展示。",
    },
    {
        "id": "csp", "name": "CCF CSP 计算机软件能力认证", "abbr": "CSP 认证",
        "tier": "认证（每月）", "organizer": "中国计算机学会",
        "window_label": "几乎每月一次，随时可考",
        "hold_month": 3, "cadence": "yearly", "team": "个人",
        "prep_weeks": 4, "result_weeks": 2,
        "majors": ["计算机", "软件", "人工智能", "信息", "数据"],
        "goals": {"考研": 2, "推免": 4, "就业": 4, "出国": 2},
        "why": "严格说是能力认证：部分高校推免加分/机考免试认可，分数可直接写进简历，成本低见效快。",
    },
    {
        "id": "nuedc", "name": "全国大学生电子设计竞赛（电赛）", "abbr": "电赛",
        "tier": "国家级", "organizer": "教育部 / 工信部",
        "window_label": "奇数年国赛 8 月；偶数年多为省级 TI 杯邀请赛",
        "hold_month": 8, "cadence": "odd", "team": "3 人组队",
        "prep_weeks": 12, "result_weeks": 8,
        "majors": ["电子", "电气", "自动化", "通信", "机电", "机械", "测控", "仪器"],
        "goals": {"考研": 4, "推免": 5, "就业": 5, "出国": 3},
        "why": "硬件/嵌入式方向的王牌赛事：四天三夜闭环作品，对口专业就业（硬件/嵌入式岗）几乎是硬通货。",
    },
    {
        "id": "smart_car", "name": "全国大学生智能汽车竞赛", "abbr": "智能车",
        "tier": "国家级", "organizer": "教育部高校自动化类教学指导委员会",
        "window_label": "分赛区 6-7 月 → 全国总决赛 8 月",
        "hold_month": 8, "cadence": "yearly", "team": "小组",
        "prep_weeks": 12, "result_weeks": 4,
        "majors": ["自动化", "电子", "通信", "计算机", "机电", "机械", "仪器"],
        "goals": {"考研": 3, "推免": 4, "就业": 4, "出国": 2},
        "why": "控制 + 嵌入式综合训练，与电赛能力栈重叠，机器人/自动驾驶方向面试的项目素材来源。",
    },
    {
        "id": "mech_design", "name": "全国大学生机械创新设计大赛", "abbr": "机创",
        "tier": "国家级", "organizer": "教育部机械基础课程教学指导分委员会等",
        "window_label": "偶数年为主：省赛 5-6 月 → 全国决赛 7-8 月前后",
        "hold_month": 8, "cadence": "even", "team": "3-5 人团队",
        "prep_weeks": 12, "result_weeks": 6,
        "majors": ["机械", "机电", "智能制造", "仪器", "农业工程", "车辆"],
        "goals": {"考研": 4, "推免": 5, "就业": 4, "出国": 2},
        "why": "机械专业的对口主赛道：实物作品 + 设计说明书，复试里能直接讲机构方案与创新点。",
    },
    {
        "id": "engineering_x", "name": "中国大学生工程实践与创新能力大赛", "abbr": "工创赛",
        "tier": "国家级", "organizer": "教育部工程训练教学指导委员会",
        "window_label": "省区赛秋季 → 全国决赛隔年 8 月前后",
        "hold_month": 8, "cadence": "yearly", "team": "3 人组队",
        "prep_weeks": 10, "result_weeks": 4,
        "majors": ["机械", "机电", "智能制造", "自动化", "电子", "能源", "车辆", "材料"],
        "goals": {"考研": 3, "推免": 4, "就业": 3, "出国": 2},
        "why": "工科综合能力（铸造/热处理/智能物流等赛道），覆盖面广，校级资源通常有现成梯队。",
    },
    {
        "id": "jienengjianpai", "name": "全国大学生节能减排社会实践与科技竞赛", "abbr": "节能减排",
        "tier": "国家级", "organizer": "教育部能源动力学科教学指导委员会",
        "window_label": "校赛 3-4 月 → 全国决赛 8 月",
        "hold_month": 8, "cadence": "yearly", "team": "团队",
        "prep_weeks": 10, "result_weeks": 4,
        "majors": ["能源", "动力", "环境", "机械", "化工", "建筑", "电气"],
        "goals": {"考研": 3, "推免": 4, "就业": 3, "出国": 3},
        "why": "双碳主题长盛不衰，科技作品与社会调研双赛道，适合与科研课题结合产出。",
    },
    {
        "id": "zhoupeiyuan", "name": "周培源全国大学生力学竞赛", "abbr": "力学竞赛",
        "tier": "国家级", "organizer": "中国力学学会",
        "window_label": "奇数年 5 月前后（个人笔试 + 团体赛）",
        "hold_month": 5, "cadence": "odd", "team": "个人",
        "prep_weeks": 8, "result_weeks": 6,
        "majors": ["力学", "机械", "土木", "航空", "航天", "车辆", "水利"],
        "goals": {"考研": 4, "推免": 3, "就业": 2, "出国": 2},
        "why": "和考研专业课（理论力学/材料力学）重合度最高的竞赛，备赛本身就是复习。",
    },
    {
        "id": "structure", "name": "全国大学生结构设计竞赛", "abbr": "结构赛",
        "tier": "国家级", "organizer": "教育部高校土木工程学科专业教学指导委员会",
        "window_label": "省赛 5-6 月 → 全国赛 10-11 月",
        "hold_month": 10, "cadence": "yearly", "team": "3 人组队",
        "prep_weeks": 10, "result_weeks": 4,
        "majors": ["土木", "建筑", "水利", "力学", "交通"],
        "goals": {"考研": 3, "推免": 4, "就业": 3, "出国": 2},
        "why": "土木方向对口主赛道，模型制作与加载试验的经历在复试实操类问题里很好用。",
    },
    {
        "id": "robomaster", "name": "RoboMaster 机甲大师赛", "abbr": "RoboMaster",
        "tier": "国家级/企业赛事", "organizer": "大疆创新",
        "window_label": "区域赛 5-6 月 → 全国总决赛 8 月",
        "hold_month": 8, "cadence": "yearly", "team": "战队（多人分工）",
        "prep_weeks": 16, "result_weeks": 2,
        "majors": ["机械", "自动化", "电子", "计算机", "机电", "控制"],
        "goals": {"考研": 2, "推免": 3, "就业": 5, "出国": 2},
        "why": "机器人方向就业认可度极高（大厂机器人/自动驾驶团队认），但投入极重，需依托学校战队。",
    },
    {
        "id": "siemens_cup", "name": "「西门子杯」中国智能制造挑战赛", "abbr": "西门子杯",
        "tier": "国家级（企业冠名）", "organizer": "教育部高校自动化类教指委等",
        "window_label": "初赛 5-7 月 → 全国决赛 8 月",
        "hold_month": 8, "cadence": "yearly", "team": "1-3 人",
        "prep_weeks": 8, "result_weeks": 4,
        "majors": ["自动化", "机械", "电气", "智能制造", "机电", "工业工程"],
        "goals": {"考研": 3, "推免": 3, "就业": 5, "出国": 2},
        "why": "智能制造/工业自动化方向与产业界贴合度最高的赛事，PLC/工艺建模能力直接对口制造大厂。",
    },
    {
        "id": "cisaw_sec", "name": "全国大学生信息安全竞赛", "abbr": "信安赛",
        "tier": "国家级", "organizer": "教育部高校网络空间安全专业教指委",
        "window_label": "报名 4-5 月 → 创作实践 5-8 月 → 决赛 8 月前后",
        "hold_month": 8, "cadence": "yearly", "team": "团队（≤4 人）",
        "prep_weeks": 10, "result_weeks": 6,
        "majors": ["网络空间安全", "信息安全", "计算机", "软件", "通信"],
        "goals": {"考研": 3, "推免": 4, "就业": 4, "出国": 3},
        "why": "网安方向唯一全国性综合赛事，作品赛道可孵化系统级安全项目，安全岗简历刚需。",
    },
    {
        "id": "market_survey", "name": "全国大学生市场调查与分析大赛", "abbr": "市调大赛",
        "tier": "国家级", "organizer": "教育部高校统计学类教指委 / 中国商业统计学会",
        "window_label": "校赛 11-12 月 → 省赛 3-4 月 → 国赛 5-6 月",
        "hold_month": 5, "cadence": "yearly", "team": "团队",
        "prep_weeks": 8, "result_weeks": 4,
        "majors": ["经济", "管理", "统计", "金融", "市场营销", "电子商务", "工商"],
        "goals": {"考研": 2, "推免": 3, "就业": 4, "出国": 2},
        "why": "经管方向数据调研全流程训练（问卷-分析-报告），咨询/用数岗求职有直接素材。",
    },
    {
        "id": "fltrp", "name": "「外研社·国才杯」全国大学生外语能力大赛", "abbr": "外研社国才杯",
        "tier": "国家级", "organizer": "外语教学与研究出版社",
        "window_label": "校赛 9-10 月 → 省赛 10-11 月 → 国赛 12 月前后",
        "hold_month": 10, "cadence": "yearly", "team": "个人",
        "prep_weeks": 6, "result_weeks": 4,
        "majors": ["通用"],
        "goals": {"考研": 3, "推免": 3, "就业": 3, "出国": 4},
        "why": "复试英文问答与出国语言背景都吃英语硬实力，演讲/写作赛道的备赛过程即是训练本身。",
    },
    {
        "id": "career_contest", "name": "全国大学生职业规划大赛", "abbr": "职规大赛",
        "tier": "国家级", "organizer": "教育部学生服务与素质发展中心",
        "window_label": "校赛 10-12 月 → 省赛次年 1-3 月 → 国赛 4-5 月",
        "hold_month": 12, "cadence": "yearly", "team": "个人",
        "prep_weeks": 4, "result_weeks": 6,
        "majors": ["通用"],
        "goals": {"考研": 1, "推免": 2, "就业": 5, "出国": 1},
        "why": "就业赛道直接对口：完整过一遍行业调研-自我定位-路径设计，作品就是一份高质量求职准备。",
    },
]

GOAL_LABELS = {"考研": "考研", "推免": "推免/保研", "就业": "就业/求职", "出国": "出国/留学"}
GOALS = list(GOAL_LABELS)

_MAJOR_SYNONYMS = {
    "计算机": ["计算机", "软件", "人工智能", "智能科学", "数据科学", "大数据", "物联网", "网络工程", "信息安全", "网络空间"],
    "电子": ["电子", "微电子", "集成电路", "光电"],
    "通信": ["通信", "信息工程", "电子信息"],
    "自动化": ["自动化", "控制", "机器人工程"],
    "机械": ["机械", "机电", "智能制造", "车辆", "工业设计", "过程装备"],
    "电气": ["电气"],
    "土木": ["土木", "建筑环境", "道路桥梁"],
    "能源": ["能源", "动力", "新能源"],
    "材料": ["材料"],
    "力学": ["力学", "工程力学"],
    "统计": ["统计"],
    "经济": ["经济", "金融", "国际经济"],
    "管理": ["管理", "工商管理", "会计", "市场营销", "人力资源", "电子商务", "物流"],
}


def _norm_goal(goal: str) -> str:
    g = goal or ""
    if "推免" in g or "保研" in g:
        return "推免"
    if "就业" in g or "求职" in g or "工作" in g:
        return "就业"
    if "出国" in g or "留学" in g or "境外" in g:
        return "出国"
    return "考研"


def _major_matches(major: str, keywords: list[str]) -> bool:
    if "通用" in keywords:
        return True
    m = (major or "").strip()
    if not m:
        return False
    # 通过同义词表扩展：机械 → 智能制造/机电/车辆…
    expanded: set[str] = set()
    for key, syns in _MAJOR_SYNONYMS.items():
        pool = {key, *syns}
        if any(s in m for s in pool):
            expanded |= pool
    hit = {k for k in keywords if (k in m or k in expanded)}
    return bool(hit)


def _deadline_from(timeline: str, goal: str) -> tuple[datetime.date | None, str]:
    """优先用档案时间线解析截止日；否则按目标给一个保守默认并标注推测。

    默认值刻意保守：9 月之后再看考研/推免，最近的 12 月已不足一个备赛周期，
    默认取下一年初试，避免把大二大三当成临考生；就业/出国同理取下一个毕业季。
    """
    t = timeline or ""
    m = re.search(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})", t)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))), t.strip()
    m = re.search(r"(20\d{2})[年./-](\d{1,2})月?", t)
    if m:
        return datetime.date(int(m.group(1)), int(m.group(2)), 15), t.strip()
    today = datetime.date.today()
    if goal in ("考研", "推免"):
        year = today.year + (1 if today.month >= 9 else 0)
        return datetime.date(year, 12, 15), "档案未填时间线，按考研初试（12 月）推测"
    year = today.year + (1 if today.month >= 4 else 0)
    return datetime.date(year, 6, 30), "档案未填时间线，按毕业季（6 月）推测"


def _next_occurrence(hold_month: int, cadence: str, today: datetime.date,
                     deadline: datetime.date | None,
                     after: datetime.date | None = None) -> datetime.date | None:
    """下一次主赛事日期（月中近似）；隔年赛事按年份奇偶校验。

    after 用于跳过"来不及备赛"的最近一届，看下一届是否还赶得上截止。
    """
    start = after or today
    year = start.year
    for _ in range(5):
        if cadence == "odd" and year % 2 == 0:
            year += 1
            continue
        if cadence == "even" and year % 2 == 1:
            year += 1
            continue
        d = datetime.date(year, hold_month, 15)
        if d >= start:
            if deadline and d > deadline:
                return None
            return d
        year += 1
    return None


def catalog() -> dict:
    return {"items": CATALOG, "count": len(CATALOG),
            "note": "窗口为常见惯例，报名与赛制以当年官方通知为准"}


def analyze(profile: dict, goal: str = "", use_llm: bool = True) -> dict:
    """目标导向的竞赛推荐：结构化分级（零 LLM）+ 可选 LLM 备赛策略。"""
    goal_path = _norm_goal(goal or profile.get("goal_type") or "")
    major = profile.get("major") or ""
    school = profile.get("current_school") or ""
    target = " ".join(x for x in [profile.get("target_school") or "", profile.get("target_major") or ""] if x)
    flags = profile.get("flags") or []
    novice = ("无竞赛奖项" in flags) or ("无科研经历" in flags)

    deadline, deadline_src = _deadline_from(profile.get("timeline") or "", goal_path)
    today = datetime.date.today()
    months_left = round((deadline - today).days / 30.44) if deadline else None

    picks: list[dict] = []
    for c in CATALOG:
        value = (c["goals"] or {}).get(goal_path, 1)
        matched = _major_matches(major, c["majors"])
        # 区分"专业强对口"（关键词命中）与"通用可打"：对口的优先级应高于通用赛
        generic = "通用" in c["majors"]
        factor = 1.35 if (matched and not generic) else 1.1 if matched else 0.7
        occ = _next_occurrence(c["hold_month"], c["cadence"], today, deadline)
        # 最近一届距今不足备赛周期 → 顺延到下一届（若下一届仍赶得上截止）
        if occ and occ - today < datetime.timedelta(weeks=max(c["prep_weeks"], 2)):
            nxt = _next_occurrence(c["hold_month"], c["cadence"], today, deadline, after=occ + datetime.timedelta(days=1))
            if nxt:
                occ = nxt
        prep_weeks = c["prep_weeks"]
        # 结果能否赶上截止（复试材料/秋招尾声）：以赛后出结果周期估算
        lands_in_time = bool(occ and deadline and
                             occ + datetime.timedelta(weeks=c["result_weeks"]) <= deadline)
        enough_prep = bool(occ and occ - today >= datetime.timedelta(weeks=max(prep_weeks, 2)))
        feasible = bool(occ) and (lands_in_time or goal_path == "就业")
        score = value * factor
        if not feasible:
            score -= 3
        if novice and prep_weeks <= 8:
            score += 0.6  # 入门友好赛事对首奖更友好
        picks.append({
            **{k: c[k] for k in ("id", "name", "abbr", "tier", "team", "window_label",
                                 "prep_weeks", "why", "organizer")},
            "value": value,
            "major_match": matched,
            "specialist": bool(matched and not generic),
            "suggested_date": occ.isoformat() if occ else None,
            "lands_in_time": lands_in_time,
            "enough_prep": enough_prep,
            "feasible": feasible,
            "score": round(score, 2),
        })

    picks.sort(key=lambda p: (-p["score"], -(p["value"])))

    tier1: list[dict] = []
    tier2: list[dict] = []
    tier3: list[dict] = []
    for p in picks:
        if p["suggested_date"] is None:
            p["note"] = "截止前已无合适届次，赶不上出成绩"
            tier3.append(p)
        elif not p["lands_in_time"] and goal_path != "就业":
            p["note"] = "出成绩晚于截止日，奖项赶不上材料提交"
            tier3.append(p)
        elif p["value"] >= 4 and (p["specialist"] or p["id"] == "cumcm") \
                and p["enough_prep"] and len(tier1) < 3:
            tier1.append(p)
        elif p["value"] >= 3 and p["feasible"]:
            if not p["enough_prep"]:
                p["note"] = "最近一届距今太近、来不及系统备赛；除非当练兵，建议按下一届规划"
            else:
                p.setdefault("note", "")
            tier2.append(p)
        else:
            p["note"] = p.get("note") or "对该路径回报有限，不建议现在投入"
            tier3.append(p)
    # 保底：即便没有完全达标的，也把时间可行的最高分项提进 tier1，保证给出"至少参加谁"的答案
    if not tier1:
        for p in picks:
            if p["feasible"] and p not in tier2 or (p in tier2 and p["value"] >= 3):
                if p["feasible"]:
                    tier1.append(p)
                    if p in tier2:
                        tier2.remove(p)
                    break

    result = {
        "goal": goal_path,
        "goal_label": GOAL_LABELS[goal_path],
        "school": school,
        "major": major,
        "target": target,
        "deadline": deadline.isoformat() if deadline else None,
        "deadline_source": deadline_src,
        "months_left": months_left,
        "tier1": tier1,
        "tier2": tier2,
        "tier3": tier3[:6],
        "catalog_count": len(CATALOG),
        "strategy_md": "",
        "strategy_error": "",
    }

    if use_llm:
        try:
            result["strategy_md"] = _strategy(goal_path, target, deadline, months_left,
                                              tier1, tier2, novice, major)
        except Exception as e:
            result["strategy_error"] = f"模型策略生成失败（结构化推荐不受影响）：{str(e)[:160]}"
    return result


def _strategy(goal_path: str, target: str, deadline: datetime.date | None,
              months_left: int | None, tier1: list[dict], tier2: list[dict],
              novice: bool, major: str) -> str:
    """LLM 备赛策略：只基于清单与档案组织计划，不允许编造院校政策。"""
    def fmt(items: list[dict]) -> str:
        return "\n".join(
            f"- {p['name']}（{p['tier']}，{p['window_label']}，建议参加 "
            f"{p['suggested_date'] or '灵活'}，备赛约 {p['prep_weeks']} 周，{p['team']}）"
            for p in items
        ) or "（无）"

    dl = deadline.isoformat() if deadline else "未定"
    sys_prompt = (
        "你是高校学科竞赛规划助教。只依据给定的竞赛清单和学生档案组织建议；"
        "不要编造任何具体院校的加分/复试政策，凡涉及目标院校具体规则都提示以官方文件为准。"
        "输出 Markdown，控制在 500 字内，结构：## 时间线倒排 / ## 精力分配 / ## 组队与选题 / ## 奖项怎么用。"
    )
    user_prompt = (
        f"目标路径：{GOAL_LABELS[goal_path]}\n目标去向：{target or '（未填）'}\n"
        f"专业：{major or '（未填）'}\n截止：{dl}"
        f"{f'（约 {months_left} 个月）' if months_left is not None else ''}\n"
        f"首次参赛基础：{'较弱（无竞赛奖项/科研经历）' if novice else '有一定基础'}\n\n"
        f"强烈推荐清单：\n{fmt(tier1)}\n\n有余力清单：\n{fmt(tier2)}\n\n"
        "请生成备赛策略：时间线倒排（何时报名/何时进入冲刺）、与日常学习的精力分配、"
        "组队与选题要点、以及获奖后如何在复试/简历中呈现。"
    )
    return llm.chat([
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt},
    ], task="competition")
