"""LLM 网关的纯函数部分：JSON 抽取与任务路由配置完整性。"""
from app import llm


def test_extract_json_whole_object():
    assert llm._extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_with_surrounding_prose():
    assert llm._extract_json('好的，结果如下：{"missed": [], "wrong": [2]} 以上。') == \
        {"missed": [], "wrong": [2]}


def test_extract_json_prefers_object_over_inner_array():
    # 对象内嵌数组：先截 {}，不能把内层数组误当结果
    raw = '说明 {"items": [1, 2], "total": 2} 完毕'
    assert llm._extract_json(raw) == {"items": [1, 2], "total": 2}


def test_extract_json_bare_array_fallback():
    assert llm._extract_json('["甲", "乙"]') == ["甲", "乙"]


def test_extract_json_invalid_returns_none():
    assert llm._extract_json("模型拒绝输出 JSON") is None
    assert llm._extract_json("") is None


def test_task_routing_entries_are_complete():
    assert llm.TASK_ROUTING, "路由表不能为空"
    for task, cfg in llm.TASK_ROUTING.items():
        assert cfg["priority"] in ("local", "cloud"), task
        assert 0.0 <= cfg["temp"] <= 2.0, task
        assert cfg["max_tokens"] > 0, task
