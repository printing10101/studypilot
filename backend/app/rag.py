"""RAG 管线：PDF/PPTX/图片/文本解析 → 分块 → 向量化 → 检索（带引用）。"""
import os
import re

from . import db, ingest, llm

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


def _read_pptx(path: str) -> str:
    """PPTX 文本提取（标准库实现，零依赖）：幻灯片正文 + 讲者备注，按页组织。

    PPTX 是 zip+XML：文本都在 drawingml 的 <a:t> 元素里，逐页抽取即可；
    老的二进制 .ppt 格式不是 zip，不支持（调用方提示转存为 .pptx 或导出 PDF）。
    """
    import re
    import zipfile
    import xml.etree.ElementTree as ET

    A_T = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"
    MAX_XML_BYTES = 2 * 1024 * 1024  # 单个 slide/notes XML 条目上限

    def _texts(xml_bytes: bytes) -> list[str]:
        # 防 XML 实体扩展：解析前拒绝 DTD/实体声明（正常 OOXML 不会出现）
        head = xml_bytes[:2048].lower()
        if b"<!doctype" in head or b"<!entity" in head:
            raise ValueError("PPTX 内含异常 XML 声明，已拒绝解析")
        root = ET.fromstring(xml_bytes)
        return [(t.text or "").strip() for t in root.iter(A_T) if (t.text or "").strip()]

    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            slides = sorted(
                (n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                key=lambda n: int(re.search(r"(\d+)", n).group(1)))
            notes = {int(re.search(r"(\d+)", n).group(1)): n for n in names
                     if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)}
            pages = []
            for i, name in enumerate(slides, 1):
                raw = z.read(name)
                if len(raw) > MAX_XML_BYTES:
                    continue  # 异常超大条目跳过
                texts = _texts(raw)
                page = f"[第{i}页]\n" + "\n".join(texts)
                if notes.get(i):
                    nraw = z.read(notes[i])
                    if len(nraw) <= MAX_XML_BYTES:
                        ntexts = [t for t in _texts(nraw) if not t.isdigit()]  # 去掉页码噪声
                        if ntexts:
                            page += "\n[讲者备注]\n" + "\n".join(ntexts)
                if texts:
                    pages.append(page)
    except zipfile.BadZipFile as e:
        raise ValueError("不是有效的 .pptx 文件（老版 .ppt 请先转存为 .pptx，或导出为 PDF 后上传）") from e
    if not pages:
        raise ValueError("未能从 PPTX 解析到文本（纯图片课件暂不支持，可导出前先补文字或用 PDF 版）")
    return "\n".join(pages)


def _read_text(path: str) -> str:
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"无法解码文件: {path}")


# ---------- 图片 OCR（RapidOCR 离线引擎，模型随包分发、懒加载） ----------

_ocr_engine = None
_ocr_lock = None


def _get_ocr():
    global _ocr_engine, _ocr_lock
    if _ocr_lock is None:
        import threading
        _ocr_lock = threading.Lock()
    if _ocr_engine is None:
        with _ocr_lock:
            if _ocr_engine is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                except ImportError as e:
                    raise ValueError("OCR 引擎未安装（backend 目录取 uv sync 安装 rapidocr-onnxruntime）") from e
                _ocr_engine = RapidOCR()
    return _ocr_engine


def _read_image(path: str) -> str:
    """图片 OCR 提取文字；大图等比缩小到最长边 2000 控制耗时。"""
    import numpy as np
    from PIL import Image
    img = Image.open(path)
    img = img.convert("RGB")
    w, h = img.size
    scale = max(w, h) / 2000.0
    if scale > 1:
        img = img.resize((max(1, int(w / scale)), max(1, int(h / scale))))
    result, _ = _get_ocr()(np.array(img))
    lines = [(item[1] or "").strip() for item in (result or [])]
    lines = [t for t in lines if t]
    if not lines:
        raise ValueError("图片中未识别到文字（可能是纯图形/照片，OCR 无法提取）")
    return "\n".join(lines)


def parse_file(path: str, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return _read_pdf(path)
    if ext == ".pptx":
        return _read_pptx(path)
    if ext in ingest.IMAGE_EXTS:
        return _read_image(path)
    if ext in (".txt", ".md", ".markdown"):
        return _read_text(path)
    if ext == ".ppt":
        raise ValueError("老版 .ppt 为二进制格式，请先在 PowerPoint/WPS 中另存为 .pptx（或导出 PDF）后上传")
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


def build_context(hits: list[dict], budget: int | None = None) -> str:
    """拼接检索片段；超过字符预算时从相关度最低的片段开始丢弃。"""
    parts = []
    for i, h in enumerate(hits, 1):
        parts.append(f"[片段{i}｜来源: {h['source']}\n{h['text']}]")
    ctx = "\n\n".join(parts)
    while budget and len(ctx) > budget and len(parts) > 1:
        parts.pop()
        ctx = "\n\n".join(parts)
    return ctx
