"""学习疲劳检测（零 LLM 成本，中文正则信号）。

借鉴 OpenTutor fatigue.py 的 OpenAkita Persona 模式：从学生消息文本中
用预编译正则检测负面/正面信号，加权累加得到 0~1 的疲劳分。
疲劳分高时调用方应：降低出题难度、切换更细粒度提示、建议休息。
"""
import re

# 负面信号（加权分）：表达疲惫/沮丧/放弃倾向
_FATIGUE_SIGNALS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"(不想学|学不动|学不进|放弃|好累|太累了|累了|撑不住|坚持不下去|讨厌|烦死了|好烦)", re.I), 0.35),
    (re.compile(r"(做不到|太难了|不会做|搞不定|沮丧|崩溃|绝望)", re.I), 0.3),
    (re.compile(r"(看不懂|学不会|怎么还错|又错了|还是错|搞不懂|理解不了)", re.I), 0.3),
    (re.compile(r"(又错|还是不|一直不|老是错|完全没|根本搞)", re.I), 0.25),
    (re.compile(r"(算了|唉|呃|随便|无所谓|爱咋咋|就这样吧|不想搞)", re.I), 0.25),
    (re.compile(r"[😫😤😩😭💀🤯😡🥲]"), 0.2),
]

# 正面信号（减分）：表达理解/满意，防止误判
_POSITIVE_SIGNALS: list[tuple[re.Pattern, float]] = [
    (re.compile(r"(懂了|明白了|会了|理解了|搞懂了|终于懂|原来如此|原来是这样)", re.I), -0.3),
    (re.compile(r"(明白了|清楚了|知道了|了解了|想通了|搞清楚)", re.I), -0.3),
    (re.compile(r"(谢谢|感谢|不错|挺好|很好|厉害|棒|牛)", re.I), -0.15),
]


def detect_fatigue(message: str) -> float:
    """检测学生消息中的疲劳/挫败程度，返回 0.0~1.0。

    0.0 = 精力充沛；0.5+ = 有挫败感；0.7+ = 明显疲劳，建议休息或降低难度。
    """
    if not message:
        return 0.0
    score = 0.0
    for pattern, weight in _FATIGUE_SIGNALS:
        if pattern.search(message):
            score += weight
    for pattern, weight in _POSITIVE_SIGNALS:
        if pattern.search(message):
            score += weight
    return max(0.0, min(score, 1.0))


def fatigue_hint(score: float) -> str:
    """根据疲劳分返回注入 system prompt 的提示词（空串 = 无需干预）。"""
    if score >= 0.7:
        return (
            "\n\n【疲劳检测】学生当前疲劳/挫败感明显。请："
            "1) 语气更温和耐心，先共情再讲解；"
            "2) 把解释拆成更小的步骤，一次只讲一个点；"
            "3) 主动建议学生休息 5-10 分钟再继续；"
            "4) 避免追加新的练习压力。"
        )
    if score >= 0.4:
        return (
            "\n\n【疲劳检测】学生有些沮丧。请用鼓励的语气，"
            "先肯定已完成的部分，再给最小可行动的下一步提示，不要一次灌输太多。"
        )
    return ""
