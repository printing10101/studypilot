"""RAG 管线：PDF/TXT/MD 解析 → 分块 → 向量化 → 检索（带引用）。"""
import os
import re

from . import db, llm

CHUNK_SIZE = 500      # 字符
CHUNK_OVERLAP = 80


def _read_pdf(path: str) -> str:
    import fitz  # pymupdf
    doc = fitz.open(path)
    pages = []
    for i, page in enumerate(doc):
        pages.append(f"[第{i + 1}页]\n{page.get_text()}")
    doc.close()
    return "\n".join(pages)


def _read_text(path: str) -> str:
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"无法解码文件: {path}")


def parse_file(path: str, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return _read_pdf(path)
    if ext in (".txt", ".md", ".markdown"):
        return _read_text(path)
    raise ValueError(f"暂不支持的文件类型: {ext}")


def chunk_text(text: str) -> list[str]:
    text = re.sub(r"\n{3,}", "\n\n", text)
    chunks, start = [], 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            # 尽量在段落/句子边界切
            cut = max(text.rfind("\n\n", start, end), text.rfind("。", start, end))
            if cut > start + CHUNK_SIZE // 2:
                end = cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return chunks


def index_document(space_id: str, document_id: str) -> int:
    """解析并向量化一个已上传文档，返回 chunk 数。"""
    doc = db.get_document(document_id)
    if not doc:
        raise ValueError("文档不存在")
    try:
        text = parse_file(doc["path"], doc["filename"])
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("未解析到文本内容")
        vecs = llm.embed(chunks)
        db.insert_vectors([(space_id, document_id, i, c, v) for i, (c, v) in enumerate(zip(chunks, vecs))])
        db.update_document(document_id, status="ready", chunks=len(chunks))
        return len(chunks)
    except Exception as e:  # 记录错误状态供前端展示
        db.update_document(document_id, status="error", error=str(e)[:500])
        raise


def retrieve(space_id: str, query: str, top_k: int = 6) -> list[dict]:
    """返回 [{text, score, source, chunk_index}]"""
    qvec = llm.embed([query])[0]
    hits = db.search_vectors(space_id, qvec, top_k=top_k)
    for h in hits:
        h["source"] = db.doc_filename(h["document_id"])
    return hits


def build_context(hits: list[dict]) -> str:
    parts = []
    for i, h in enumerate(hits, 1):
        parts.append(f"[片段{i}｜来源: {h['source']}\n{h['text']}]")
    return "\n\n".join(parts)
