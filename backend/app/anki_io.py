"""Anki 牌组导入导出。

借鉴 LearnKit：支持 .apkg (Anki 2.1 zip 格式) 导入闪卡、导出闪卡为 .apkg。
.apkg = zip 包含 collection.anki2 (SQLite) + media/。
导入时映射 FSRS 调度字段（state/stability/difficulty/last_review/due）。
"""
import io
import json
import os
import re
import sqlite3
import tempfile
import time
import uuid
import zipfile

from . import db, fsrs

# Anki 2.1 collection schema 关键表
# col: 集合元数据
# notes: 笔记（字段拼接）
# cards: 卡片（指向 note，含调度状态）
# revlog: 复习日志


def import_apkg(file_bytes: bytes, space_id: str) -> dict:
    """导入 .apkg 文件，将闪卡写入指定空间。

    返回 {"imported": n, "skipped": n, "errors": [...]}。
    """
    imported, skipped = 0, 0
    errors: list[str] = []

    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile:
        return {"imported": 0, "skipped": 0, "errors": ["不是有效的 .apkg 文件（zip 损坏）"]}

    # .apkg 也是 zip：先按声明大小做廉价预检，再在读取成员时按实际字节计量——
    # 恶意包会谎报 file_size，信任 zip 头等于没有防护（同 ingest.expand_zip 的立场）
    _MAX_UNCOMPRESSED = 500 * 1024 * 1024
    _COL_MEMBER_LIMIT = 200 * 1024 * 1024
    if sum(i.file_size for i in zf.infolist()) > _MAX_UNCOMPRESSED:
        return {"imported": 0, "skipped": 0,
                "errors": [f".apkg 解压后超过 {_MAX_UNCOMPRESSED // (1024 * 1024)}MB 上限，已拒绝"]}

    # 找 collection.anki2 或 collection.anki21（fullmatch，避免误匹配 "collection.anki2evil"）
    col_name = None
    for name in zf.namelist():
        if re.fullmatch(r"collection\.anki2(1)?", name):
            col_name = name
            break
    if not col_name:
        return {"imported": 0, "skipped": 0, "errors": [".apkg 中未找到 collection.anki2"]}

    # 流式解压到临时 SQLite：按实际拷贝字节计量，超限即中止
    chunks = []
    total = 0
    with zf.open(col_name) as src:
        while True:
            chunk = src.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > _COL_MEMBER_LIMIT:
                return {"imported": 0, "skipped": 0,
                        "errors": [f"collection.anki2 解压后超过 {_COL_MEMBER_LIMIT // (1024 * 1024)}MB 上限，已拒绝"]}
            chunks.append(chunk)
    with tempfile.NamedTemporaryFile(suffix=".anki2", delete=False) as tmp:
        for chunk in chunks:
            tmp.write(chunk)
        tmp_path = tmp.name
    del chunks

    try:
        conn = sqlite3.connect(tmp_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # 读笔记：flds = 字段用 \x1f 连接；sfld = 第一个字段（用于去重）
        notes = {}
        for row in c.execute("SELECT id, flds, tags FROM notes"):
            fields = row["flds"].split("\x1f")
            front = fields[0].strip() if fields else ""
            back = fields[1].strip() if len(fields) > 1 else ""
            # HTML 清理：去掉基础标签
            front = _strip_html(front)
            back = _strip_html(back)
            if not front:
                continue
            notes[row["id"]] = {
                "front": front,
                "back": back,
                "tags": (row["tags"] or "").strip(),
            }

        # 读卡片调度状态
        # type: 0=新卡 1=学习 2=复习 3=重学
        # queue: -3=重复学习 -2/-1=隐藏 0=新卡 1=学习 2=复习 3=当日学习
        # ivl: 间隔天数（复习卡为正，学习卡为负=分钟）
        # factor: 简易度 ×1000（2500=250%）
        # reps, lapses
        pending: list[dict] = []  # (闪卡字段, 调度列) 成对收集，最后一次性入库
        for row in c.execute(
            "SELECT nid, type, queue, ivl, factor, reps, lapses, due FROM cards"
        ):
            note = notes.get(row["nid"])
            if not note:
                skipped += 1
                continue

            # Anki type → FSRS state: 0→0(new), 1→1(learning), 2→2(review), 3→3(relearning)
            anki_type = row["type"] or 0
            fsrs_state = {0: 0, 1: 1, 2: 2, 3: 3}.get(anki_type, 0)

            # 稳定性估算：Anki ivl 天数 → FSRS stability ≈ ivl
            ivl = row["ivl"] or 0
            if ivl > 0:
                stability = float(ivl)
            elif ivl < 0:
                stability = abs(ivl) / 1440.0  # 分钟转天
            else:
                stability = 0.0

            # 难度：Anki factor 2500=简单(250%) → FSRS 难度低；factor 越小越难
            factor = row["factor"] or 2500
            # factor 1300~3000 映射到 FSRS difficulty 1~10（反向）
            diff = 10.0 - (factor - 1300) / (3000 - 1300) * 9.0
            diff = max(1.0, min(10.0, diff))

            reps = row["reps"] or 0
            lapses = row["lapses"] or 0

            # due：Anki due 对复习卡是天数差，对新卡/学习卡是时间戳
            now_ts = time.time()
            if anki_type == 2 and ivl > 0:
                # 复习卡：due 是"距今天的天数"（相对集合创建日）
                # 简化：按 due 天数从现在起算
                due_at = now_ts + max(0, row["due"] or 0) * 86400
            else:
                due_at = now_ts  # 新卡/学习卡立即到期

            pending.append({
                "card": {"front": note["front"], "back": note["back"],
                         "point": note["tags"] or ""},
                "sched": (min(5, max(1, int(stability / 7) + 1)), due_at,
                          fsrs_state, stability, diff,
                          now_ts - (ivl * 86400 if ivl > 0 else 0), reps, lapses),
            })

        # 万卡牌组逐卡 commit 会慢到不可用：一次批量插入 + 一次批量 UPDATE
        saved = db.add_flashcards(space_id, [p["card"] for p in pending])
        if len(saved) == len(pending):
            c2 = db.get_conn()
            c2.executemany(
                "UPDATE flashcards SET box=?, due_at=?, state=?, step=?, "
                "stability=?, difficulty=?, last_review=?, reps=?, lapses=? WHERE id=?",
                [(*p["sched"], fid) for p, fid in zip(pending, (s["id"] for s in saved))])
            c2.commit()
            imported = len(saved)
        else:
            skipped += len(pending)

        conn.close()
    except sqlite3.Error as e:
        errors.append(f"SQLite 读取失败: {e}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    return {"imported": imported, "skipped": skipped, "errors": errors}


def export_apkg(space_id: str) -> bytes:
    """将空间内闪卡导出为 .apkg 字节流。

    生成最小可用的 Anki 2.1 collection.anki2 + 空 media。
    """
    cards = db.list_flashcards(space_id)
    space = db.get_space(space_id)
    deck_name = f"StudyPilot::{space['name'] if space else space_id}"

    # 构建临时 SQLite（sqlite3.connect 不接受 BytesIO，与导入侧同样落临时文件）
    fd, col_path = tempfile.mkstemp(suffix=".anki2")
    os.close(fd)
    conn = sqlite3.connect(col_path)
    c = conn.cursor()

    # Anki 2.1 最小 schema
    c.executescript("""
        CREATE TABLE col (
            id integer PRIMARY KEY,
            crt integer NOT NULL,
            mod integer NOT NULL,
            scm integer NOT NULL,
            ver integer NOT NULL,
            dty integer NOT NULL,
            usn integer NOT NULL,
            ls integer NOT NULL,
            conf text NOT NULL,
            models text NOT NULL,
            decks text NOT NULL,
            dconf text NOT NULL,
            tags text NOT NULL
        );
        CREATE TABLE notes (
            id integer PRIMARY KEY,
            guid text NOT NULL,
            mid integer NOT NULL,
            mod integer NOT NULL,
            usn integer NOT NULL,
            tags text NOT NULL,
            flds text NOT NULL,
            sfld text NOT NULL,
            csum integer NOT NULL,
            flags integer NOT NULL,
            data text NOT NULL
        );
        CREATE TABLE cards (
            id integer PRIMARY KEY,
            nid integer NOT NULL,
            did integer NOT NULL,
            ord integer NOT NULL,
            mod integer NOT NULL,
            usn integer NOT NULL,
            type integer NOT NULL,
            queue integer NOT NULL,
            due integer NOT NULL,
            ivl integer NOT NULL,
            factor integer NOT NULL,
            reps integer NOT NULL,
            lapses integer NOT NULL,
            left integer NOT NULL,
            odue integer NOT NULL,
            odid integer NOT NULL,
            flags integer NOT NULL,
            data text NOT NULL
        );
        CREATE TABLE revlog (
            id integer PRIMARY KEY,
            cid integer NOT NULL,
            usn integer NOT NULL,
            ease integer NOT NULL,
            ivl integer NOT NULL,
            lastIvl integer NOT NULL,
            factor integer NOT NULL,
            time integer NOT NULL,
            type integer NOT NULL
        );
        CREATE TABLE graves (
            usn integer NOT NULL,
            oid integer NOT NULL,
            type integer NOT NULL
        );
        CREATE INDEX ix_notes_usn ON notes (usn);
        CREATE INDEX ix_cards_usn ON cards (usn);
        CREATE INDEX ix_cards_nid ON cards (nid);
        CREATE INDEX ix_cards_sched ON cards (did, queue, due);
        CREATE INDEX ix_revlog_usn ON revlog (usn);
        CREATE INDEX ix_revlog_cid ON revlog (cid);
    """)

    now_ms = int(time.time() * 1000)
    now_s = int(time.time())

    # model (note type)：Basic
    model_id = 1600000000001
    deck_id = 1600000000002
    models = {
        str(model_id): {
            "id": model_id, "name": "StudyPilot Basic", "type": 0,
            "mod": now_s, "usn": -1, "sortf": 0, "did": deck_id,
            "tmpls": [{
                "name": "Card 1", "ord": 0, "qfmt": "{{Front}}", "afmt": "{{Front}}<hr>{{Back}}",
                "did": None, "bqfmt": "", "bafmt": "", "bfont": "", "bsize": 0,
            }],
            "flds": [
                {"name": "Front", "ord": 0, "sticky": False, "rtl": False,
                 "font": "Arial", "size": 20, "media": []},
                {"name": "Back", "ord": 1, "sticky": False, "rtl": False,
                 "font": "Arial", "size": 20, "media": []},
            ],
            "css": ".card { font-family: arial; font-size: 20px; text-align: center; }",
            "latexPre": "", "latexPost": "",
            "latexsvg": False, "req": [[0, "any", [0]]],
            "vers": [], "tags": [],
        }
    }
    decks = {
        "1": {"id": 1, "name": "Default", "mod": now_s, "usn": -1,
              "lrnToday": [0, 0], "revToday": [0, 0], "newToday": [0, 0],
              "timeToday": [0, 0], "collapsed": False, "browserCollapsed": False,
              "desc": "", "dyn": 0, "conf": 1, "extendNew": 0, "extendRev": 0},
        str(deck_id): {"id": deck_id, "name": deck_name, "mod": now_s, "usn": -1,
                       "lrnToday": [0, 0], "revToday": [0, 0], "newToday": [0, 0],
                       "timeToday": [0, 0], "collapsed": False, "browserCollapsed": False,
                       "desc": "Exported from StudyPilot", "dyn": 0, "conf": 1,
                       "extendNew": 0, "extendRev": 0},
    }
    dconf = {
        "1": {"id": 1, "name": "Default", "mod": now_s, "usn": -1,
              "maxTaken": 60, "autoplay": True, "timer": 0, "replayq": True,
              "new": {"delays": [1, 10], "ints": [1, 4, 7], "initialFactor": 2500,
                      "separate": True, "order": 1, "perDay": 20, "bury": False},
              "rev": {"perDay": 200, "ease4": 1.3, "fuzz": 0.05, "ivlFct": 1.0,
                      "maxIvl": 36500, "bury": False, "hardFactor": 1.2},
              "lapse": {"delays": [10], "mult": 0.0, "minInt": 1, "leechFails": 8,
                        "leechAction": 0},
              "dyn": False},
    }
    conf = {
        "nextPos": 1, "estTimes": True, "activeDecks": [1],
        "sortType": "noteFld", "timeLim": 0, "sortBackwards": False,
        "addToCur": True, "curDeck": 1, "newBury": True, "newSpread": 0,
        "dueCounts": True, "curModel": str(model_id), "collapseTime": 1200,
    }
    c.execute(
        "INSERT INTO col VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (1, now_s, now_ms, now_ms, 11, 0, 0, 0,
         json.dumps(conf), json.dumps(models), json.dumps(decks),
         json.dumps(dconf), "{}"),
    )

    for i, card in enumerate(cards):
        note_id = now_ms + i * 1000
        card_id = now_ms + i * 1000 + 1
        front = (card.get("front") or "").replace("\x1f", " ")
        back = (card.get("back") or "").replace("\x1f", " ")
        flds = f"{front}\x1f{back}"
        # Anki csum: 前 8 位 hex of sha1 of stripped front
        import hashlib
        stripped = _strip_html(front).strip()
        csum = int(hashlib.sha1(stripped.encode("utf-8")).hexdigest()[:8], 16)

        tags = f" {card.get('point', '')} " if card.get("point") else ""

        c.execute(
            "INSERT INTO notes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (note_id, f"sp{i:08d}", model_id, now_s, -1, tags, flds, stripped, csum, 0, ""),
        )

        # FSRS state → Anki type
        st = card.get("state", 0) or 0
        anki_type = {0: 0, 1: 1, 2: 2, 3: 3}.get(st, 0)
        anki_queue = anki_type  # 简化映射
        stability = card.get("stability", 0) or 0
        ivl = max(1, int(stability)) if st >= 2 else 0
        # FSRS difficulty 1-10 → Anki factor（反向）
        d = card.get("difficulty", 5) or 5
        factor = int(1300 + (10 - d) / 9.0 * 1700)
        factor = max(1300, min(3000, factor))

        reps = card.get("reps", 0) or 0
        lapses = card.get("lapses", 0) or 0
        due = max(0, int((card.get("due_at", 0) or 0) - time.time()) // 86400)

        c.execute(
            "INSERT INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (card_id, note_id, deck_id, 0, now_s, -1, anki_type, anki_queue,
             due, ivl, factor, reps, lapses, 0, 0, 0, 0, ""),
        )

    conn.commit()
    conn.close()
    with open(col_path, "rb") as f:
        col_bytes = f.read()
    os.unlink(col_path)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("collection.anki2", col_bytes)
        zf.writestr("media", "{}")
    return out.getvalue()


def _strip_html(text: str) -> str:
    """去掉基本 HTML 标签，保留文本。"""
    import re
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&amp;", "&").replace("&quot;", '"')
    return text.strip()
