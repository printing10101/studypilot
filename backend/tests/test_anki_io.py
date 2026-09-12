"""Anki .apkg 导出/导入闭环（不联网、不调 LLM）。"""
from app import anki_io, db


def test_flashcard_roundtrip_through_apkg(db_space):
    sid = db_space
    db.add_flashcards(sid, [
        {"front": "什么是洛必达法则", "back": "0/0 或 ∞/∞ 型极限的分子分母分别求导", "point": "洛必达法则"},
        {"front": "泰勒公式余项", "back": "拉格朗日余项 / 佩亚诺余项", "point": "泰勒公式"},
    ])
    blob = anki_io.export_apkg(sid)
    assert blob[:2] == b"PK"  # .apkg 是 zip 容器

    other = db.create_space("导入目标")["id"]
    res = anki_io.import_apkg(blob, other)
    assert res["imported"] == 2
    assert res["errors"] == []
    cards = db.list_flashcards(other)
    fronts = {c["front"] for c in cards}
    assert fronts == {"什么是洛必达法则", "泰勒公式余项"}


def test_import_rejects_non_apkg_bytes(db_space):
    res = anki_io.import_apkg(b"this is not a zip", db_space)
    assert res["imported"] == 0
    assert res["errors"]


def test_export_empty_space_still_valid_zip(db_space):
    blob = anki_io.export_apkg(db_space)
    assert blob[:2] == b"PK"
