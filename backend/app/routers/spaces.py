"""项目空间：CRUD + 知识库文档 / RAG 索引。"""
import os
import shutil
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import db, ingest, rag
from .common import MAX_UPLOAD_BYTES, UPLOAD_ROOT, display_name, file_sha256, save_upload_capped, space_or_404

router = APIRouter()


class SpaceIn(BaseModel):
    name: str
    description: str = ""


@router.get("/api/spaces")
def api_list_spaces():
    return db.list_spaces()


@router.post("/api/spaces")
def api_create_space(body: SpaceIn):
    return db.create_space(body.name, body.description)


@router.delete("/api/spaces/{sid}")
def api_delete_space(sid: str):
    db.delete_space(sid)
    rag.drop_space_cache(sid)  # 回收该空间的 BM25 索引缓存
    return {"ok": True}


# ---------- 文档 / RAG ----------

@router.get("/api/spaces/{sid}/documents")
def api_list_documents(sid: str):
    return db.list_documents(sid)


@router.post("/api/spaces/{sid}/documents")
def api_upload(sid: str, file: UploadFile = File(...)):
    space_or_404(sid)
    # 原始文件名仅作展示名存库；磁盘文件由 tempfile 在上传目录内生成，用户输入不参与路径
    display = display_name(file)
    ext = ingest.ext_of(display)
    if ext not in ingest.UPLOAD_EXTS:
        raise HTTPException(400, "仅支持 PDF / TXT / Markdown / PPTX / 图片(png/jpg/webp/bmp) / zip 压缩包"
                                "（老版 .ppt 请先另存为 .pptx）")

    if ext == ".zip":
        # 压缩包：安全展开 → 逐个索引，返回批量结果（含跳过清单）
        zip_path = save_upload_capped(file, ".zip", MAX_UPLOAD_BYTES)
        extract_dir = tempfile.mkdtemp(dir=UPLOAD_ROOT, prefix="zip_")
        try:
            members = ingest.expand_zip(zip_path, extract_dir)
        except Exception:
            # 展开失败时已落盘的成员全是孤儿，连同临时目录一起清掉
            shutil.rmtree(extract_dir, ignore_errors=True)
            raise
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        batch = []
        for name, path in members:
            h = file_sha256(path)
            dup = db.find_doc_by_hash(sid, h)
            if dup:
                batch.append({"filename": name, "id": dup["id"], "status": "duplicate",
                              "error": f"与已有讲义《{dup['filename']}》内容相同，已跳过"})
                try:
                    os.remove(path)  # 判重后不保留落盘副本
                except OSError:
                    pass
                continue
            did = db.add_document(sid, name, path, doc_id=db.new_id(), content_hash=h)
            try:
                n = rag.index_document(sid, did)
                batch.append({"filename": name, "id": did, "status": "ready", "chunks": n})
            except Exception as e:
                batch.append({"filename": name, "id": did, "status": "error", "error": str(e)[:200]})
        return {"batch": batch}

    tmp_path = save_upload_capped(file, ext, MAX_UPLOAD_BYTES)
    h = file_sha256(tmp_path)
    dup = db.find_doc_by_hash(sid, h)
    if dup:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise HTTPException(409, f"该文件已在本空间知识库中（《{dup['filename']}》），无需重复上传")
    did = db.new_id()
    db.add_document(sid, display, tmp_path, doc_id=did, content_hash=h)
    try:
        n = rag.index_document(sid, did)
        return {"id": did, "status": "ready", "chunks": n}
    except Exception as e:
        raise HTTPException(400, f"索引失败: {e}") from e


@router.post("/api/spaces/{sid}/documents/{did}/reindex")
def api_reindex_document(sid: str, did: str):
    """重新索引失败/中断的文档：磁盘原文件还在时不必删掉重传整个文件。
    此前索引失败只有一个出口——删除后重传，大文件代价很高。

    向量写入是原子换版（db.replace_vectors）：不再预先 clear_vectors，
    重新索引失败时已索引文档的旧向量原样保留、检索不受影响。"""
    space_or_404(sid)
    doc = db.get_document(did)
    if not doc or doc["space_id"] != sid:
        raise HTTPException(404, "文档不存在")
    if not doc["path"] or not os.path.exists(doc["path"]):
        raise HTTPException(400, "原文件已丢失，请删除该讲义后重新上传")
    prev_status = doc["status"]
    db.update_document(did, status="pending", error="")
    try:
        n = rag.index_document(sid, did)
        return {"id": did, "status": "ready", "chunks": n}
    except HTTPException:
        raise
    except Exception as e:
        # 旧索引还在（原子换版保证）：已索引文档恢复 ready，学生可继续用旧索引检索
        if prev_status == "ready" and any(r["document_id"] == did for r in db.space_chunks(sid)):
            db.update_document(did, status="ready", error="")
            raise HTTPException(400, f"重新索引失败（原索引未受影响，仍可正常检索）: {e}") from e
        raise HTTPException(400, f"重新索引失败: {e}") from e


@router.delete("/api/spaces/{sid}/documents/{did}")
def api_delete_document(sid: str, did: str):
    """删除知识库文档（含向量、磁盘文件；若为挂载教材则同时解除挂载）。"""
    space_or_404(sid)
    doc = db.get_document(did)
    if not doc or doc["space_id"] != sid:
        raise HTTPException(404, "文档不存在")
    # 挂载教材的文档与书库文件同路径且可被多空间共享，只解除挂载、不删磁盘文件
    db.delete_document(did, remove_file=not db.document_is_book(did))
    return {"ok": True}
