"""RAG 文本层：编码嗅探、分块、上下文预算、真实 Markdown 夹具解析。"""
import pathlib

from app import rag

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _write(tmp_path, name: str, data: bytes) -> str:
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_read_text_utf8_and_utf8_sig(tmp_path):
    p = _write(tmp_path, "a.txt", "极限与连续".encode())
    assert rag._read_text(p) == "极限与连续"
    p = _write(tmp_path, "b.txt", b"\xef\xbb\xbf" + "泰勒公式".encode())
    assert rag._read_text(p) == "泰勒公式"


def test_read_text_gb18030(tmp_path):
    p = _write(tmp_path, "c.txt", "拉格朗日中值定理".encode("gb18030"))
    assert rag._read_text(p) == "拉格朗日中值定理"


def test_read_text_utf16_bom(tmp_path):
    p = _write(tmp_path, "d.txt", "洛必达法则".encode("utf-16"))
    assert rag._read_text(p) == "洛必达法则"


def test_chunk_text_respects_sentence_boundary():
    para = "第一句话讲概念。第二句话给公式。第三句话举例子。" * 30  # > CHUNK_SIZE(500)
    chunks = rag.chunk_text(para)
    assert len(chunks) >= 2
    assert all(c.strip() for c in chunks)
    assert chunks[0].startswith("第一句话")


def test_chunk_text_short_input_single_chunk():
    assert rag.chunk_text("短文本") == ["短文本"]
    assert rag.chunk_text("") == []


def test_parse_file_on_markdown_fixture():
    """真实讲义 Markdown 夹具：内容完整解析、可分块（原手动上传测试样例转正为测试资产）。"""
    text = rag.parse_file(str(FIXTURES / "uploads_test_optics.md"), "uploads_test_optics.md")
    assert "几何光学" in text and "斯涅尔定律" in text
    assert len(rag.chunk_text(text)) >= 1


def test_build_context_respects_budget():
    hits = [{"index": i + 1, "source": f"s{i}.pdf", "score": 0.9 - i * 0.1,
             "text": "内容" * 200} for i in range(6)]
    ctx = rag.build_context(hits, budget=500)
    assert len(ctx) <= 600  # 预算附近（允许标题行开销）
    assert "[1]" in ctx or "s0" in ctx  # 最相关的片段一定保留
