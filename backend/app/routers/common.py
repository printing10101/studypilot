"""路由层共享工具：空间校验、上传落盘、文件指纹。"""
import hashlib
import os
import pathlib
import tempfile

from fastapi import HTTPException, UploadFile

from .. import db
from ..config import settings

UPLOAD_ROOT = pathlib.Path(settings.upload_dir).resolve()

MAX_UPLOAD_BYTES = 300 * 1024 * 1024  # 教材 PDF 现实上限；zip 在 expand_zip 内另有解压计量


def space_or_404(sid: str) -> dict:
    """空间存在性校验的统一入口：此前 20+ 端点各自手写，且有一半漏写，
    导致访问不存在的空间时有的 404、有的静默返回空数据。"""
    sp = db.get_space(sid)
    if not sp:
        raise HTTPException(404, "空间不存在")
    return sp


def display_name(file: UploadFile) -> str:
    """上传文件名 → 纯展示名（去路径成分）。四个上传端点共用，避免复制漂移。"""
    return (file.filename or "未命名").replace("\\", "/").rsplit("/", 1)[-1] or "未命名"


def save_upload_capped(file: UploadFile, suffix: str, max_bytes: int) -> str:
    """把上传流按计量拷贝到上传目录的临时文件：无上限的 copyfileobj
    单请求就能写满磁盘。超限抛 ValueError（调用方转 400）。"""
    fd, path = tempfile.mkstemp(dir=UPLOAD_ROOT, suffix=suffix)
    written = 0
    with os.fdopen(fd, "wb") as f:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                os.remove(path)
                raise ValueError(f"文件超过 {max_bytes // (1024 * 1024)}MB 上限")
            f.write(chunk)
    return path


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()
