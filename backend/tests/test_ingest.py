"""压缩包安全展开与扩展名白名单。"""
import os
import zipfile

import pytest

from app import ingest


def test_ext_of_lowercases():
    assert ingest.ext_of("A.PDF") == ".pdf"
    assert ingest.ext_of("x.tar.gz") == ".gz"
    assert ingest.ext_of("noext") == ""


def _mk_zip(tmp_path, entries: dict[str, bytes]) -> str:
    zpath = str(tmp_path / "in.zip")
    with zipfile.ZipFile(zpath, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return zpath


def test_expand_zip_happy_path(tmp_path):
    dest = str(tmp_path / "out")
    zpath = _mk_zip(tmp_path, {"docs/讲义.md": "# 标题".encode(),
                               "图片.png": b"\x89PNG\r\n\x1a\n"})
    members = ingest.expand_zip(zpath, dest)
    assert {n for n, _ in members} == {"讲义.md", "图片.png"}
    # 落盘文件在受控目录内、扩展名保留、内容完整
    for display, path in members:
        assert os.path.dirname(path) == os.path.abspath(dest)
        assert os.path.splitext(path)[1] == os.path.splitext(display)[1]
    md = next(p for n, p in members if n == "讲义.md")
    with open(md, encoding="utf-8") as f:
        assert f.read() == "# 标题"


def test_expand_zip_skips_unsupported_and_nested_zip(tmp_path):
    dest = str(tmp_path / "out")
    zpath = _mk_zip(tmp_path, {"病毒.exe": b"MZ", "inner.zip": b"PK\x05\x06",
                               "notes.txt": b"hello"})
    members = ingest.expand_zip(zpath, dest)
    assert [n for n, _ in members] == ["notes.txt"]


def test_expand_zip_rejects_when_nothing_importable(tmp_path):
    dest = str(tmp_path / "out")
    zpath = _mk_zip(tmp_path, {"a.exe": b"MZ", "b.exe": b"MZ"})
    with pytest.raises(ValueError, match="没有可导入"):
        ingest.expand_zip(zpath, dest)


def test_expand_zip_member_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "MAX_MEMBERS", 3)
    dest = str(tmp_path / "out")
    zpath = _mk_zip(tmp_path, {f"f{i}.txt": b"x" for i in range(4)})
    with pytest.raises(ValueError, match="文件过多"):
        ingest.expand_zip(zpath, dest)


def test_expand_zip_member_size_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(ingest, "MAX_MEMBER_BYTES", 10)
    dest = str(tmp_path / "out")
    zpath = _mk_zip(tmp_path, {"big.txt": b"x" * 64})
    with pytest.raises(ValueError, match="超大文件"):
        ingest.expand_zip(zpath, dest)
