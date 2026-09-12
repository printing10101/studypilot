"""专家团 + 三层记忆（L1 镜像 / L2 摘要 / L3 长期综合）+ 模式(Ask/Plan/Craft)编排。"""
import json
import logging
import re
import sys
import threading

from . import connectors, db, fatigue, llm, rag
from .config import settings

log = logging.getLogger("studypilot.experts")

# ---------- 专家团（WorkBuddy: 专家 agents） ----------

EXPERTS = {
    "qa": {
        "name": "讲义答疑专家",
        "description": "基于课程讲义精准答疑，回答附引用来源",
        "system": (
            "你是严谨且善于启发的课程助教。回答原则：\n"
            "1. 只依据提供的讲义片段回答；片段未覆盖的内容明确说明「讲义未涉及」，不要编造。\n"
            "2. 先给结论再展开论证；公式用 LaTeX（$..$ 行内 / $$..$$ 独行）。\n"
            "3. 关键结论标注来源片段编号，如 [片段2]。\n"
            "4. 如果学生的问题涉及多个概念，先厘清概念间的关系再作答。\n"
            "5. 回答末尾用一句话点出「这个知识点常见的误解是什么」，帮助学生避开陷阱。\n"
            "6. 结合学生的薄弱点档案个性化调整讲解深度——对已掌握的概念一笔带过，对薄弱概念多展开。"
        ),
    },
    "examiner": {
        "name": "出题官",
        "description": "根据讲义出测试题，考察理解而非背诵",
        "system": (
            "你是资深的课程出题官。出题原则：\n"
            "1. 依据讲义片段出题，覆盖不同难度层次（回忆→应用→分析→陷阱）。\n"
            "2. 注重概念理解与迁移应用，避免纯记忆题。\n"
            "3. 选择题干扰项要有迷惑性（常见错误思路），不要出现明显荒谬的选项。\n"
            "4. 简答题的参考答案要给出评分要点（关键步骤/关键概念）。\n"
            "5. 每道题标注 knowledge_point（10-20字的知识点短语）。\n"
            "6. 输出严格 JSON 数组，不要多余文字。"
        ),
    },
    "grader": {
        "name": "判卷助教",
        "description": "逐题判卷、给出错误原因分析",
        "system": (
            "你是耐心且敏锐的判卷助教。判卷原则：\n"
            "1. 概念近似正确算对（表述不同但意思对）；部分正确标「部分对」。\n"
            "2. 对错误答案做三层归因：知识层（概念不会/前置缺失）、策略层（方法选错/步骤跳步）、"
            "认知层（审题偏差/思维定式/粗心）。\n"
            "3. analysis 字段给出：错误根因 + 正确思路（50字内），要具体到哪个概念/步骤出了问题。\n"
            "4. 对「部分对」的答案，指出缺了什么才能得满分。\n"
            "5. 输出严格 JSON，不要多余文字。"
        ),
    },
    "planner": {
        "name": "学习规划师",
        "description": "结合掌握状态生成学习计划",
        "system": (
            "你是学习规划师。规划原则：\n"
            "1. 根据学生的记忆档案（薄弱点、易错点、到期复习）和讲义目录，给出可执行的分阶段计划。\n"
            "2. 每个阶段：目标 → 具体行动（到知识点粒度）→ 验收标准 → 预估时间。\n"
            "3. 薄弱知识点优先安排，且要先补前置依赖再学后继内容。\n"
            "4. 合理分配复习与新学的比例（建议 40% 复习 + 60% 新学）；复习必须是检索而非重读。\n"
            "5. 每条任务写明学习方法（检索/间隔/交错/样例/自我解释/费曼等）与可执行动作，禁止空泛「多做题」。\n"
            "6. 同一阶段交错不同知识点与题型；单次会话含检索热身→精学→交错练→闭卷收尾。\n"
            "7. 用 Markdown 表格输出，附时间线。"
        ),
    },
}

MODE_SYSTEM = {
    "ask": EXPERTS["qa"]["system"],
    "plan": EXPERTS["planner"]["system"],
    "craft": "你是学习产出助手，帮学生把讲义内容整理成结构化笔记、错题本或总结，用 Markdown 输出，重要概念加粗，附来源片段编号。",
}

# ask 模式路由到非 qa 专家时用的对话版系统词：技能管线（quiz.generate 等）要求严格 JSON，
# 直接搬进聊天会让回答变成裸 JSON，这里只保留人设与出题/规划原则、把输出格式改为对话友好
_CHAT_SYSTEM = {
    "examiner": (
        "你是资深的课程出题官，现在在对话中应学生要求出题。出题原则：\n"
        "1. 依据讲义片段出题，覆盖不同难度层次（回忆→应用→分析→陷阱）。\n"
        "2. 注重概念理解与迁移应用，避免纯记忆题；选择题干扰项要有迷惑性（常见错误思路）。\n"
        "3. 直接用 Markdown 在对话里列出题目（选择题标 A-D 选项），先不要公布答案。\n"
        "4. 每道题末尾标注知识点（10-20字短语）；出完提醒学生作答后你来逐题判卷讲评。"
    ),
}


def _system_for(mode: str, expert_key: str) -> str:
    if mode != "ask":
        return MODE_SYSTEM.get(mode, MODE_SYSTEM["ask"])
    return _CHAT_SYSTEM.get(expert_key) or EXPERTS[expert_key]["system"]

# 苏格拉底引导模式（Ask 页「引导我」开关开启时追加到系统词）
GUIDE_SUFFIX = (
    "\n\n【引导教学模式】你现在是一位苏格拉底式助教，不要直接给出完整答案：\n"
    "1. 先确认学生卡在哪一步——如果学生描述模糊，用一个选择题式的问题帮其定位卡点。\n"
    "2. 给最小限度的提示：先指方向（「想想这个公式适用的前提是什么」），"
    "再给思路（「我们可以从X角度切入」），最后才给关键步骤。\n"
    "3. 学生答对中间步骤就肯定并推进到下一步；答错了不直接说「错」，"
    "而是指出矛盾之处让其自己发现。\n"
    "4. 如果学生连续两次在同一步卡住，主动降低一个台阶，换更基础的角度重新引导。\n"
    "5. 仅当学生明确要求直接给答案、或已引导三轮仍未突破时，才给出完整解答（仍附引用）。\n"
    "6. 每次回复控制在 150 字内，并以一个推动思考的问题结尾。\n"
    "7. 如果检测到学生疲劳，先共情再给最小可行动的提示，不要追加压力。"
)


_EXAMINER_RE = re.compile(r"出.{0,10}题|考.{0,3}我|测试|练习|做题|来几道|刷题")
_PLANNER_RE = re.compile(r"计划|规划|怎么学|如何安排|安排一下|复习")


def route_expert(question: str) -> str:
    """宽松路由：正则匹配口语化表达（如"出几道题练练手"也能命中出题官）。"""
    if _EXAMINER_RE.search(question):
        return "examiner"
    if _PLANNER_RE.search(question):
        return "planner"
    return "qa"


def build_memory_context(space_id: str) -> str:
    l2 = db.latest_l2(space_id)
    l3 = db.list_memory(space_id, level=3)
    weak = db.weak_points(space_id, 8)
    due = db.due_points(space_id)
    parts = []
    if l2:
        parts.append(f"【近期学习摘要】{l2}")
    if weak:
        status_cn = {"weak": "薄弱", "learning": "学习中", "mastered": "已掌握"}
        lines = [f"- {w['point']}（掌握度 {int(w['score'] * 100)}%，错 {w['wrong']} 次，{status_cn.get(w['status'], w['status'])}）"
                 for w in weak]
        parts.append("【薄弱知识点排行】\n" + "\n".join(lines))
    if due:
        parts.append(f"【待复习】{len(due)} 个知识点已到间隔复习时间：" + "、".join(p["point"] for p in due[:5]))
    if l3:
        lines = [f"- ({m['kind']}) {m['content']}" for m in l3[-20:]]
        parts.append("【长期记忆档案】\n" + "\n".join(lines))
    # 跨空间迁移提示：其他课程已掌握的相关概念
    try:
        from . import velocity
        transfers = velocity.detect_cross_space_transfer()
        if transfers:
            hints = [t["recommendation"] for t in transfers[:3]]
            parts.append("【跨课程关联】\n" + "\n".join(f"- {h}" for h in hints))
    except Exception:
        pass
    return "\n".join(parts)


def record_feedback(space_id: str, message_id: str, rating: str,
                    understood: int, confusion: str) -> dict:
    """记录用户对单条回答的反馈；负反馈自动削弱相关知识点的掌握度并写入 L3。"""
    db.add_feedback(space_id, message_id, rating, understood, confusion)
    negative = rating == "unhelpful" or understood == 0
    if not negative:
        # 正反馈：给该回答涉及的既有知识点轻微加分。
        # 只匹配已存在的知识点——引用片段/回答正文是自然语言，不能拿片段当知识点名新建，
        # 否则会污染掌握度表并流入薄弱点排行与知识图谱。
        msg = db.get_message(message_id) if message_id else None
        matched: list[str] = []
        if msg:
            existing = db.list_mastery(space_id)
            if existing:
                haystack = msg.get("content") or ""
                for c in (msg.get("citations") or [])[:3]:
                    if isinstance(c, dict):
                        haystack += "\n" + (c.get("snippet") or "")
                for row in existing:
                    name = (row.get("point") or "").strip()
                    if len(name) >= 4 and name in haystack and name not in matched:
                        matched.append(name)
                    if len(matched) >= 3:
                        break
        for p in matched:
            db.adjust_mastery(space_id, p, "progress")
        return {"ok": True, "points": matched}

    # 负反馈：定位相关知识并削弱
    msg = db.get_message(message_id) if message_id else None
    question = db.previous_user_message(space_id, message_id) if msg else ""
    ctx_parts = []
    if question:
        ctx_parts.append(f"学生提问：{question[:300]}")
    if msg:
        ctx_parts.append(f"助教回答（节选）：{msg['content'][:400]}")
    if confusion:
        ctx_parts.append(f"学生补充说明哪里没懂：{confusion[:200]}")
    context = "\n".join(ctx_parts) or "学生未说明具体内容"
    try:
        data = llm.chat_json([
            {"role": "system", "content":
                "从学习对话中提取学生没有掌握的知识点。输出 JSON 数组 "
                "[{\"point\":\"知识点短语(10-20字)\"}]，最多 3 个，只输出 JSON。"},
            {"role": "user", "content": context},
        ], temperature=0.2, max_tokens=300, task="extract")
        points = [d.get("point", "").strip() for d in data if isinstance(d, dict) and d.get("point")]
    except Exception:
        points = []
    if not points:
        # 提炼失败且拿不到任何具体表述时直接放弃：把「当前话题」这类占位词
        # 写进掌握度会污染薄弱点排行/知识图谱，且 UI 上几乎无法清除
        if not (confusion or question).strip():
            return {"ok": True, "points": []}
        points = [(confusion or question).strip()[:40]]
    reason = "没听懂" if understood == 0 else "回答没帮助"
    for p in points:
        db.adjust_mastery(space_id, p, "confused")
        extra = f"，补充：{confusion[:80]}" if confusion else ""
        db.add_memory(space_id, 3, f"反馈薄弱（{p}）：学生反馈{reason}{extra}", kind="weakness")
    return {"ok": True, "points": points}


def _l1_block(space_id: str) -> str:
    msgs = db.recent_messages(space_id, 12)
    return "\n".join(f"{m['role']}: {m['content'][:300]}" for m in msgs)


# ---------- 聊天（Ask/Plan/Craft 共用，RAG + 记忆注入） ----------

def build_prompt(space_id: str, mode: str, question: str,
                 guide: bool = False) -> tuple[str, str, list[dict]]:
    """组装系统词（模式 + 记忆档案 + 讲义片段），供普通回复与流式回复共用。

    guide=True 时在 Ask 模式上叠加苏格拉底引导协议。
    返回 (system, expert_key, hits)。
    """
    expert_key = "qa" if mode != "ask" else route_expert(question)
    memory_ctx = build_memory_context(space_id)
    system = _system_for(mode, expert_key)
    if guide:
        system += GUIDE_SUFFIX
    if memory_ctx:
        system += "\n\n以下是该学生的记忆档案，回答时结合其薄弱点个性化作答：\n" + memory_ctx
    # 疲劳检测：零 LLM 成本的正则信号，高疲劳时调整语气与节奏
    fatigue_score = fatigue.detect_fatigue(question)
    fatigue_tip = fatigue.fatigue_hint(fatigue_score)
    if fatigue_tip:
        system += fatigue_tip

    hits = rag.retrieve(space_id, question)
    # 上下文预算：讲义片段总量不超过剩余字符预算，防止 prompt 超长被截断降智
    budget = max(2000, settings.max_context_chars - len(system) - 1200)
    if hits:
        # 只保留真正进入 prompt 的片段：引用列表与模型看到的内容保持一致
        hits = rag.select_hits(hits, budget=budget)
        context = rag.build_context(hits, budget=budget)
    else:
        context = "（知识库暂无相关内容，可提示用户先上传讲义）"
    # 注入当前日期，让模型有时间感知（计划/复习建议更准确）
    from datetime import date
    today_str = date.today().strftime("%Y年%m月%d日")
    system += f"\n\n【当前日期】{today_str}。涉及时间规划时以此为基准。"
    return system + f"\n\n【讲义检索片段】\n{context}", expert_key, hits


_TOOL_PROTOCOL = (
    "\n\n【可用工具】回答前可调用以下外部工具获取信息：\n{tools}\n"
    "如需调用工具，只输出严格 JSON："
    '{{"tool_call":{{"server":"...","tool":"...","arguments":{{}}}}}}；'
    "拿到工具结果后继续作答。不需要工具时正常回答，不要输出任何 JSON。"
)


def _chat_with_tools(messages: list[dict]) -> str:
    """答疑主循环：注册了 MCP 工具时允许模型调用（最多 3 轮工具往返），否则直接补全。"""
    try:
        tools = connectors.all_tools()
    except Exception:
        tools = []
    convo = list(messages)
    if tools:
        convo[0] = {**convo[0], "content": convo[0]["content"] + _TOOL_PROTOCOL.format(
            tools=json.dumps(tools, ensure_ascii=False))}
    raw = ""
    for round_no in range(4):
        raw = llm.chat(convo, task="chat")
        call = None
        data = llm._extract_json(raw)
        if isinstance(data, dict) and isinstance(data.get("tool_call"), dict):
            call = data["tool_call"]
        if not call or not call.get("tool"):
            return raw
        if round_no == 3:  # 轮次用尽：要求模型放弃工具直接作答，而不是把 tool_call JSON 当回答返回
            convo.append({"role": "user", "content":
                          "工具调用轮次已达上限，不要再请求调用工具。请基于已获得的信息直接给出最终回答。"})
            raw = llm.chat(convo, task="chat")
            data = llm._extract_json(raw)
            if isinstance(data, dict) and isinstance(data.get("tool_call"), dict):
                return "（工具调用轮次已达上限，未能获取更多信息。）请换个问法重试，或在模型设置页检查 MCP 服务是否可用。"
            return raw
        try:
            result = connectors.call_mcp_tool(call.get("server", ""), call["tool"],
                                              call.get("arguments") or {})
        except Exception as e:
            result = f"工具调用失败: {e}"
        convo += [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": (f"【工具结果】{result[:2000]}\n"
                                          "请结合以上结果继续；若信息足够，直接给出最终回答。")},
        ]
    return raw


def answer(space_id: str, mode: str, question: str,
           guide: bool = False) -> tuple[str, list[dict], str, str, str]:
    """返回 (回答, 引用, 专家名, 用户消息id, 助手消息id)。"""
    system, expert_key, hits = build_prompt(space_id, mode, question, guide=guide)
    expert_name = EXPERTS.get(expert_key, EXPERTS["qa"])["name"]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question}]
    # 先落库用户提问：模型调用失败时问题不丢失（可刷新后重问）
    user_mid = db.add_message(space_id, mode, "user", question)
    reply = _chat_with_tools(messages)
    citations = [{"index": i + 1, "source": h["source"], "score": round(h["score"], 3),
                  "snippet": h["text"][:120]} for i, h in enumerate(hits)]

    assistant_mid = db.add_message(space_id, mode, "assistant", reply, expert=expert_name, citations=citations)
    maybe_update_memory_async(space_id)
    return reply, citations, expert_name, user_mid, assistant_mid


# ---------- 三层记忆 ----------

_analysis_lock = threading.Lock()  # 学习分析串行化：避免并发对话触发两次分析互踩


def maybe_update_memory_async(space_id: str) -> None:
    """把学习分析放入后台线程：3 次串行 LLM 调用不再阻塞回答返回与流式 done 事件。"""
    threading.Thread(target=_analysis_worker, args=(space_id,),
                     daemon=True, name=f"memory-analysis-{space_id}").start()


def _analysis_worker(space_id: str) -> None:
    try:
        with _analysis_lock:
            maybe_update_memory(space_id)
    except Exception as e:
        # 后台分析失败不影响已返回的回答，只记录现场供排查
        print(f"[studypilot] 学习分析失败（space={space_id}）: {e}", file=sys.stderr)


def maybe_update_memory(space_id: str, every_n_msgs: int = 8) -> None:
    """学习分析：新消息累计达到阈值时运行（用 meta 记录分析位置，不会因技能消息跳跃而漏触发）。

    一次分析做三件事：
    1. L2 摘要：把近期对话压缩成事实摘要；
    2. L3 提取：沉淀知识点掌握状态变化；
    3. 掌握度更新：从对话中提取薄弱点/进步点，更新知识点掌握度模型。
    """
    c = db.get_conn()
    n = c.execute("SELECT COUNT(*) AS n FROM messages WHERE space_id=?", (space_id,)).fetchone()["n"]
    marker = f"analyzed_{space_id}"
    last = int(db.get_meta(marker) or 0)
    if n - last < every_n_msgs:
        return
    l1 = _l1_block(space_id)
    if not l1:
        return

    # 1) L2 摘要
    summary = llm.chat([
        {"role": "system", "content": "把以下学习对话压缩成不超过200字的中文事实摘要，只保留知识点、易错点、学习进度。直接输出摘要。"},
        {"role": "user", "content": l1},
    ], temperature=0.2, task="analyze")

    marker_advanced = False
    try:
        # 分析位点在摘要成功后才推进：中途失败下次还能覆盖这批消息
        db.set_meta(marker, str(n))
        db.clear_memory(space_id, level=2)
        db.add_memory(space_id, 2, summary, kind="summary")
        marker_advanced = True

        # 2) L3 提取（失败不推进位点之外的事：位点已推进，这批消息的 L3 就此错过，
        #    但绝不能让它一路抛上去把整个分析线程打挂）
        l3_raw = llm.chat([
            {"role": "system", "content": (
                "根据摘要和历史档案，提取学生当前的知识点掌握状态变化。"
                "输出严格 JSON 数组，每项 {\"kind\":\"mastery|weakness|error\",\"content\":\"...\"}，最多5条，不要多余文字。")},
            {"role": "user", "content": f"近期摘要：{summary}\n现有档案：{json.dumps(db.list_memory(space_id, 3), ensure_ascii=False)}"},
        ], temperature=0.2, task="extract")
        try:
            text = l3_raw[l3_raw.find("["): l3_raw.rfind("]") + 1]
            for item in json.loads(text):
                db.add_memory(space_id, 3, item.get("content", ""), kind=item.get("kind", ""))
        except (ValueError, json.JSONDecodeError):
            log.warning("L3 记忆提取输出非法 JSON（space=%s），本批跳过", space_id)

        # 3) 掌握度模型更新（对话信号：解释不通/反复追问 → 削弱；顺利理解 → 加固）
        data = llm.chat_json([
            {"role": "system", "content": (
                "根据学习对话判断学生对知识点的掌握变化。输出 JSON："
                "{\"weak\":[{\"point\":\"知识点(10-20字)\",\"evidence\":\"依据(30字内)\"}],"
                "\"strong\":[{\"point\":\"知识点(10-20字)\"}]}，weak/strong 各最多 3 条，只输出 JSON。")},
            {"role": "user", "content": f"近期摘要：{summary}\n现有掌握度：{json.dumps(db.list_mastery(space_id), ensure_ascii=False)}"},
        ], temperature=0.2, max_tokens=600, task="analyze")
        for w in (data.get("weak") or [])[:3]:
            p = (w.get("point") or "").strip()
            if p:
                db.adjust_mastery(space_id, p, "confused")
                db.add_memory(space_id, 3, f"对话薄弱点（{p}）：{(w.get('evidence') or '')[:100]}", kind="weakness")
        for s in (data.get("strong") or [])[:3]:
            p = (s.get("point") or "").strip()
            if p:
                db.adjust_mastery(space_id, p, "progress")
    except Exception:
        # L2 摘要是 clear+add 覆盖式写入、可安全重算：位点回退让下批消息触发时重跑整轮，
        # 而不是让 L3/掌握度阶段静默漏采
        if marker_advanced:
            db.set_meta(marker, str(last))
        log.warning("学习分析第 2/3 阶段失败（space=%s），位点已回退待重试", space_id, exc_info=True)
