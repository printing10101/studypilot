"""概念可视化：规格规整、HTML 渲染转义、技能入库闭环。"""
import pytest

from app import db, llm, rag, visual

_SPEC = {
    "title": "高斯定理",
    "summary": "闭合曲面的电通量只由内部电荷决定",
    "analogy": "像水龙头出水量只看水管截面",
    "formula": {"expr": "Φ = ∮E·dA = Q/ε0", "explain": "Q 为曲面内电荷代数和"},
    "pitfall": "外部电荷不影响通量但会影响场分布",
    "steps": [
        {"label": "是什么", "detail": "电通量与包围电荷的关系", "formula": "Φ = Q/ε0"},
        {"label": "怎么用", "detail": "选对称高斯面", "formula": ""},
    ],
}


def test_normalize_spec_ok():
    spec = visual.normalize_spec("高斯定理", _SPEC)
    assert spec["title"] == "高斯定理"
    assert len(spec["steps"]) == 2
    assert spec["steps"][0]["label"] == "是什么"


def test_normalize_spec_rejects_empty_steps():
    with pytest.raises(ValueError):
        visual.normalize_spec("x", {"title": "t", "steps": []})
    with pytest.raises(ValueError):
        visual.normalize_spec("x", ["不是对象"])


def test_normalize_spec_caps_and_cleans():
    noisy = {**_SPEC, "steps": [
        {"label": f"步{i}", "detail": "长" * 1000, "formula": None} for i in range(20)]}
    spec = visual.normalize_spec("主题", noisy)
    assert len(spec["steps"]) <= visual._MAX_STEPS
    assert all(len(s["detail"]) <= visual._MAX_FIELD for s in spec["steps"])
    assert spec["steps"][0]["formula"] == ""


def test_render_html_escapes_model_output():
    """模型字段里塞脚本/HTML 必须被转义——渲染器绝不能成为注入点。"""
    evil = {**_SPEC, "title": "<script>alert(1)</script>",
            "analogy": "<img src=x onerror=alert(2)>",
            "steps": [{"label": "<b>步</b>", "detail": "</div><script>x()</script>",
                       "formula": "<iframe>"}]}
    out = visual.render_visual_html(visual.normalize_spec("x", evil))
    assert "<script>alert(1)</script>" not in out
    assert "<img src=x" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;iframe&gt;" in out


def test_render_html_structure_and_no_external_refs():
    out = visual.render_visual_html(visual.normalize_spec("高斯定理", _SPEC))
    assert "高斯定理" in out
    assert "Φ = ∮E·dA = Q/ε0" in out
    assert out.count("step-panel") >= 2
    # 自包含：离线可用，不允许任何外部资源引用
    assert "http://" not in out and "https://" not in out
    assert "<iframe" not in out and "srcdoc" not in out.lower()


def test_concept_visualize_persists(db_space, monkeypatch):
    """技能闭环：检索为空也能走通识讲解，LLM 规格入库、返回可渲染 HTML。"""
    monkeypatch.setattr(rag, "retrieve", lambda *a, **k: [])
    captured = {}

    def fake_chat_json(messages, **kw):
        captured["kw"] = kw
        return _SPEC

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    r = visual.concept_visualize(db_space, "高斯定理")
    assert captured["kw"]["task"] == "visualize"
    assert r["steps_count"] == 2 and "<h1>" in r["html"]
    rows = db.list_visuals(db_space)
    assert len(rows) == 1 and rows[0]["title"] == "高斯定理"
    v = db.get_visual(rows[0]["id"])
    assert v["spec"]["summary"] == _SPEC["summary"]


def test_concept_visualize_requires_topic(db_space):
    with pytest.raises(ValueError):
        visual.concept_visualize(db_space, "   ")


def test_concept_visualize_llm_garbage_raises(db_space, monkeypatch):
    monkeypatch.setattr(rag, "retrieve", lambda *a, **k: [])
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {"oops": 1})
    with pytest.raises(ValueError):
        visual.concept_visualize(db_space, "高斯定理")
    assert db.list_visuals(db_space) == []
