"""上传入库的公共入口层：受支持的文件类型清单 + 压缩包安全展开。

压缩包防护：
- Zip Slip：磁盘文件名完全不由压缩包成员名构成——落盘一律用
  tempfile.mkstemp 在受控目录内生成（自生成随机名 + 白名单扩展名），
  原始成员名仅作为展示名存数据库，路径逃逸面为零；
- Zip 炸弹：单文件/解压总量双重上限，按实际拷贝字节数计量（不信任 zip 头
  声明的未压缩大小），另有成员数上限；嵌套压缩包跳过，防递归炸弹；
- 不支持的类型跳过。
"""
import os
import tempfile
import zipfile

DOC_EXTS = (".pdf", ".pptx", ".txt", ".md", ".markdown")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
ARCHIVE_EXTS = (".zip",)

# 上传入口接受的完整集合；压缩包内会展开导入的是 DOC+IMAGE
UPLOAD_EXTS = DOC_EXTS + IMAGE_EXTS + ARCHIVE_EXTS
SUPPORTED_EXTS = DOC_EXTS + IMAGE_EXTS

MAX_MEMBER_BYTES = 300 * 1024 * 1024   # 单文件解压上限（与单本教材一致）
MAX_TOTAL_BYTES = 500 * 1024 * 1024    # 解压总量上限
MAX_MEMBERS = 300                      # 压缩包内文件数上限


def ext_of(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


def expand_zip(zip_path: str, dest_root: str) -> list[tuple[str, str]]:
    """安全展开 zip，返回 [(展示文件名, 落盘路径)]（仅受支持的类型）。

    dest_root 由调用方传入受控目录（如上传目录内的临时子目录）；
    每个成员经 mkstemp 在该目录内生成受控新文件，不按路径打开。
    """
    results: list[tuple[str, str]] = []
    total_copied = 0
    os.makedirs(dest_root, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        members = [i for i in z.infolist() if not i.is_dir()]
        if len(members) > MAX_MEMBERS:
            raise ValueError(f"压缩包内文件过多（{len(members)} 个 > 上限 {MAX_MEMBERS}）")
        for info in members:
            # 展示名只取最后一段文件名（丢弃目录成分），仅用于存库展示
            display = os.path.basename(info.filename.replace("\\", "/")).strip() or "未命名"
            ext = ext_of(display)
            # 磁盘名与成员名彻底解耦：mkstemp 自生成名 + 白名单扩展名；
            # 扩展名显式拒绝路径分隔符与相对段（白名单之外的另一道硬校验）
            if (not ext or ext not in SUPPORTED_EXTS
                    or "/" in ext or "\\" in ext or ".." in ext):
                continue
            fd, dst = tempfile.mkstemp(dir=dest_root, suffix=ext)
            copied = 0
            try:
                with os.fdopen(fd, "wb") as f, z.open(info) as src:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > MAX_MEMBER_BYTES or total_copied + copied > MAX_TOTAL_BYTES:
                            raise ValueError(
                                "压缩包含超大文件或解压总量超限（单文件 300MB / 总量 500MB），已中止")
                        f.write(chunk)
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                if os.path.exists(dst):
                    os.remove(dst)
                raise
            total_copied += copied
            results.append((display, dst))
    if not results:
        raise ValueError("压缩包内没有可导入的文件（支持 PDF/PPTX/TXT/Markdown/图片）")
    return results
