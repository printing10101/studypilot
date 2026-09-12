"""教材书库：预置书目 / 上传 / 直链获取 / 挂载到空间。"""
import os

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import db, ingest, library
from .common import MAX_UPLOAD_BYTES, display_name, save_upload_capped, space_or_404

router = APIRouter()


class UrlIn(BaseModel):
    url: str
    title: str = ""


class AttachIn(BaseModel):
    space_id: str


@router.get("/api/library")
def api_library(query: str = "", subject: str = ""):
    return db.list_books(query, subject)


@router.get("/api/library/subjects")
def api_library_subjects():
    return db.list_subjects()


@router.post("/api/library/upload")
def api_library_upload(file: UploadFile = File(...)):
    display = display_name(file)

    def _cleanup(path: str):
        try:
            os.remove(path)
        except OSError:
            pass

    try:
        if ingest.ext_of(display) == ".zip":
            zip_path = save_upload_capped(file, ".zip", MAX_UPLOAD_BYTES)
            try:
                with open(zip_path, "rb") as fobj:
                    return {"batch": library.register_zip(os.path.splitext(display)[0] or "压缩包", fobj)}
            finally:
                _cleanup(zip_path)
        title, ext = os.path.splitext(display)
        path = save_upload_capped(file, ext or ".bin", MAX_UPLOAD_BYTES)
        try:
            with open(path, "rb") as fobj:
                bid = library.register_upload(title or "未命名", ext, fobj)
        except Exception:
            _cleanup(path)  # 入库失败时垃圾文件不留孤儿
            raise
        book = db.get_book(bid)
        return {"id": bid, "status": book["status"] if book else "local"}
    except ValueError as e:
        # 扩展名白名单 / 大小超限 / zip 炸弹防护都是业务拒绝，给 400 而非 500
        raise HTTPException(400, str(e)) from e


@router.post("/api/library/url")
def api_library_import_url(body: UrlIn):
    try:
        return library.import_url(body.url, body.title)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/api/library/{bid}/fetch")
def api_library_fetch(bid: str):
    try:
        return library.fetch_pdf(bid)
    except ValueError as e:
        # 书目不存在 / 无直链 / 下载失败等业务原因，前端弹明确提示而非 500
        raise HTTPException(400, str(e)) from e


@router.post("/api/library/{bid}/attach")
def api_library_attach(bid: str, body: AttachIn):
    space_or_404(body.space_id)
    try:
        return library.attach(bid, body.space_id)
    except ValueError as e:
        # 书目不存在 / 没有本地文件 / 索引失败（含嵌入模型不可用）都是业务拒绝
        raise HTTPException(400, str(e)) from e


@router.get("/api/library/{bid}/spaces")
def api_library_book_spaces(bid: str):
    return db.list_book_spaces(bid)


@router.delete("/api/library/{bid}")
def api_library_delete(bid: str):
    return library.delete_book(bid)
