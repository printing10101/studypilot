"""RAG 管线：PDF/PPTX/图片/文本解析 → 分块 → 向量化 → 混合检索（带引用）。

检索为双通道：向量（语义）+ BM25（词法，中文按字 bigram），RRF 融合排序——
专有名词、公式符号、章节标题等"词面精确匹配"场景向量检索常漏召，词法通道补齐；
可选 cross-encoder 精排（settings.rerank_model 配置后启用）。
"""
import math
import os
import re
import threading
import time
import zipfile
from collections import Counter

from . import db, ingest, llm
from .config import settings

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
    import xml.etree.ElementTree as ET
    import zipfile

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
                # 声明 3KB 实际可膨胀数 GB 的 zip 炸弹：流式读取并在上限处截断，
                # 不能 z.read 整体进内存后再检查
                raw = _read_capped(z, name, MAX_XML_BYTES)
                if raw is None:
                    continue
                texts = _texts(raw)
                page = f"[第{i}页]\n" + "\n".join(texts)
                if notes.get(i):
                    nraw = _read_capped(z, notes[i], MAX_XML_BYTES)
                    if nraw is not None:
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


def _read_capped(z: zipfile.ZipFile, name: str, cap: int) -> bytes | None:
    """流式读取 zip 成员，超过 cap 字节返回 None（防声明大小造假的炸弹）。"""
    total = 0
    parts = []
    with z.open(name) as src:
        while True:
            chunk = src.read(256 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                return None
            parts.append(chunk)
    return b"".join(parts)


def _read_text(path: str) -> str:
    import codecs
    with open(path, "rb") as f:
        head = f.read(4)
    # 先嗅探 BOM：带 BOM 的 UTF-16 大多能被 gb18030「成功」解码成乱码，
    # 纯 try-encoding 顺序会永远走不到 utf-16 分支
    if head.startswith(codecs.BOM_UTF16_LE) or head.startswith(codecs.BOM_UTF16_BE):
        try:
            with open(path, encoding="utf-16") as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            pass
    for enc in ("utf-8-sig", "gb18030", "utf-16"):
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
    """解析并向量化一个已上传文档，返回 chunk 数。

    向量写入走 db.replace_vectors 原子换版：解析/嵌入全部成功后才替换旧索引，
    中途失败时已索引文档的旧向量原样保留（重新索引不再有"删了旧的、新的没写上"的空窗）。"""
    doc = db.get_document(document_id)
    if not doc:
        raise ValueError("文档不存在")
    try:
        text = parse_file(doc["path"], doc["filename"])
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("未解析到文本内容")
        vecs = llm.embed(chunks)
        rows = [(space_id, document_id, i, c, v)
                for i, (c, v) in enumerate(zip(chunks, vecs, strict=True))]
        db.replace_vectors(document_id, rows)
        db.update_document(document_id, status="ready", chunks=len(chunks))
        return len(chunks)
    except Exception as e:  # 记录错误状态供前端展示
        db.update_document(document_id, status="error", error=str(e)[:500])
        raise


# ---------- 混合检索：向量通道 + BM25 词法通道，RRF 融合 ----------

_RRF_K = 60          # Reciprocal Rank Fusion 常数（论文经验值，平滑排名差异）
_FETCH_MULT = 3      # 每通道超采倍数：先取 top(3k) 再融合截到 top_k
_BM25_K1 = 1.5
_BM25_B = 0.75

_bm25_lock = threading.Lock()  # 仅保护 _bm25_cache 的并发写（索引重建幂等，竞争无害但避免重复劳动）
_bm25_cache: dict[str, tuple[tuple, dict]] = {}   # space_id -> (行签名, 索引)


def drop_space_cache(space_id: str) -> None:
    """删除空间后回收其 BM25 索引缓存（含全量 token Counter，不清理会一直滞留内存）。"""
    with _bm25_lock:
        _bm25_cache.pop(space_id, None)
_reranker = None
_reranker_lock = threading.Lock()
_reranker_failed_at = 0.0
_RERANKER_RETRY_INTERVAL = 3600.0  # 加载失败后的冷却期（秒），期内直接回退融合序


def _tokenize(text: str) -> list[str]:
    """中文检索分词（零依赖）：连续拉丁/数字按整词，CJK 连续段拆 字+二元组。
    单字与二元组都入索引——常用单字（的/是）由 BM25 的 IDF 自然降权。"""
    tokens: list[str] = []
    for m in re.finditer(r"[a-z0-9_]+|[\u4e00-\u9fff]+", text.lower()):
        run = m.group(0)
        if run[0].isascii():
            tokens.append(run)
            continue
        tokens.extend(run)                      # 单字
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))  # 二元组
    return tokens


def _bm25_index(texts: list[str]) -> dict:
    tfs, lens, df = [], [], Counter()
    for t in texts:
        tf = Counter(_tokenize(t))
        tfs.append(tf)
        lens.append(sum(tf.values()))
        df.update(tf.keys())
    n = max(1, len(texts))
    idf = {term: math.log(1.0 + (n - d + 0.5) / (d + 0.5)) for term, d in df.items()}
    return {"tfs": tfs, "lens": lens, "idf": idf, "avgdl": (sum(lens) / n) or 1.0}


def _bm25_scores(space_id: str, rows: list[dict], query: str) -> list[tuple[int, float]]:
    """BM25 打分，返回 [(rows 下标, 得分)] 按分降序。索引按空间缓存（行集合变了才重建）。"""
    sig = (len(rows), hash(tuple(r["id"] for r in rows)))
    cached = _bm25_cache.get(space_id)
    if cached and cached[0] == sig:
        index = cached[1]
    else:
        index = _bm25_index([r["text"] for r in rows])
        with _bm25_lock:
            _bm25_cache[space_id] = (sig, index)
    q_terms = {t for t in _tokenize(query) if t in index["idf"]}
    if not q_terms:
        return []
    out = []
    for i, (tf, dl) in enumerate(zip(index["tfs"], index["lens"], strict=True)):
        s = 0.0
        for t in q_terms:
            f = tf.get(t, 0)
            if f:
                s += index["idf"][t] * f * (_BM25_K1 + 1.0) / (
                    f + _BM25_K1 * (1.0 - _BM25_B + _BM25_B * dl / index["avgdl"]))
        if s > 0:
            out.append((i, s))
    out.sort(key=lambda x: -x[1])
    return out


def _vector_scores(rows: list[dict], qvec: list[float]) -> list[tuple[int, float]]:
    """余弦相似度打分（写入时已归一化，点积即余弦），跳过维度不一致的旧向量。"""
    import numpy as np
    q = np.asarray(qvec, dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-9)
    out = []
    for i, r in enumerate(rows):
        v = np.frombuffer(r["embedding"], dtype=np.float32)
        if v.shape[0] == q.shape[0]:
            out.append((i, float(v @ q)))
    out.sort(key=lambda x: -x[1])
    return out


def _get_reranker():
    """懒加载 cross-encoder 精排模型（settings.rerank_model），加载失败返回 None。

    失败后冷却 1 小时内不再尝试：模型下载失败时反复重试会让每次检索都付出加载开销。"""
    global _reranker, _reranker_failed_at
    if not settings.rerank_model:
        return None
    if _reranker is None and time.time() - _reranker_failed_at < _RERANKER_RETRY_INTERVAL:
        return None
    if _reranker is None:
        with _reranker_lock:
            if _reranker is None:
                if time.time() - _reranker_failed_at < _RERANKER_RETRY_INTERVAL:
                    return None
                try:
                    from sentence_transformers import CrossEncoder
                    _reranker = CrossEncoder(settings.rerank_model, max_length=512)
                except Exception:
                    _reranker_failed_at = time.time()
                    return None  # 模型下载失败/无网络等：静默回退融合序，不阻塞答疑
    return _reranker


def _rerank(query: str, hits: list[dict]) -> list[dict]:
    """cross-encoder 精排：对融合后的候选重打分（sigmoid 到 0..1），失败保持原序。"""
    if len(hits) < 2:
        return hits
    model = _get_reranker()
    if model is None:
        return hits
    try:
        import numpy as np
        pairs = [(query, h["text"][:1500]) for h in hits]
        logits = np.asarray(model.predict(pairs), dtype=np.float64)
        scores = 1.0 / (1.0 + np.exp(-logits))  # sigmoid 压到 0..1 作展示相关度
        order = np.argsort(-scores)
        return [{**hits[i], "score": round(float(scores[i]), 3)} for i in order]
    except Exception:
        return hits


def retrieve(space_id: str, query: str, top_k: int = 6) -> list[dict]:
    """混合检索：向量（语义）+ BM25（词法）RRF 融合，可选精排。
    返回 [{text, score, source, chunk_index}]；score 为展示用相关度
    （纯向量=余弦值；融合=RRF 归一化 Top1=1.0；精排=sigmoid）。"""
    rows = db.space_chunks(space_id)
    if not rows:
        return []
    fetch_k = max(top_k * _FETCH_MULT, 12)
    try:
        qvec = llm.embed([query])[0]
    except Exception as e:
        # embed 失败（嵌入模型缺失/下载失败）原本以 OSError 等类型裸抛，
        # 端点只捕 RuntimeError → 用户看到 500 而不是「模型不可用」的 502
        raise RuntimeError(f"向量检索不可用：{e}") from e
    vec_ranked = _vector_scores(rows, qvec)[:fetch_k]
    if not settings.hybrid_search:
        ranked = _rerank(query, [
            {"id": rows[i]["id"], "document_id": rows[i]["document_id"],
             "chunk_index": rows[i]["chunk_index"], "text": rows[i]["text"],
             "score": round(s, 4)} for i, s in vec_ranked[:top_k]])
        hits = ranked
    else:
        fused: dict[int, float] = {}
        for rank, (i, _s) in enumerate(vec_ranked):
            fused[i] = fused.get(i, 0.0) + 1.0 / (_RRF_K + rank + 1)
        for rank, (i, _s) in enumerate(_bm25_scores(space_id, rows, query)[:fetch_k]):
            fused[i] = fused.get(i, 0.0) + 1.0 / (_RRF_K + rank + 1)
        order = sorted(fused.items(), key=lambda kv: -kv[1])[:top_k]
        top_score = order[0][1] if order else 0.0
        hits = [{"id": rows[i]["id"], "document_id": rows[i]["document_id"],
                 "chunk_index": rows[i]["chunk_index"], "text": rows[i]["text"],
                 "score": round(f / top_score, 3) if top_score else 0.0} for i, f in order]
        hits = _rerank(query, hits)
    for h in hits:
        h["source"] = db.doc_filename(h["document_id"])
    return hits


def select_hits(hits: list[dict], budget: int | None = None) -> list[dict]:
    """按字符预算筛出实际会进入上下文的片段（丢弃从相关度最低的开始），
    供引用列表与 prompt 内容对齐。"""
    kept = list(hits)

    def _join(ps):
        return "\n\n".join(f"[片段{i}｜来源: {h['source']}\n{h['text']}]" for i, h in enumerate(ps, 1))

    ctx = _join(kept)
    while budget and len(ctx) > budget and len(kept) > 1:
        kept.pop()
        ctx = _join(kept)
    return kept


def build_context(hits: list[dict], budget: int | None = None) -> str:
    """拼接检索片段；超过字符预算时从相关度最低的片段开始丢弃（单个超长片段截断到预算）。"""
    parts = []
    for i, h in enumerate(hits, 1):
        parts.append(f"[片段{i}｜来源: {h['source']}\n{h['text']}]")
    ctx = "\n\n".join(parts)
    while budget and len(ctx) > budget and len(parts) > 1:
        parts.pop()
        ctx = "\n\n".join(parts)
    if budget and len(ctx) > budget:
        ctx = ctx[:budget]
    return ctx
