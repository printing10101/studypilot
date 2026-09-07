"""SQLite 持久化层：项目空间、文档、消息、测验、三层记忆、向量。"""
import json
import os
import sqlite3
import time
import uuid
from typing import Any

from .config import settings

os.makedirs(settings.data_dir, exist_ok=True)
os.makedirs(settings.upload_dir, exist_ok=True)

DB_PATH = os.path.join(settings.data_dir, settings.db_path)

SCHEMA = """
CREATE TABLE IF NOT EXISTS spaces(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT DEFAULT '',
  created_at REAL
);
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  path TEXT NOT NULL,
  status TEXT DEFAULT 'pending',   -- pending/ready/error
  chunks INTEGER DEFAULT 0,
  error TEXT DEFAULT '',
  created_at REAL
);
CREATE TABLE IF NOT EXISTS messages(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  mode TEXT NOT NULL,              -- ask/plan/craft
  expert TEXT DEFAULT '',
  role TEXT NOT NULL,              -- user/assistant
  content TEXT NOT NULL,
  citations TEXT DEFAULT '[]',
  created_at REAL
);
CREATE TABLE IF NOT EXISTS quiz_records(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  topic TEXT DEFAULT '',
  questions TEXT NOT NULL,         -- json
  answers TEXT DEFAULT '[]',       -- json [{qid, user_answer, verdict, analysis}]
  created_at REAL
);
CREATE TABLE IF NOT EXISTS memory(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  level INTEGER NOT NULL,          -- 1 镜像 / 2 摘要 / 3 长期综合
  kind TEXT DEFAULT '',            -- fact/weakness/mastery 等
  content TEXT NOT NULL,
  created_at REAL
);
CREATE TABLE IF NOT EXISTS vectors(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  chunk_index INTEGER,
  text TEXT NOT NULL,
  embedding BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vec_space ON vectors(space_id);
CREATE INDEX IF NOT EXISTS idx_msg_space ON messages(space_id);
"""

_conn: sqlite3.Connection | None = None


def get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> float:
    return time.time()


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


# ---------- 空间 ----------

def create_space(name: str, description: str = "") -> dict[str, Any]:
    c = get_conn()
    sid = new_id()
    c.execute("INSERT INTO spaces(id,name,description,created_at) VALUES(?,?,?,?)",
              (sid, name, description, now()))
    c.commit()
    return dict(get_conn().execute("SELECT * FROM spaces WHERE id=?", (sid,)).fetchone())


def list_spaces() -> list[dict[str, Any]]:
    return rows_to_dicts(get_conn().execute("SELECT * FROM spaces ORDER BY created_at DESC").fetchall())


def get_space(sid: str) -> dict[str, Any] | None:
    r = get_conn().execute("SELECT * FROM spaces WHERE id=?", (sid,)).fetchone()
    return dict(r) if r else None


def delete_space(sid: str) -> None:
    c = get_conn()
    for t in ("documents", "messages", "quiz_records", "memory", "vectors"):
        c.execute(f"DELETE FROM {t} WHERE space_id=?", (sid,))
    c.execute("DELETE FROM spaces WHERE id=?", (sid,))
    c.commit()


# ---------- 文档 ----------

def add_document(space_id: str, filename: str, path: str, doc_id: str = "") -> str:
    c = get_conn()
    did = doc_id or new_id()
    c.execute("INSERT INTO documents(id,space_id,filename,path,status,created_at) VALUES(?,?,?,?, 'pending',?)",
              (did, space_id, filename, path, now()))
    c.commit()
    return did


def update_document(did: str, **kw: Any) -> None:
    c = get_conn()
    sets = ",".join(f"{k}=?" for k in kw)
    c.execute(f"UPDATE documents SET {sets} WHERE id=?", (*kw.values(), did))
    c.commit()


def list_documents(space_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(get_conn().execute(
        "SELECT id,filename,status,chunks,error,created_at FROM documents WHERE space_id=? ORDER BY created_at DESC",
        (space_id,)).fetchall())


def get_document(did: str) -> dict[str, Any] | None:
    r = get_conn().execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
    return dict(r) if r else None


# ---------- 消息 ----------

def add_message(space_id: str, mode: str, role: str, content: str,
                expert: str = "", citations: list | None = None) -> str:
    c = get_conn()
    mid = new_id()
    c.execute("INSERT INTO messages(id,space_id,mode,expert,role,content,citations,created_at) VALUES(?,?,?,?,?,?,?,?)",
              (mid, space_id, mode, expert, role, content, json.dumps(citations or [], ensure_ascii=False), now()))
    c.commit()
    return mid


def list_messages(space_id: str, limit: int = 200) -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT * FROM messages WHERE space_id=? ORDER BY created_at DESC LIMIT ?", (space_id, limit)).fetchall()
    out = rows_to_dicts(rows)
    for m in out:
        m["citations"] = json.loads(m["citations"])
    out.reverse()
    return out


def recent_messages(space_id: str, n: int = 12) -> list[dict[str, Any]]:
    """L1 记忆素材：最近 n 轮消息。"""
    rows = get_conn().execute(
        "SELECT role,content,mode FROM messages WHERE space_id=? ORDER BY created_at DESC LIMIT ?", (space_id, n)).fetchall()
    return rows_to_dicts(rows)


# ---------- 测验 ----------

def save_quiz(space_id: str, topic: str, questions: list, answers: list | None = None) -> str:
    c = get_conn()
    qid = new_id()
    c.execute("INSERT INTO quiz_records(id,space_id,topic,questions,answers,created_at) VALUES(?,?,?,?,?,?)",
              (qid, space_id, topic, json.dumps(questions, ensure_ascii=False),
               json.dumps(answers or [], ensure_ascii=False), now()))
    c.commit()
    return qid


def update_quiz(qid: str, answers: list) -> None:
    get_conn().execute("UPDATE quiz_records SET answers=? WHERE id=?",
                       (json.dumps(answers, ensure_ascii=False), qid))
    get_conn().commit()


def list_quizzes(space_id: str) -> list[dict[str, Any]]:
    rows = rows_to_dicts(get_conn().execute(
        "SELECT * FROM quiz_records WHERE space_id=? ORDER BY created_at DESC", (space_id,)).fetchall())
    for q in rows:
        q["questions"] = json.loads(q["questions"])
        q["answers"] = json.loads(q["answers"])
    return rows


# ---------- 记忆 ----------

def add_memory(space_id: str, level: int, content: str, kind: str = "") -> str:
    c = get_conn()
    mid = new_id()
    c.execute("INSERT INTO memory(id,space_id,level,kind,content,created_at) VALUES(?,?,?,?,?,?)",
              (mid, space_id, level, kind, content, now()))
    c.commit()
    return mid


def list_memory(space_id: str, level: int | None = None) -> list[dict[str, Any]]:
    if level:
        rows = get_conn().execute("SELECT * FROM memory WHERE space_id=? AND level=? ORDER BY created_at",
                                  (space_id, level)).fetchall()
    else:
        rows = get_conn().execute("SELECT * FROM memory WHERE space_id=? ORDER BY level,created_at", (space_id,)).fetchall()
    return rows_to_dicts(rows)


def clear_memory(space_id: str, level: int) -> None:
    get_conn().execute("DELETE FROM memory WHERE space_id=? AND level=?", (space_id, level))
    get_conn().commit()


def latest_l2(space_id: str) -> str:
    rows = get_conn().execute(
        "SELECT content FROM memory WHERE space_id=? AND level=2 ORDER BY created_at DESC LIMIT 1", (space_id,)).fetchall()
    return rows[0]["content"] if rows else ""


# ---------- 向量 ----------

def insert_vectors(rows: list[tuple[str, str, int, str, list[float]]]) -> None:
    """(space_id, document_id, chunk_index, text, embedding)"""
    import struct
    c = get_conn()
    for sid, did, idx, text, emb in rows:
        blob = struct.pack(f"{len(emb)}f", *emb)
        c.execute("INSERT OR REPLACE INTO vectors(id,space_id,document_id,chunk_index,text,embedding) VALUES(?,?,?,?,?,?)",
                  (new_id(), sid, did, idx, text, blob))
    c.commit()


def search_vectors(space_id: str, query_emb: list[float], top_k: int = 6) -> list[dict[str, Any]]:
    import struct
    import numpy as np
    rows = get_conn().execute(
        "SELECT id,document_id,chunk_index,text,embedding FROM vectors WHERE space_id=?", (space_id,)).fetchall()
    if not rows:
        return []
    q = np.array(query_emb, dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-9)
    scored = []
    for r in rows:
        v = np.frombuffer(r["embedding"], dtype=np.float32)
        v = v / (np.linalg.norm(v) + 1e-9)
        scored.append((float(q @ v), r))
    scored.sort(key=lambda x: -x[0])
    return [{"id": r["id"], "document_id": r["document_id"], "chunk_index": r["chunk_index"],
             "text": r["text"], "score": s} for s, r in scored[:top_k]]


def doc_filename(document_id: str) -> str:
    r = get_conn().execute("SELECT filename FROM documents WHERE id=?", (document_id,)).fetchone()
    return r["filename"] if r else "unknown"
