"""RAG 向量原子换版：重新索引失败不再丢旧索引（此前 clear→insert 有空窗）。"""
import pytest

from app import db, rag


def _doc_with_file(tmp_path, sid, name="a.txt", content="泰勒公式 是 用多项式逼近函数的工具。"):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    did = db.add_document(sid, name, str(p), doc_id=db.new_id(), content_hash="h-" + name)
    return did, str(p)


def _fake_embed(monkeypatch, dim=2):
    calls = {"n": 0}

    def fake_embed(texts, *a, **k):
        vecs = []
        for _ in texts:
            v = [0.0] * dim
            v[calls["n"] % dim] = 1.0
            calls["n"] += 1
            vecs.append(v)
        return vecs

    monkeypatch.setattr(rag.llm, "embed", fake_embed)


def test_replace_vectors_swaps_atomically(db_space, tmp_path, monkeypatch):
    did, _ = _doc_with_file(tmp_path, db_space)
    _fake_embed(monkeypatch)
    rag.index_document(db_space, did)
    assert len([r for r in db.space_chunks(db_space) if r["document_id"] == did]) == 1

    # 换版到 3 个 chunk：旧行全清、新行全在
    rows = [(db_space, did, i, f"chunk{i}", [1.0, 0.0]) for i in range(3)]
    db.replace_vectors(did, rows)
    chunks = [r for r in db.space_chunks(db_space) if r["document_id"] == did]
    assert [c["chunk_index"] for c in chunks] == [0, 1, 2]


def test_reindex_failure_keeps_old_vectors(db_space, tmp_path, monkeypatch):
    """重新索引中途失败：旧向量必须原样保留，文档状态恢复 ready（检索不受影响）。"""
    did, _ = _doc_with_file(tmp_path, db_space)
    _fake_embed(monkeypatch)
    rag.index_document(db_space, did)
    old_chunks = [r for r in db.space_chunks(db_space) if r["document_id"] == did]
    assert len(old_chunks) == 1

    def broken_parse(path, filename):
        raise ValueError("磁盘文件损坏")

    monkeypatch.setattr(rag, "parse_file", broken_parse)
    with pytest.raises(ValueError):
        rag.index_document(db_space, did)

    chunks = [r for r in db.space_chunks(db_space) if r["document_id"] == did]
    assert chunks == old_chunks  # 旧索引一条不丢


def test_reindex_endpoint_reports_and_restores(db_space, tmp_path, monkeypatch):
    from fastapi import HTTPException

    from app.routers.spaces import api_reindex_document

    did, _ = _doc_with_file(tmp_path, db_space)
    _fake_embed(monkeypatch)
    rag.index_document(db_space, did)

    def broken_parse(path, filename):
        raise ValueError("重新解析失败")

    monkeypatch.setattr(rag, "parse_file", broken_parse)
    with pytest.raises(HTTPException) as ei:
        api_reindex_document(db_space, did)
    assert "原索引未受影响" in ei.value.detail
    doc = db.get_document(did)
    assert doc["status"] == "ready"  # 旧索引还在，学生可继续检索
    assert len([r for r in db.space_chunks(db_space) if r["document_id"] == did]) == 1


def test_reindex_failure_on_never_indexed_doc(db_space, tmp_path, monkeypatch):
    """从未索引成功的文档失败：状态保持 error，不应假装 ready。"""
    from fastapi import HTTPException

    from app.routers.spaces import api_reindex_document

    did, _ = _doc_with_file(tmp_path, db_space, name="b.txt")

    def broken_parse(path, filename):
        raise ValueError("解析失败")

    monkeypatch.setattr(rag, "parse_file", broken_parse)
    with pytest.raises(HTTPException) as ei:
        api_reindex_document(db_space, did)
    assert "原索引未受影响" not in ei.value.detail
    assert db.get_document(did)["status"] == "error"
    assert not [r for r in db.space_chunks(db_space) if r["document_id"] == did]
