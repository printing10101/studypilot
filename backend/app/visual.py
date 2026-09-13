"""概念可视化（借鉴 DeepTutor Visualize 模式）：抽象知识点 → 单文件交互式讲解页。

设计要点：
- LLM 只产出**结构化 JSON 规格**（标题/直觉解释/类比/分步讲解/公式/常见误解），
  不直接产出 HTML——渲染由本地模板完成并全量转义，模型输出再离谱也不会注入脚本；
- 渲染结果是自包含 HTML（内联 CSS/JS，零外部依赖，离线可用），前端放 sandbox iframe 展示；
- 生成结果存 visuals 表，按空间回看（GET 列表 / 详情按需重渲染，库里只存小规格）。
"""
import html
import logging

from . import db, llm, rag
from .config import settings

log = logging.getLogger("studypilot.visual")

_MAX_STEPS = 8          # 步数上限：超过说明模型跑偏，截断
_MAX_FIELD = 600        # 单文本字段长度上限（防止异常长输出撑爆版面）
_MAX_FORMULA = 300


def _emit(progress, label: str):
    """SSE 进度埋点：progress 由流式端点注入；同步调用（progress=None）时是空操作。"""
    if progress:
        try:
            progress(label)
        except Exception:
            log.debug("progress 回调失败（不影响技能执行）", exc_info=True)


def _clean(s, limit: int = _MAX_FIELD) -> str:
    """字段清洗：None→空串、截断到上限。模型漏字段/超长都不应让技能 500。"""
    t = str(s or "").strip()
    return t[:limit]


def normalize_spec(topic: str, data) -> dict:
    """校验并规整 LLM 输出的可视化规格；不合法时抛 ValueError（技能层映射 400）。"""
    if not isinstance(data, dict):
        raise ValueError("可视化规格格式异常（不是 JSON 对象）")
    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise ValueError("可视化规格缺少讲解步骤（steps）")
    steps = []
    for s in steps_raw[:_MAX_STEPS]:
        if not isinstance(s, dict):
            continue
        label = _clean(s.get("label"), 80)
        if not label:
            continue
        steps.append({
            "label": label,
            "detail": _clean(s.get("detail")),
            "formula": _clean(s.get("formula"), _MAX_FORMULA),
        })
    if not steps:
        raise ValueError("可视化规格的步骤均为空")
    formula = data.get("formula")
    if not isinstance(formula, dict):
        formula = {}
    return {
        "title": _clean(data.get("title"), 80) or topic,
        "summary": _clean(data.get("summary")),
        "analogy": _clean(data.get("analogy")),
        "formula": {
            "expr": _clean(formula.get("expr"), _MAX_FORMULA),
            "explain": _clean(formula.get("explain")),
        },
        "pitfall": _clean(data.get("pitfall")),
        "steps": steps,
    }


def _esc(s: str) -> str:
    return html.escape(str(s or ""), quote=True)


def _step_panel(i: int, step: dict, active: bool) -> str:
    parts = [f'<div class="step-panel{" active" if active else ""}" id="panel-{i}">']
    parts.append(f"<h3>{_esc(step['label'])}</h3>")
    if step["detail"]:
        parts.append(f"<p>{_esc(step['detail'])}</p>")
    if step["formula"]:
        parts.append(f'<pre class="formula">{_esc(step["formula"])}</pre>')
    parts.append("</div>")
    return "\n".join(parts)


def render_visual_html(spec: dict) -> str:
    """规格 → 自包含交互式 HTML。所有模型产出文本经 HTML 转义，无外部资源引用。"""
    nav = "\n".join(
        f'<button class="step-btn{" active" if i == 0 else ""}" data-i="{i}" '
        f'onclick="showStep({i})">{i + 1}. {_esc(s["label"])}</button>'
        for i, s in enumerate(spec["steps"]))
    panels = "\n".join(_step_panel(i, s, active=(i == 0))
                       for i, s in enumerate(spec["steps"]))
    formula = spec.get("formula") or {}
    analogy = spec.get("analogy")
    pitfall = spec.get("pitfall")
    summary = spec.get("summary")
    blocks = []
    if summary:
        blocks.append(f'<p class="summary">{_esc(summary)}</p>')
    if analogy:
        blocks.append(f'<div class="card analogy"><b>生活类比</b>{_esc(analogy)}</div>')
    if formula.get("expr"):
        inner = f'<pre class="formula">{_esc(formula["expr"])}</pre>'
        if formula.get("explain"):
            inner += f'<p>{_esc(formula["explain"])}</p>'
        blocks.append(f'<div class="card">{inner}</div>')
    if pitfall:
        blocks.append(f'<div class="card pitfall"><b>常见误解</b>{_esc(pitfall)}</div>')
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(spec["title"])}</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; margin: 0;
         padding: 24px; background: #fafafa; color: #1c1c1e; line-height: 1.65; }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ font-size: 22px; margin: 0 0 6px; }}
  .summary {{ color: #555; margin: 0 0 18px; }}
  .card {{ background: #fff; border: 1px solid #e3e3e6; border-radius: 10px;
          padding: 14px 16px; margin-bottom: 14px; }}
  .analogy {{ border-left: 4px solid #3478f6; }}
  .pitfall {{ border-left: 4px solid #e6a23c; }}
  .card b {{ display: block; margin-bottom: 4px; }}
  .card p {{ margin: 6px 0 0; }}
  .stepper {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0 12px; }}
  .step-btn {{ border: 1px solid #d6d6da; background: #fff; border-radius: 999px;
              padding: 6px 14px; cursor: pointer; font-size: 13px; }}
  .step-btn.active {{ background: #3478f6; border-color: #3478f6; color: #fff; }}
  .step-panel {{ display: none; background: #fff; border: 1px solid #e3e3e6;
                border-radius: 10px; padding: 14px 16px; }}
  .step-panel.active {{ display: block; }}
  .step-panel h3 {{ margin: 0 0 6px; font-size: 16px; }}
  .step-panel p {{ margin: 6px 0 0; }}
  .formula {{ background: #f4f4f6; border-radius: 8px; padding: 10px 12px;
             font-family: Cambria, "Times New Roman", serif; font-size: 15px;
             white-space: pre-wrap; word-break: break-all; margin: 8px 0; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>{_esc(spec["title"])}</h1>
  {"".join(blocks)}
  <div class="stepper">{nav}</div>
  {panels}
</div>
<script>
function showStep(i) {{
  document.querySelectorAll(".step-panel").forEach(function (p, j) {{
    p.classList.toggle("active", j === i);
  }});
  document.querySelectorAll(".step-btn").forEach(function (b, j) {{
    b.classList.toggle("active", j === i);
  }});
}}
</script>
</body>
</html>"""


def concept_visualize(space_id: str, topic: str, progress=None) -> dict:
    """技能入口：检索讲义 → 生成结构化可视化规格 → 本地模板渲染 → 存档。"""
    topic = topic.strip()
    if not topic:
        raise ValueError("请填写要可视化的知识点")
    _emit(progress, "正在检索讲义…")
    budget = max(2000, settings.max_context_chars - 1500)
    hits = rag.retrieve(space_id, topic, top_k=8)
    context = rag.build_context(hits, budget=budget) if hits else "（无讲义片段，按通识讲解）"
    _emit(progress, "正在生成交互式可视化…（本地模型约 1 分钟）")
    data = llm.chat_json([
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": (
            f"请为知识点「{topic}」生成可视化讲解规格。\n\n讲义片段：\n{context}")},
    ], temperature=0.4, max_tokens=2600, task="visualize")
    spec = normalize_spec(topic, data)
    vid = db.save_visual(space_id, topic, spec["title"], spec["summary"], spec)
    return {"id": vid, "topic": topic, "title": spec["title"],
            "summary": spec["summary"], "steps_count": len(spec["steps"]),
            "html": render_visual_html(spec)}


_SYSTEM = (
    "你是擅长把抽象概念讲直观的学科助教。针对给定知识点产出可视化讲解规格，"
    "输出严格 JSON（不要多余文字）：\n"
    '{"title":"简短标题","summary":"一句话直觉解释",'
    '"analogy":"一个贴切的生活类比（没有贴切的就留空字符串）",'
    '"formula":{"expr":"核心公式（纯文本，可用 ^ _ / √ 等符号，不要 LaTeX 命令）",'
    '"explain":"公式各项含义"},'
    '"steps":[{"label":"步骤名(6字内)","detail":"这一步在讲什么","formula":"该步涉及的表达式，可留空"}],'
    '"pitfall":"最常见的误解或易错点（没有就留空字符串）"}\n'
    "要求：\n"
    "1. steps 3-6 步，按认知顺序递进（是什么→为什么→怎么用→易错在哪）。\n"
    "2. 只依据讲义片段讲解；片段未覆盖的通识内容须准确，不确定的宁可不写。\n"
    "3. detail 面向初学者，避免堆术语；每步不超过 80 字。"
)
