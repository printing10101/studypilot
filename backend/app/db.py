"""SQLite 持久化层：项目空间、文档、消息、测验、三层记忆、向量。"""
import difflib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from typing import Any

from . import fsrs as _fsrs
from .config import settings

log = logging.getLogger("studypilot.db")

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
  content_hash TEXT DEFAULT '',    -- 上传文件 sha256，同空间判重用
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
CREATE TABLE IF NOT EXISTS books(
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  author TEXT DEFAULT '',
  subject TEXT DEFAULT '',
  publisher TEXT DEFAULT '',
  license TEXT DEFAULT '',
  note TEXT DEFAULT '',
  pdf_url TEXT DEFAULT '',         -- 官方直链（可自动获取）
  source_url TEXT DEFAULT '',      -- 官方页面外链
  status TEXT DEFAULT 'catalog',   -- catalog 仅书目 / external 官方可获取 / local 已有文件
  path TEXT DEFAULT '',
  error TEXT DEFAULT '',
  created_at REAL
);
CREATE TABLE IF NOT EXISTS book_documents(
  book_id TEXT NOT NULL,
  space_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  created_at REAL,
  PRIMARY KEY(book_id, space_id)
);
CREATE TABLE IF NOT EXISTS feedback(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  message_id TEXT DEFAULT '',      -- 关联的助手消息
  rating TEXT DEFAULT '',          -- helpful / unhelpful
  understood INTEGER DEFAULT -1,   -- 1 听懂了 / 0 没听懂 / -1 未表态
  confusion TEXT DEFAULT '',       -- 用户补充说明（哪里没懂）
  created_at REAL
);
CREATE TABLE IF NOT EXISTS mastery(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  point TEXT NOT NULL,             -- 知识点
  score REAL DEFAULT 0.5,          -- 0..1 掌握度
  attempts INTEGER DEFAULT 0,
  correct INTEGER DEFAULT 0,
  wrong INTEGER DEFAULT 0,
  box INTEGER DEFAULT 1,           -- 展示用盒位（1=刚忘/学习中 .. 5=长稳），调度由 FSRS 接管
  due_at REAL DEFAULT 0,           -- 下次应复习的时间戳（FSRS due）
  status TEXT DEFAULT 'learning',  -- weak / learning / mastered
  updated_at REAL,
  state INTEGER DEFAULT 0,         -- FSRS 状态 0=未评 1=学习中 2=复习中 3=重学
  step INTEGER,                    -- FSRS 学习/重学步进
  stability REAL DEFAULT 0,        -- FSRS 稳定性（天）
  difficulty REAL DEFAULT 0,       -- FSRS 难度 1..10
  last_review REAL DEFAULT 0,      -- 上次评分时间戳
  UNIQUE(space_id, point)
);
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS handbooks(
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  profile TEXT DEFAULT '[]',       -- json 用户档案
  space_id TEXT DEFAULT '',
  content TEXT NOT NULL,           -- markdown 手册正文
  created_at REAL
);
CREATE TABLE IF NOT EXISTS flashcards(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  front TEXT NOT NULL,             -- 卡面（问题/提示）
  back TEXT NOT NULL,              -- 答案
  point TEXT DEFAULT '',           -- 关联知识点
  box INTEGER DEFAULT 1,           -- 展示用盒位（1=刚忘/学习中 .. 5=长稳），调度由 FSRS 接管
  due_at REAL DEFAULT 0,           -- 下次应复习时间戳（FSRS due）
  created_at REAL,
  state INTEGER DEFAULT 0,         -- FSRS 状态 0=未评 1=学习中 2=复习中 3=重学
  step INTEGER,                    -- FSRS 学习/重学步进
  stability REAL DEFAULT 0,        -- FSRS 稳定性（天）
  difficulty REAL DEFAULT 0,       -- FSRS 难度 1..10
  last_review REAL DEFAULT 0,      -- 上次评分时间戳
  reps INTEGER DEFAULT 0,          -- 累计评分次数
  lapses INTEGER DEFAULT 0         -- 累计遗忘次数（评"忘了"）
);
CREATE INDEX IF NOT EXISTS idx_fc_space ON flashcards(space_id);
CREATE TABLE IF NOT EXISTS mastery_history(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  point TEXT NOT NULL,
  score REAL NOT NULL,
  verdict TEXT DEFAULT '',         -- correct/partial/wrong/confused/progress
  created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_mh_space ON mastery_history(space_id);
CREATE TABLE IF NOT EXISTS plan_tasks(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  phase TEXT DEFAULT '',           -- 阶段名（含时间范围）
  content TEXT NOT NULL,           -- 行动项
  accept TEXT DEFAULT '',          -- 验收标准
  points TEXT DEFAULT '[]',        -- 涉及知识点 json
  due_date TEXT DEFAULT '',        -- 截止日期 YYYY-MM-DD（今日学习页排期用）
  method TEXT DEFAULT '',          -- 证据导向学习方法名（检索/间隔/交错等）
  source_plan TEXT DEFAULT '',     -- 来源学涯计划 id（push 同步写入，幂等/回溯用）
  done INTEGER DEFAULT 0,
  done_at REAL DEFAULT 0,
  created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_pt_space ON plan_tasks(space_id);
CREATE TABLE IF NOT EXISTS student_profile(
  id INTEGER PRIMARY KEY CHECK (id=1),  -- 单用户档案，固定一行
  current_school TEXT DEFAULT '',
  major TEXT DEFAULT '',
  year TEXT DEFAULT '',
  rank_hint TEXT DEFAULT '',
  flags TEXT DEFAULT '[]',         -- 情况标签 json（重修/跨考…）
  goal_type TEXT DEFAULT '考研',
  target_school TEXT DEFAULT '',
  target_major TEXT DEFAULT '',
  timeline TEXT DEFAULT '',
  notes TEXT DEFAULT '',
  learner_personas TEXT DEFAULT '[]',  -- 学习者画像 id json（可多选，与行为推断合并）
  updated_at REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS concept_edges(
  space_id TEXT NOT NULL,
  from_point TEXT NOT NULL,        -- 前置知识点
  to_point TEXT NOT NULL,          -- 后继知识点（依赖前置）
  source TEXT DEFAULT 'llm',       -- llm=讲义抽取 / curriculum=内置课程图谱
  created_at REAL,
  UNIQUE(space_id, from_point, to_point)
);
CREATE INDEX IF NOT EXISTS idx_ce_space ON concept_edges(space_id);
CREATE TABLE IF NOT EXISTS course_schedule(
  id TEXT PRIMARY KEY,
  term TEXT DEFAULT '',            -- 学期（如 2025-2026-1）
  day INTEGER DEFAULT 1,           -- 1..7 = 周一..周日
  period TEXT DEFAULT '',          -- 节次（如 1-2）
  course TEXT NOT NULL,            -- 课程名
  teacher TEXT DEFAULT '',
  room TEXT DEFAULT '',
  weeks TEXT DEFAULT '',           -- 周次说明（1-16周/单周…）
  kind TEXT DEFAULT '',            -- 课程性质（必修/选修/实验）
  created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_cs_term ON course_schedule(term);
CREATE TABLE IF NOT EXISTS career_plans(
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  school TEXT DEFAULT '',
  major TEXT DEFAULT '',
  goal_type TEXT DEFAULT '',       -- 保研/考研/就业/竞赛/出国/期末
  target TEXT DEFAULT '',          -- 目标院校专业/岗位
  term TEXT DEFAULT '',            -- 当前学期
  horizon TEXT DEFAULT '',         -- 规划跨度（本学期/本学年/至毕业）
  summary TEXT DEFAULT '',         -- 总方针
  tasks TEXT NOT NULL,             -- json [{id,phase,content,accept,course,done,done_at}]
  markdown TEXT DEFAULT '',        -- 渲染后的计划全文
  created_at REAL
);
CREATE TABLE IF NOT EXISTS syllabus_custom(
  school TEXT NOT NULL,            -- 学校名（与 schools.json 对齐）
  major TEXT NOT NULL,             -- 专业名
  data TEXT NOT NULL,              -- json 结构化培养方案（与 programs 模板同构）
  source TEXT DEFAULT '',          -- 来源说明（导入文件名等）
  updated_at REAL,
  PRIMARY KEY(school, major)
);
CREATE TABLE IF NOT EXISTS taken_courses(
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,              -- 课程名
  credit REAL DEFAULT 0,           -- 学分（0=未知）
  grade TEXT DEFAULT '',           -- 原始成绩（92 / 优秀 / A-…）
  gpa REAL DEFAULT -1,             -- 换算绩点（4.0 制，-1=无法换算）
  semester TEXT DEFAULT '',        -- 修读学期（自由文本）
  status TEXT DEFAULT 'done',      -- done 已修 / taking 修读中
  created_at REAL
);
CREATE TABLE IF NOT EXISTS question_bank(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  knowledge_point TEXT DEFAULT '',
  question TEXT NOT NULL,          -- json 题目全文
  qtype TEXT DEFAULT '',           -- 判断/选择/简答
  difficulty INTEGER DEFAULT 1,    -- 1=基础 2=应用 3=陷阱
  times_used INTEGER DEFAULT 0,
  times_correct INTEGER DEFAULT 0,
  created_at REAL,
  last_used_at REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_qb_space ON question_bank(space_id);
CREATE INDEX IF NOT EXISTS idx_qb_point ON question_bank(space_id, knowledge_point);
CREATE TABLE IF NOT EXISTS campus_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,            -- 信息源 id（如 mech_notice）
  title TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,        -- 绝对链接，按 URL 判重
  published TEXT DEFAULT '',       -- 页面标注的发布日期 YYYY-MM-DD
  fetched_at REAL
);
CREATE INDEX IF NOT EXISTS idx_campus_source ON campus_items(source, published);
CREATE TABLE IF NOT EXISTS visuals(
  id TEXT PRIMARY KEY,
  space_id TEXT NOT NULL,
  topic TEXT NOT NULL,             -- 可视化的知识点/主题
  title TEXT DEFAULT '',           -- 展示标题
  summary TEXT DEFAULT '',         -- 一句话直觉解释
  spec TEXT NOT NULL,              -- json 结构化可视化规格（steps/analogy/formula）
  created_at REAL
);
CREATE INDEX IF NOT EXISTS idx_vis_space ON visuals(space_id);
"""

_local = threading.local()  # 线程本地连接：FastAPI 线程池并发共享单连接会触发 sqlite3 InterfaceError
_migrate_lock = threading.Lock()
_migrated = False  # SCHEMA + 列迁移进程内只跑一次：并发首连各自 ALTER 会 duplicate column


def get_conn() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # 多线程并发写友好（读写不互斥）
        global _migrated
        if not _migrated:
            with _migrate_lock:
                if not _migrated:
                    _run_migrations(conn)
                    _migrated = True
        _local.conn = conn
    return conn


def _run_migrations(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # 轻量迁移：老库没有的列在此补齐
    cols = {r[1] for r in conn.execute("PRAGMA table_info(plan_tasks)")}
    if "due_date" not in cols:
        conn.execute("ALTER TABLE plan_tasks ADD COLUMN due_date TEXT DEFAULT ''")
    if "source_plan" not in cols:
        conn.execute("ALTER TABLE plan_tasks ADD COLUMN source_plan TEXT DEFAULT ''")
    if "method" not in cols:
        conn.execute("ALTER TABLE plan_tasks ADD COLUMN method TEXT DEFAULT ''")
    pcols = {r[1] for r in conn.execute("PRAGMA table_info(student_profile)")}
    if "learner_personas" not in pcols:
        conn.execute("ALTER TABLE student_profile ADD COLUMN learner_personas TEXT DEFAULT '[]'")
    dcols = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
    if "content_hash" not in dcols:
        conn.execute("ALTER TABLE documents ADD COLUMN content_hash TEXT DEFAULT ''")
    # FSRS 调度列（老 Leitner 数据零迁移：box 折算初始稳定性的逻辑在 app.fsrs 里）
    mcols = {r[1] for r in conn.execute("PRAGMA table_info(mastery)")}
    if "state" not in mcols:
        conn.execute("ALTER TABLE mastery ADD COLUMN state INTEGER DEFAULT 0")
    if "step" not in mcols:
        conn.execute("ALTER TABLE mastery ADD COLUMN step INTEGER")
    if "stability" not in mcols:
        conn.execute("ALTER TABLE mastery ADD COLUMN stability REAL DEFAULT 0")
    if "difficulty" not in mcols:
        conn.execute("ALTER TABLE mastery ADD COLUMN difficulty REAL DEFAULT 0")
    if "last_review" not in mcols:
        conn.execute("ALTER TABLE mastery ADD COLUMN last_review REAL DEFAULT 0")
    fcols = {r[1] for r in conn.execute("PRAGMA table_info(flashcards)")}
    if "state" not in fcols:
        conn.execute("ALTER TABLE flashcards ADD COLUMN state INTEGER DEFAULT 0")
    if "step" not in fcols:
        conn.execute("ALTER TABLE flashcards ADD COLUMN step INTEGER")
    if "stability" not in fcols:
        conn.execute("ALTER TABLE flashcards ADD COLUMN stability REAL DEFAULT 0")
    if "difficulty" not in fcols:
        conn.execute("ALTER TABLE flashcards ADD COLUMN difficulty REAL DEFAULT 0")
    if "last_review" not in fcols:
        conn.execute("ALTER TABLE flashcards ADD COLUMN last_review REAL DEFAULT 0")
    if "reps" not in fcols:
        conn.execute("ALTER TABLE flashcards ADD COLUMN reps INTEGER DEFAULT 0")
    if "lapses" not in fcols:
        conn.execute("ALTER TABLE flashcards ADD COLUMN lapses INTEGER DEFAULT 0")
    # 一次性清洗：strptime 曾放过非补零日期（"2026-9-1"），字符串比较会失真，这里统一补零
    for r in conn.execute("SELECT id, due_date FROM plan_tasks WHERE due_date != ''").fetchall():
        try:
            conn.execute("UPDATE plan_tasks SET due_date=? WHERE id=?",
                         (time.strftime("%Y-%m-%d", time.strptime(r["due_date"], "%Y-%m-%d")), r["id"]))
        except ValueError:
            pass  # 本就非法的值留给校验层拒绝
    conn.commit()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> float:
    return time.time()


def like_escape(s: str) -> str:
    """LIKE 通配符转义（配合 `LIKE ? ESCAPE '\\'` 使用），防止用户输入里的 % _ 误匹配。"""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _safe_json(text: Any, default: Any) -> Any:
    """历史脏数据容错：单行 JSON 损坏不应让整个列表接口 500。"""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return default


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
    # 先收集该空间文档的磁盘路径（须在上传目录内，防误删）
    upload_root = os.path.realpath(settings.upload_dir)
    # 挂载教材的文档与书库共享同一磁盘文件（与 delete_document 的 remove_file=False 口径一致），
    # 删空间时只删库记录、跳过文件，否则书库条目变「文件丢失」、其他空间无法再挂载
    book_doc_ids = {r["document_id"] for r in c.execute("SELECT document_id FROM book_documents").fetchall()}
    paths: list[str] = []
    for r in c.execute("SELECT id, path FROM documents WHERE space_id=?", (sid,)).fetchall():
        p = r["path"]
        if p and r["id"] not in book_doc_ids:
            try:
                if os.path.realpath(p).startswith(upload_root + os.sep):
                    paths.append(p)
            except OSError:
                log.debug("空间 %s 文件路径解析失败，跳过该文件（%s）", sid, p, exc_info=True)
    for t in ("documents", "messages", "quiz_records", "memory", "vectors",
              "feedback", "mastery", "mastery_history", "flashcards",
              "plan_tasks", "concept_edges", "book_documents", "question_bank"):
        c.execute(f"DELETE FROM {t} WHERE space_id=?", (sid,))
    # method_events/quiz_predictions 由 study_metrics 首次使用时才建表，可能尚不存在
    for t in ("method_events", "quiz_predictions"):
        try:
            c.execute(f"DELETE FROM {t} WHERE space_id=?", (sid,))
        except sqlite3.OperationalError:
            pass  # 表未创建，自然也没有该空间的行
    c.execute("DELETE FROM handbooks WHERE space_id=?", (sid,))
    # meta 里挂着该空间的 KV（分析位点 analyzed_*、个性化 BKT 参数 bkt_params:*），一并清掉
    try:
        c.execute("DELETE FROM meta WHERE key LIKE ? ESCAPE '\\'",
                  (f"%{like_escape(sid)}%",))
    except sqlite3.OperationalError:
        pass
    c.execute("DELETE FROM spaces WHERE id=?", (sid,))
    c.commit()
    # 提交成功后再删磁盘文件：中途失败时记录还在、文件也还在，可重试
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass  # 文件可能已被移动/删除，不阻塞空间清理


# ---------- 文档 ----------

def add_document(space_id: str, filename: str, path: str, doc_id: str = "",
                 content_hash: str = "") -> str:
    c = get_conn()
    did = doc_id or new_id()
    c.execute("INSERT INTO documents(id,space_id,filename,path,status,content_hash,created_at) "
              "VALUES(?,?,?,?,'pending',?,?)",
              (did, space_id, filename, path, content_hash, now()))
    c.commit()
    return did


def find_doc_by_hash(space_id: str, content_hash: str) -> dict[str, Any] | None:
    """同空间内按内容哈希找已就绪文档：重复上传同一文件时向量化结果会全量翻倍，
    检索里重复片段挤占上下文预算、引用列表也重复，上传入口据此判重。"""
    if not content_hash:
        return None
    r = get_conn().execute(
        "SELECT id, filename FROM documents WHERE space_id=? AND content_hash=? AND status='ready' "
        "ORDER BY created_at DESC LIMIT 1", (space_id, content_hash)).fetchone()
    return dict(r) if r else None


def reset_stale_pending() -> int:
    """启动时清扫：进程中途被杀（如直接关窗）会让文档永远停在 pending「处理中」转圈，
    没有任何自愈路径；这里统一置为 error 并提示可重新索引。"""
    c = get_conn()
    rows = c.execute("SELECT id FROM documents WHERE status='pending'").fetchall()
    if not rows:
        return 0
    c.execute("UPDATE documents SET status='error', error='上次处理被中断（应用退出），请点「重新索引」重试' "
              "WHERE status='pending'")
    c.commit()
    return len(rows)


def backup_database(keep: int = 7) -> str | None:
    """滚动整库备份到 data/backups/（SQLite 在线 backup API，不阻塞写入）。
    库损坏或误删空间后掌握度历史/记忆档案才有一线恢复机会。"""
    try:
        backup_root = os.path.realpath(os.path.join(os.path.realpath(settings.data_dir), "backups"))
        os.makedirs(backup_root, exist_ok=True)
        # 文件名仅由时间戳构成、不含任何外部输入；仍做目录边界校验防呆
        dest_path = os.path.realpath(os.path.join(
            backup_root, f"studypilot-{time.strftime('%Y%m%d-%H%M%S')}.db"))
        if os.path.commonpath([dest_path, backup_root]) != backup_root:
            return None
        src = get_conn()
        dest = sqlite3.connect(dest_path)
        with dest:
            src.backup(dest)
        dest.close()
        # 只保留最近 keep 份
        olds = sorted(
            p for p in os.listdir(backup_root)
            if p.startswith("studypilot-") and p.endswith(".db")
            and os.path.commonpath([os.path.realpath(os.path.join(backup_root, p)), backup_root]) == backup_root)
        for p in olds[:-keep] if len(olds) > keep else []:
            try:
                os.remove(os.path.join(backup_root, p))
            except OSError:
                log.debug("旧备份清理失败（%s）", p, exc_info=True)
        return dest_path
    except Exception:
        # 备份失败不阻塞启动，但必须留痕：备份是数据安全的最后防线
        log.warning("启动滚动备份失败（不阻塞启动）", exc_info=True)
        return None


_DOC_UPDATABLE_COLS = {"status", "error", "chunks", "filename", "path"}  # 防御性白名单：SET 列名不拼接任意输入


def update_document(did: str, **kw: Any) -> None:
    bad = set(kw) - _DOC_UPDATABLE_COLS
    if bad:
        raise ValueError(f"documents 不允许更新的列: {bad}")
    c = get_conn()
    sets = ",".join(f"{k}=?" for k in kw)
    c.execute(f"UPDATE documents SET {sets} WHERE id=?", (*kw.values(), did))
    c.commit()


def list_documents(space_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(get_conn().execute(
        "SELECT id,filename,status,chunks,error,created_at FROM documents WHERE space_id=? ORDER BY created_at DESC",
        (space_id,)).fetchall())


def list_documents_with_review(space_id: str) -> list[dict[str, Any]]:
    """带 FSRS 复习调度列的文档列表（note_review 到期计算专用；
    普通 list_documents 的窄列 SELECT 不含 review_*，会让到期判断恒为「从未复习」）。"""
    return rows_to_dicts(get_conn().execute(
        "SELECT id,filename,status,created_at,review_state,review_stability,review_reps,review_lapses,review_due_at "
        "FROM documents WHERE space_id=? AND status='ready' ORDER BY created_at DESC",
        (space_id,)).fetchall())


def get_document(did: str) -> dict[str, Any] | None:
    r = get_conn().execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
    return dict(r) if r else None


def clear_vectors(did: str) -> None:
    """清空文档已有向量（重新索引前调用，避免新旧 chunk 混杂）。"""
    c = get_conn()
    c.execute("DELETE FROM vectors WHERE document_id=?", (did,))
    c.commit()


def delete_document(did: str, remove_file: bool = True) -> None:
    """删除单个文档：向量、教材挂载映射一并清理；磁盘文件默认删除
    （挂载教材的文档与书库文件同路径，需 remove_file=False 避免误删书库文件）。"""
    c = get_conn()
    r = c.execute("SELECT path FROM documents WHERE id=?", (did,)).fetchone()
    if r and r["path"] and remove_file:
        upload_root = os.path.realpath(settings.upload_dir)
        try:
            if os.path.realpath(r["path"]).startswith(upload_root + os.sep):
                os.remove(r["path"])
        except OSError:
            pass  # 文件可能已被移动/删除，不阻塞记录清理
    c.execute("DELETE FROM vectors WHERE document_id=?", (did,))
    c.execute("DELETE FROM book_documents WHERE document_id=?", (did,))
    c.execute("DELETE FROM documents WHERE id=?", (did,))
    c.commit()


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
        m["citations"] = _safe_json(m["citations"], [])
    out.reverse()
    return out


def list_messages_paged(space_id: str, limit: int = 50, before_ts: float | None = None):
    """分页取最近消息（时间正序）。before_ts 为上一页最早一条的时间戳；has_more 提示是否还有更早消息。"""
    sql = "SELECT * FROM messages WHERE space_id=?"
    args: list = [space_id]
    if before_ts is not None:
        sql += " AND created_at < ?"
        args.append(before_ts)
    sql += " ORDER BY created_at DESC LIMIT ?"
    args.append(limit + 1)
    rows = get_conn().execute(sql, args).fetchall()
    has_more = len(rows) > limit
    out = rows_to_dicts(rows[:limit])
    for m in out:
        m["citations"] = _safe_json(m["citations"], [])
    out.reverse()
    return out, has_more


def recent_messages(space_id: str, n: int = 12) -> list[dict[str, Any]]:
    """L1 记忆素材：最近 n 轮消息（按时间正序返回，保证摘要模型看到的是正常时间线）。"""
    rows = get_conn().execute(
        "SELECT role,content,mode FROM messages WHERE space_id=? ORDER BY created_at DESC LIMIT ?", (space_id, n)).fetchall()
    out = rows_to_dicts(rows)
    out.reverse()
    return out


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


def set_quiz_topic(qid: str, topic: str) -> None:
    get_conn().execute("UPDATE quiz_records SET topic=? WHERE id=?", (topic, qid))
    get_conn().commit()


def list_quizzes(space_id: str) -> list[dict[str, Any]]:
    rows = rows_to_dicts(get_conn().execute(
        "SELECT * FROM quiz_records WHERE space_id=? ORDER BY created_at DESC", (space_id,)).fetchall())
    for q in rows:
        q["questions"] = _safe_json(q["questions"], [])
        q["answers"] = _safe_json(q["answers"], [])
    return rows


def recent_quizzes(space_id: str, n: int = 5) -> list[dict[str, Any]]:
    """最近 n 份测验（新→旧，含 answers）。SQL LIMIT 取行：
    list_quizzes 会解析全空间每份卷的 questions/answers JSON，只为取最近几份时开销线性膨胀。"""
    rows = rows_to_dicts(get_conn().execute(
        "SELECT * FROM quiz_records WHERE space_id=? ORDER BY created_at DESC LIMIT ?",
        (space_id, max(1, n))).fetchall())
    for q in rows:
        q["questions"] = _safe_json(q["questions"], [])
        q["answers"] = _safe_json(q["answers"], [])
    return rows


def count_quizzes(space_id: str) -> int:
    return get_conn().execute(
        "SELECT COUNT(*) AS n FROM quiz_records WHERE space_id=?", (space_id,)).fetchone()["n"]


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
    """(space_id, document_id, chunk_index, text, embedding)。嵌入写入前已 L2 归一化。"""
    import struct
    c = get_conn()
    c.executemany(
        "INSERT OR REPLACE INTO vectors(id,space_id,document_id,chunk_index,text,embedding) VALUES(?,?,?,?,?,?)",
        [(new_id(), sid, did, idx, text, struct.pack(f"{len(emb)}f", *emb))
         for sid, did, idx, text, emb in rows])
    c.commit()


def replace_vectors(document_id: str, rows: list[tuple[str, str, int, str, list[float]]]) -> None:
    """原子换版重索引：单事务内「删旧向量 + 写新向量」一起提交（DeepTutor 版本化思路的库内适配）。

    此前 reindex 是「先 clear_vectors 再逐条 INSERT」，中途失败会留下
    「旧索引已删、新索引未写」的空窗——原本能检索的文档反而彻底不可检索。
    换版语义：新向量全部构建成功后才落库替换，失败时旧索引原样保留。"""
    import struct
    c = get_conn()
    try:
        c.execute("DELETE FROM vectors WHERE document_id=?", (document_id,))
        c.executemany(
            "INSERT OR REPLACE INTO vectors(id,space_id,document_id,chunk_index,text,embedding) VALUES(?,?,?,?,?,?)",
            [(new_id(), sid, did, idx, text, struct.pack(f"{len(emb)}f", *emb))
             for sid, did, idx, text, emb in rows])
        c.commit()
    except Exception:
        c.rollback()
        raise


def search_vectors(space_id: str, query_emb: list[float], top_k: int = 6) -> list[dict[str, Any]]:
    import numpy as np
    rows = get_conn().execute(
        "SELECT id,document_id,chunk_index,text,embedding FROM vectors WHERE space_id=?", (space_id,)).fetchall()
    if not rows:
        return []
    # 库内嵌入写入时已归一化，点积即余弦相似度；整块矩阵乘替代逐行 Python 循环
    q = np.asarray(query_emb, dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-9)
    vecs = [np.frombuffer(r["embedding"], dtype=np.float32) for r in rows]
    # 过滤维度不一致的旧向量（更换嵌入模型后可能出现），避免整体检索崩溃
    rows = [r for r, v in zip(rows, vecs, strict=True) if v.shape[0] == q.shape[0]]
    vecs = [v for v in vecs if v.shape[0] == q.shape[0]]
    if not rows:
        return []
    scores = np.stack(vecs) @ q
    top = np.argsort(-scores)[:top_k]
    return [{"id": rows[i]["id"], "document_id": rows[i]["document_id"],
             "chunk_index": rows[i]["chunk_index"], "text": rows[i]["text"],
             "score": float(scores[i])} for i in top]


def space_chunks(space_id: str) -> list[dict[str, Any]]:
    """全量 chunk 行（含嵌入与原文）：混合检索一次取数，向量/BM25 双通道共用。"""
    rows = get_conn().execute(
        "SELECT id,document_id,chunk_index,text,embedding FROM vectors WHERE space_id=?",
        (space_id,)).fetchall()
    return rows_to_dicts(rows)


def doc_filename(document_id: str) -> str:
    r = get_conn().execute("SELECT filename FROM documents WHERE id=?", (document_id,)).fetchone()
    return r["filename"] if r else "unknown"


# ---------- 概念可视化 ----------

def save_visual(space_id: str, topic: str, title: str, summary: str, spec: dict) -> str:
    c = get_conn()
    vid = new_id()
    c.execute("INSERT INTO visuals(id,space_id,topic,title,summary,spec,created_at) VALUES(?,?,?,?,?,?,?)",
              (vid, space_id, topic, title, summary,
               json.dumps(spec, ensure_ascii=False), now()))
    c.commit()
    return vid


def list_visuals(space_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """可视化存档列表（不含 spec 大字段，列表页只展示标题/摘要）。"""
    rows = get_conn().execute(
        "SELECT id,topic,title,summary,created_at FROM visuals WHERE space_id=? ORDER BY created_at DESC LIMIT ?",
        (space_id, limit)).fetchall()
    return rows_to_dicts(rows)


def get_visual(vid: str) -> dict[str, Any] | None:
    r = get_conn().execute("SELECT * FROM visuals WHERE id=?", (vid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["spec"] = _safe_json(d.get("spec"), {})
    return d


def delete_visual(vid: str) -> None:
    c = get_conn()
    c.execute("DELETE FROM visuals WHERE id=?", (vid,))
    c.commit()


# ---------- 教材书库 ----------

def add_book(title: str, author: str = "", subject: str = "", publisher: str = "",
             license: str = "", note: str = "", pdf_url: str = "", source_url: str = "",
             status: str = "catalog", path: str = "", error: str = "") -> str:
    c = get_conn()
    bid = new_id()
    c.execute("INSERT INTO books(id,title,author,subject,publisher,license,note,"
              "pdf_url,source_url,status,path,error,created_at) "
              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (bid, title, author, subject, publisher, license, note,
               pdf_url, source_url, status, path, error, now()))
    c.commit()
    return bid


def list_books(query: str = "", subject: str = "") -> list[dict[str, Any]]:
    like = f"%{like_escape(query)}%" if query else ""
    if query and subject:
        rows = get_conn().execute(
            "SELECT * FROM books WHERE subject=? AND (title LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\' OR note LIKE ? ESCAPE '\\')"
            " ORDER BY subject,created_at", (subject, like, like, like)).fetchall()
    elif query:
        rows = get_conn().execute(
            "SELECT * FROM books WHERE title LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\' OR note LIKE ? ESCAPE '\\'"
            " ORDER BY subject,created_at", (like, like, like)).fetchall()
    elif subject:
        rows = get_conn().execute(
            "SELECT * FROM books WHERE subject=? ORDER BY subject,created_at", (subject,)).fetchall()
    else:
        rows = get_conn().execute("SELECT * FROM books ORDER BY subject,created_at").fetchall()
    return rows_to_dicts(rows)


def get_book(bid: str) -> dict[str, Any] | None:
    r = get_conn().execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
    return dict(r) if r else None


def find_book_by_title(title: str) -> dict[str, Any] | None:
    r = get_conn().execute("SELECT * FROM books WHERE title=?", (title,)).fetchone()
    return dict(r) if r else None


def find_book_by_url(url: str) -> dict[str, Any] | None:
    r = get_conn().execute("SELECT * FROM books WHERE source_url=? AND source_url!=''", (url,)).fetchone()
    return dict(r) if r else None


def update_book_file(bid: str, status: str, path: str = "", error: str = "") -> None:
    c = get_conn()
    c.execute("UPDATE books SET status=?, path=?, error=? WHERE id=?", (status, path, error, bid))
    c.commit()


def delete_book(bid: str) -> None:
    """删除书目：所有空间里的挂载文档（含向量）与磁盘文件一并清理，避免检索残留。"""
    c = get_conn()
    upload_root = os.path.realpath(settings.upload_dir)
    for r in c.execute(
            "SELECT d.id AS did, d.path AS path FROM book_documents bd "
            "JOIN documents d ON d.id=bd.document_id WHERE bd.book_id=?", (bid,)).fetchall():
        c.execute("DELETE FROM vectors WHERE document_id=?", (r["did"],))
        c.execute("DELETE FROM documents WHERE id=?", (r["did"],))
        if r["path"]:
            try:
                if os.path.realpath(r["path"]).startswith(upload_root + os.sep):
                    os.remove(r["path"])
            except OSError:
                pass  # 文件可能已被移动/删除，不阻塞书目删除
    c.execute("DELETE FROM book_documents WHERE book_id=?", (bid,))
    c.execute("DELETE FROM books WHERE id=?", (bid,))
    c.commit()


def list_subjects() -> list[str]:
    rows = get_conn().execute("SELECT DISTINCT subject FROM books WHERE subject!='' ORDER BY subject").fetchall()
    return [r["subject"] for r in rows]


def get_book_document(bid: str, sid: str) -> str:
    r = get_conn().execute(
        "SELECT document_id FROM book_documents WHERE book_id=? AND space_id=?", (bid, sid)).fetchone()
    return r["document_id"] if r else ""


def document_is_book(did: str) -> bool:
    """该文档是否为教材书库挂载（文件与书库共享，删文档时不可删磁盘文件）。"""
    c = get_conn()
    return c.execute("SELECT 1 FROM book_documents WHERE document_id=?", (did,)).fetchone() is not None


def add_book_document(bid: str, sid: str, did: str) -> None:
    c = get_conn()
    c.execute("INSERT OR REPLACE INTO book_documents(book_id,space_id,document_id,created_at) VALUES(?,?,?,?)",
              (bid, sid, did, now()))
    c.commit()


def list_book_spaces(bid: str) -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT s.id, s.name FROM book_documents bd JOIN spaces s ON s.id=bd.space_id WHERE bd.book_id=?",
        (bid,)).fetchall()
    return rows_to_dicts(rows)


# ---------- 用户反馈 ----------

def add_feedback(space_id: str, message_id: str, rating: str,
                 understood: int, confusion: str) -> str:
    c = get_conn()
    fid = new_id()
    c.execute("INSERT INTO feedback(id,space_id,message_id,rating,understood,confusion,created_at) "
              "VALUES(?,?,?,?,?,?,?)",
              (fid, space_id, message_id, rating, understood, confusion, now()))
    c.commit()
    return fid


def list_feedback(space_id: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT * FROM feedback WHERE space_id=? ORDER BY created_at DESC LIMIT ?",
        (space_id, limit)).fetchall()
    return rows_to_dicts(rows)


def get_message(mid: str) -> dict[str, Any] | None:
    r = get_conn().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["citations"] = json.loads(d.get("citations") or "[]")
    except ValueError:
        d["citations"] = []
    return d


def previous_user_message(space_id: str, before_id: str) -> str:
    """直查某条消息之前最近的一条用户提问（免加载整段对话）。"""
    msg = get_message(before_id) if before_id else None
    if not msg:
        return ""
    r = get_conn().execute(
        "SELECT content FROM messages WHERE space_id=? AND role='user' AND id!=? "
        "AND created_at<=? ORDER BY created_at DESC LIMIT 1",
        (space_id, before_id, msg["created_at"])).fetchone()
    return r["content"] if r else ""


# ---------- 知识点掌握度（BKT 知识追踪 + FSRS 间隔复习 + 缺陷依赖图） ----------

# 旧 Leitner 盒间隔（盒1=30分钟 … 盒5=14天）：仅作老数据折算与留存率回退公式，
# 复习调度已由 FSRS 接管（app.fsrs，目标留存率 0.9，按个人评分历史自适应间隔）
_BOX_DELAYS = {1: 1800.0, 2: 86400.0, 3: 259200.0, 4: 604800.0, 5: 1209600.0}

# ---- 贝叶斯知识追踪（BKT）参数 ----
# prior: 初始先验 P(已掌握)；learn: 每次练习后的学习转移概率 P(T)
# slip: 已掌握但做错的概率 P(S)；guess: 未掌握但蒙对的概率 P(G)
_BKT_PRIOR = 0.35
_BKT_LEARN = 0.13
_BKT_SLIP = 0.10
_DEFAULT_GUESS = 0.15

# 各类证据对"掌握"的支持强度（软观测，按强度混合两个方向的贝叶斯后验）
_EVIDENCE_STRENGTH = {"correct": 1.0, "progress": 0.6, "partial": 0.5, "confused": 0.15, "wrong": 0.0}


def _bkt_posterior(p: float, obs_correct: bool, guess: float) -> float:
    """单次观测的贝叶斯后验 P(K|obs)。"""
    if obs_correct:
        lik_k, lik_notk = 1.0 - _BKT_SLIP, guess
    else:
        lik_k, lik_notk = _BKT_SLIP, 1.0 - guess
    denom = lik_k * p + lik_notk * (1 - p)
    return (lik_k * p) / denom if denom > 0 else p


def _bkt_update(p: float, evidence: float, guess: float) -> float:
    """软观测 BKT：按证据强度混合对/错两个后验，再做学习转移。"""
    p1 = _bkt_posterior(p, True, guess)
    p0 = _bkt_posterior(p, False, guess)
    p_obs = evidence * p1 + (1 - evidence) * p0
    return min(0.98, p_obs + (1 - p_obs) * _BKT_LEARN)


def estimate_retention(p_known: float, box: int, updated_at: float, at: float | None = None,
                       stability: float = 0.0, last_review: float = 0.0) -> float:
    """估算"此刻还记得多少"：优先 FSRS 幂律遗忘曲线（有稳定性时）；
    无 FSRS 状态的老数据退回 Ebbinghaus 半衰期公式 R = 0.5^(Δt/半衰期)。"""
    r = _fsrs.retrievability(stability, last_review, at)
    if r >= 0:
        return round(r, 4)
    at = at if at is not None else time.time()
    delay_h = _BOX_DELAYS.get(box, 1800.0) / 3600.0
    half_life_h = delay_h * 1.2 + 4.0
    dt_h = max(0.0, (at - updated_at) / 3600.0)
    return round(0.5 ** (dt_h / half_life_h), 4)


def _mastery_status(score: float) -> str:
    if score < 0.35:
        return "weak"
    if score < 0.75:
        return "learning"
    return "mastered"


def _find_mastery(space_id: str, point: str) -> dict[str, Any] | None:
    """精确匹配，再做包含关系匹配（LLM 对同一知识点的表述会有差异，
    如「牛顿第二定律」vs「牛顿第二运动定律」）。不用纯字符相似度：
    ratio≥0.5 会把「光的干涉/光的衍射」这类相邻概念误并成同一个点。"""
    r = get_conn().execute("SELECT * FROM mastery WHERE space_id=? AND point=?",
                           (space_id, point)).fetchone()
    if r:
        return dict(r)
    if len(point) < 4:
        return None  # 短名没有可靠的模糊匹配依据，宁可不并
    rows = rows_to_dicts(get_conn().execute(
        "SELECT * FROM mastery WHERE space_id=?", (space_id,)).fetchall())
    for row in rows:
        a, b = row["point"], point
        if len(a) >= 4 and (a in b or b in a):
            return row
    return None


def adjust_mastery(space_id: str, point: str, verdict: str, guess: float | None = None,
                   override_score: float | None = None) -> dict[str, Any] | None:
    """按证据更新知识点掌握度（BKT）并调度 FSRS 复习。

    verdict: correct / partial / wrong / confused / progress
    guess: 该次观测的蒙对概率（未给则按默认；选择/判断题应由调用方传更高值）
    override_score: 直接指定新的掌握度（个性化 BKT 拟合参数算出的值），跳过内部 BKT 更新
    """
    point = point.strip()[:80]
    if not point:
        return None
    evidence = _EVIDENCE_STRENGTH.get(verdict)
    if evidence is None:
        return None
    row = _find_mastery(space_id, point)
    if row:
        score, attempts, correct, wrong, box = (row["score"], row["attempts"],
                                                row["correct"], row["wrong"], row["box"])
        point = row["point"]
    else:
        score, attempts, correct, wrong, box = _BKT_PRIOR, 0, 0, 0, 1
    if override_score is not None:
        score = max(0.0, min(1.0, override_score))
    else:
        score = _bkt_update(score, evidence, _DEFAULT_GUESS if guess is None else min(max(guess, 0.01), 0.6))
    attempts += 1
    if verdict == "correct":
        correct += 1
    elif verdict == "wrong":
        wrong += 1
    # 复习排期走 FSRS（正确→良好 / 部分·进步→困难 / 混淆·错误→忘了），box 仅作展示同步
    sched_row = dict(row) if row else {
        "id": f"{space_id}:{point}", "box": 1, "due_at": now(), "state": 0, "step": None,
        "stability": 0.0, "difficulty": 0.0, "last_review": 0.0, "attempts": 0, "updated_at": 0,
    }
    sched_row["attempts"] = attempts - 1  # 折算旧数据时看评分前的次数
    sched = _fsrs.review(sched_row, _fsrs.VERDICT_RATING[verdict])
    box, due = sched["box"], sched["due_at"]
    c = get_conn()
    c.execute("INSERT INTO mastery(id,space_id,point,score,attempts,correct,wrong,box,due_at,status,"
              "updated_at,state,step,stability,difficulty,last_review) "
              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
              "ON CONFLICT(space_id,point) DO UPDATE SET score=excluded.score, attempts=excluded.attempts, "
              "correct=excluded.correct, wrong=excluded.wrong, box=excluded.box, due_at=excluded.due_at, "
              "status=excluded.status, updated_at=excluded.updated_at, state=excluded.state, "
              "step=excluded.step, stability=excluded.stability, difficulty=excluded.difficulty, "
              "last_review=excluded.last_review",
              (new_id(), space_id, point, round(score, 4), attempts, correct, wrong,
               box, due, _mastery_status(score), now(),
               sched["state"], sched["step"], sched["stability"], sched["difficulty"], sched["last_review"]))
    add_mastery_history(space_id, point, round(score, 4), verdict)
    c.commit()
    return get_mastery_point(space_id, point)


def add_mastery_history(space_id: str, point: str, score: float, verdict: str = "") -> None:
    c = get_conn()
    c.execute("INSERT INTO mastery_history(id,space_id,point,score,verdict,created_at) VALUES(?,?,?,?,?,?)",
              (new_id(), space_id, point, score, verdict, now()))
    c.commit()


def list_mastery_history(space_id: str, limit: int = 500) -> list[dict[str, Any]]:
    """掌握度变更流水（时间正序）。该表每次判卷/反馈都会插行，必须限量：
    默认取最近 limit 条；趋势分析等需要更长历史时显式传大值。"""
    rows = get_conn().execute(
        "SELECT point,score,verdict,created_at FROM ("
        "  SELECT point,score,verdict,created_at FROM mastery_history WHERE space_id=?"
        "  ORDER BY created_at DESC LIMIT ?"
        ") ORDER BY created_at", (space_id, max(1, limit))).fetchall()
    return rows_to_dicts(rows)


_POINT_MATCH_RATIO = 0.65  # 与 defects._error_stats_bulk 同一阈值：避免「导数应用/导数定义」互相串扰


def point_evidence(space_id: str, point: str, limit: int = 60) -> dict[str, Any] | None:
    """知识点判定溯源（DeepTutor 式 evidence↔synthesis）：掌握度现状 + 证据时间线。

    证据两类来源合并成一条时间线：
    - quiz_records：判卷答案中 knowledge_point 与该点模糊匹配（阈值同缺陷诊断），
      关联到具体卷子（topic/verdict/作答/错因），并就近吸附 mastery_history 的调分结果——
      学生能看到「哪次练习把掌握度调到了多少」；
    - mastery_history 剩余行：无对应卷子的调整（对话反馈「没听懂」、讲解检验等）单列。
    """
    point = (point or "").strip()
    if not point:
        return None
    mastery = get_mastery_point(space_id, point)
    if not mastery:
        return None
    hist = [h for h in list_mastery_history(space_id, limit=2000) if h["point"] == point]
    hist_used: set[int] = set()
    events: list[dict[str, Any]] = []
    for q in list_quizzes(space_id):
        for a in q["answers"]:
            kp = str(a.get("knowledge_point") or "").strip()
            if not kp or not a.get("verdict"):
                continue
            if not (kp == point or kp in point or point in kp
                    or difflib.SequenceMatcher(None, kp, point).ratio() >= _POINT_MATCH_RATIO):
                continue
            ts = q["created_at"] or 0
            # 就近吸附同一时刻的调分行（判卷 → adjust_mastery → history 间隔毫秒级）
            score_after, hit = None, None
            for i, h in enumerate(hist):
                if i in hist_used:
                    continue
                if abs((h["created_at"] or 0) - ts) < 3.0 and h["verdict"]:
                    score_after, hit = h["score"], i
                    break
            if hit is not None:
                hist_used.add(hit)
            events.append({
                "ts": ts, "kind": "quiz", "topic": q.get("topic") or "",
                "verdict": a.get("verdict"),
                "user_answer": str(a.get("user_answer") or "")[:120],
                "analysis": str(a.get("analysis") or "")[:200],
                "error_type": str(a.get("error_type") or ""),
                "score_after": score_after,
            })
    for i, h in enumerate(hist):
        if i in hist_used:
            continue
        events.append({"ts": h["created_at"] or 0, "kind": "adjust",
                       "verdict": h["verdict"], "score_after": h["score"]})
    events.sort(key=lambda e: e["ts"])
    return {"point": point, "mastery": mastery, "events": events[-limit:]}


def get_mastery_point(space_id: str, point: str) -> dict[str, Any] | None:
    row = _find_mastery(space_id, point)
    return row


def list_mastery(space_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(get_conn().execute(
        "SELECT * FROM mastery WHERE space_id=? ORDER BY score ASC, updated_at DESC", (space_id,)).fetchall())


def weak_points(space_id: str, limit: int = 8) -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT * FROM mastery WHERE space_id=? AND status!='mastered' "
        "ORDER BY score ASC, wrong DESC LIMIT ?", (space_id, limit)).fetchall()
    return rows_to_dicts(rows)


def due_points(space_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(get_conn().execute(
        "SELECT * FROM mastery WHERE space_id=? AND status!='mastered' AND due_at<=? "
        "ORDER BY due_at ASC", (space_id, now())).fetchall())


# ---------- 错题本 ----------

def wrong_questions(space_id: str) -> list[dict[str, Any]]:
    """跨测验聚合错题（按测验时间倒序），附带判卷分析、用户答案与知识点。"""
    out = []
    for q in list_quizzes(space_id):
        if not q["answers"]:
            continue
        graded = {a.get("qid"): a for a in q["answers"]}
        for question in q["questions"]:
            g = graded.get(question["id"])
            if not g or g.get("verdict") == "对":
                continue
            out.append({**question, "verdict": g.get("verdict", ""),
                        "analysis": g.get("analysis", ""),
                        "user_answer": g.get("user_answer", ""),
                        "quiz_id": q["id"], "quiz_topic": q["topic"],
                        "quiz_created_at": q["created_at"]})
    return out


def wrong_question_count(space_id: str) -> int:
    """错题数：只解析 answers JSON 计数（today 徽标用，免加载全部题目）。"""
    n = 0
    for r in get_conn().execute(
            "SELECT answers FROM quiz_records WHERE space_id=? AND answers!='[]'", (space_id,)).fetchall():
        try:
            answers = json.loads(r["answers"])
        except ValueError:
            continue
        n += sum(1 for a in answers if isinstance(a, dict) and a.get("verdict") not in (None, "", "对"))
    return n


# ---------- 闪卡（Leitner 复用掌握度的复习盒间隔） ----------

def add_flashcards(space_id: str, cards: list[dict]) -> list[dict]:
    c = get_conn()
    saved = []
    for card in cards:
        fid = new_id()
        c.execute("INSERT INTO flashcards(id,space_id,front,back,point,box,due_at,created_at) "
                  "VALUES(?,?,?,?,?,1,?,?)",
                  (fid, space_id, (card.get("front") or "").strip(),
                   (card.get("back") or "").strip(), (card.get("point") or "").strip()[:80],
                   now(), now()))
        saved.append({"id": fid, "front": card.get("front", ""), "back": card.get("back", ""),
                      "point": card.get("point", ""), "box": 1, "due_at": now(),
                      "kind": card.get("kind", "")})
    c.commit()
    return saved


def list_flashcards(space_id: str, due_only: bool = False, limit: int = 30,
                    with_preview: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM flashcards WHERE space_id=?"
    params: list[Any] = [space_id]
    if due_only:
        sql += " AND due_at<=?"
        params.append(now())
    sql += " ORDER BY due_at ASC LIMIT ?"
    params.append(limit)
    rows = get_conn().execute(sql, params).fetchall()
    cards = rows_to_dicts(rows)
    if with_preview:  # 到期复习流：附四档评分的下次间隔（秒）供按钮预告
        for card in cards:
            card["preview"] = _fsrs.preview_intervals(card)
    return cards


def flashcard_stats(space_id: str) -> dict[str, int]:
    c = get_conn()
    total = c.execute("SELECT COUNT(*) AS n FROM flashcards WHERE space_id=?", (space_id,)).fetchone()["n"]
    due = c.execute("SELECT COUNT(*) AS n FROM flashcards WHERE space_id=? AND due_at<=?",
                    (space_id, now())).fetchone()["n"]
    return {"total": total, "due": due}


def grade_flashcard(space_id: str, fid: str, know: bool | None = None,
                    rating: int = 0) -> dict[str, Any] | None:
    """刷卡自评走 FSRS 调度。rating 1..4（忘了/困难/良好/轻松）优先；
    旧调用只传 know 布尔时映射：记得→良好(3)、忘了→忘了(1)。"""
    c = get_conn()
    r = c.execute("SELECT * FROM flashcards WHERE id=? AND space_id=?", (fid, space_id)).fetchone()
    if not r:
        return None
    if rating not in (_fsrs.R_AGAIN, _fsrs.R_HARD, _fsrs.R_GOOD, _fsrs.R_EASY):
        rating = _fsrs.R_GOOD if know else _fsrs.R_AGAIN
    row = dict(r)
    sched = _fsrs.review(row, rating)
    reps = int(row["reps"] or 0) + 1
    lapses = int(row["lapses"] or 0) + (1 if rating == _fsrs.R_AGAIN else 0)
    c.execute("UPDATE flashcards SET box=?, due_at=?, state=?, step=?, stability=?, difficulty=?, "
              "last_review=?, reps=?, lapses=? WHERE id=?",
              (sched["box"], sched["due_at"], sched["state"], sched["step"], sched["stability"],
               sched["difficulty"], sched["last_review"], reps, lapses, fid))
    c.commit()
    return {"id": fid, "box": sched["box"], "due_at": sched["due_at"],
            "interval": sched["interval_seconds"], "state": sched["state"],
            "stability": sched["stability"], "reps": reps, "lapses": lapses}


def clear_flashcards(space_id: str) -> None:
    c = get_conn()
    c.execute("DELETE FROM flashcards WHERE space_id=?", (space_id,))
    c.commit()


# ---------- 学习计划任务 ----------

def _norm_due_date(due: str) -> str:
    """归一化为补零的 YYYY-MM-DD：strptime 接受 "2026-9-1"，原样入库会让
    today_snapshot 的字符串比较（"2026-9-1" <= "2026-09-12" 为 False）漏掉到期任务。"""
    due = (due or "").strip()[:10]
    if not due:
        return ""
    try:
        return time.strftime("%Y-%m-%d", time.strptime(due, "%Y-%m-%d"))
    except ValueError:
        raise ValueError("日期格式应为 YYYY-MM-DD") from None


def replace_plan_tasks(space_id: str, tasks: list[dict]) -> None:
    """重新生成计划时整体替换（含已完成历史，生成即代表重开一版计划）。

    只替换 AI 生成的任务（source_plan=''）；学涯计划推送的任务（source_plan=pid）
    不属于本空间计划的版本管理，误删会让完成状态无法在重推时找回。单事务写入。
    """
    c = get_conn()
    c.execute("DELETE FROM plan_tasks WHERE space_id=? AND source_plan=''", (space_id,))
    for t in tasks:
        _insert_plan_task(c, space_id, t)
    c.commit()


def _insert_plan_task(c: sqlite3.Connection, space_id: str, t: dict,
                      source_plan: str = "", done: int = 0, done_at: float = 0) -> str:
    tid = new_id()
    due = _norm_due_date(t.get("due_date") or t.get("due") or "")
    c.execute("INSERT INTO plan_tasks(id,space_id,phase,content,accept,points,due_date,method,source_plan,done,done_at,created_at) "
              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
              (tid, space_id, (t.get("phase") or "").strip()[:80],
               (t.get("content") or "").strip(), (t.get("accept") or "").strip(),
               json.dumps(t.get("points") or [], ensure_ascii=False),
               due, (t.get("method") or "").strip()[:40], source_plan, done, done_at, now()))
    return tid


def add_plan_task(space_id: str, t: dict, source_plan: str = "",
                  done: int = 0, done_at: float = 0) -> str:
    c = get_conn()
    tid = _insert_plan_task(c, space_id, t, source_plan, done, done_at)
    c.commit()
    return tid


def delete_plan_tasks_by_source(space_id: str, source_plan: str, keep_done: bool = False) -> int:
    """删除某学涯计划同步到空间的任务（push 重新同步/删除计划时用）。"""
    c = get_conn()
    if keep_done:
        n = c.execute("DELETE FROM plan_tasks WHERE space_id=? AND source_plan=? AND done=0",
                      (space_id, source_plan)).rowcount
    else:
        n = c.execute("DELETE FROM plan_tasks WHERE space_id=? AND source_plan=?",
                      (space_id, source_plan)).rowcount
    c.commit()
    return n


def list_plan_tasks(space_id: str) -> list[dict[str, Any]]:
    rows = rows_to_dicts(get_conn().execute(
        "SELECT * FROM plan_tasks WHERE space_id=? ORDER BY created_at", (space_id,)).fetchall())
    for t in rows:
        t["points"] = _safe_json(t["points"], [])
    return rows


def set_plan_task_date(space_id: str, task_id: str, due_date: str) -> dict[str, Any] | None:
    """设置/清除任务截止日期（YYYY-MM-DD，空串清除）。"""
    due_date = _norm_due_date(due_date)
    c = get_conn()
    r = c.execute("SELECT id FROM plan_tasks WHERE id=? AND space_id=?", (task_id, space_id)).fetchone()
    if not r:
        return None
    c.execute("UPDATE plan_tasks SET due_date=? WHERE id=?", (due_date, task_id))
    c.commit()
    return {"id": task_id, "due_date": due_date}


def today_snapshot(space_id: str) -> dict[str, Any]:
    """今日学习视图聚合：到期复习点 + 到期闪卡 + 今日/未排期计划任务 + 今日完成。"""
    today = time.strftime("%Y-%m-%d")
    tasks = list_plan_tasks(space_id)

    def _day(ts: float) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else ""

    due = due_points(space_id)
    flash = flashcard_stats(space_id)
    qb = question_bank_stats(space_id)
    return {
        "date": today,
        "due_points": due[:20],
        "due_total": len(due),
        "flash_due": flash["due"],
        "flash_total": flash["total"],
        "tasks_today": [t for t in tasks if not t["done"] and t["due_date"] and t["due_date"] <= today],
        "tasks_unscheduled": [t for t in tasks if not t["done"] and not t["due_date"]][:20],
        "done_today": [t for t in tasks if t["done"] and _day(t["done_at"]) == today],
        "wrong_count": wrong_question_count(space_id),
        "question_bank": qb,
    }


def toggle_plan_task(space_id: str, task_id: str, done: bool) -> dict[str, Any] | None:
    c = get_conn()
    r = c.execute("SELECT * FROM plan_tasks WHERE id=? AND space_id=?", (task_id, space_id)).fetchone()
    if not r:
        return None
    c.execute("UPDATE plan_tasks SET done=?, done_at=? WHERE id=?",
              (1 if done else 0, now() if done else 0, task_id))
    c.commit()
    if done:
        row = dict(r)
        try:
            from . import study_metrics
            points = []
            try:
                points = json.loads(row.get("points") or "[]")
            except ValueError:
                points = []
            study_metrics.record_method_use(
                space_id, row.get("method") or "", kind="task_done",
                meta={"task_id": task_id, "points": points[:6], "content": (row.get("content") or "")[:80]})
        except Exception:
            log.warning("任务打卡的方法效果埋点写入失败（task=%s）", task_id, exc_info=True)
    return {"id": task_id, "done": done}


# ---------- 通用元数据 ----------

def get_meta(key: str) -> str:
    r = get_conn().execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r["value"] if r else ""


def set_meta(key: str, value: str) -> None:
    c = get_conn()
    c.execute("INSERT INTO meta(key,value) VALUES(?,?) "
              "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    c.commit()


# ---------- 校园网信息（campus_net.py 的存储层） ----------

def campus_upsert(source: str, title: str, url: str, published: str) -> str:
    """按 URL 判重入库：新条目返回 added，已存在返回 dup（不覆盖首次抓到的日期）。"""
    c = get_conn()
    if c.execute("SELECT 1 FROM campus_items WHERE url=?", (url,)).fetchone():
        return "dup"
    c.execute("INSERT INTO campus_items(source,title,url,published,fetched_at) VALUES(?,?,?,?,?)",
              (source, title, url, published, now()))
    c.commit()
    return "added"


def campus_list(source: str = "", limit: int = 60, q: str = "") -> list[dict[str, Any]]:
    sql = "SELECT * FROM campus_items WHERE 1=1"
    args: list[Any] = []
    if source:
        sql += " AND source=?"
        args.append(source)
    if q.strip():
        sql += " AND title LIKE ? ESCAPE '\\'"
        esc = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        args.append(f"%{esc}%")
    sql += " ORDER BY published DESC, id DESC LIMIT ?"
    args.append(max(1, min(int(limit), 200)))
    return rows_to_dicts(get_conn().execute(sql, args).fetchall())


def campus_counts() -> dict[str, int]:
    return {r["source"]: r["n"] for r in get_conn().execute(
        "SELECT source, COUNT(*) AS n FROM campus_items GROUP BY source").fetchall()}


def campus_total() -> int:
    return get_conn().execute("SELECT COUNT(*) AS n FROM campus_items").fetchone()["n"]


def campus_prune(keep_per_source: int = 300) -> int:
    """每个信息源只保留最近 keep_per_source 条，防止长期运行无限膨胀。"""
    c = get_conn()
    removed = 0
    for (src,) in c.execute("SELECT DISTINCT source FROM campus_items").fetchall():
        cur = c.execute("""DELETE FROM campus_items WHERE source=? AND id NOT IN (
                       SELECT id FROM campus_items WHERE source=?
                       ORDER BY published DESC, id DESC LIMIT ?)""",
                  (src, src, keep_per_source))
        removed += cur.rowcount
    c.commit()
    return removed


# ---------- 成长手册 ----------

def save_handbook(title: str, profile: dict, content: str, space_id: str = "") -> str:
    c = get_conn()
    hid = new_id()
    c.execute("INSERT INTO handbooks(id,title,profile,space_id,content,created_at) VALUES(?,?,?,?,?,?)",
              (hid, title, json.dumps(profile, ensure_ascii=False), space_id, content, now()))
    c.commit()
    return hid


def list_handbooks() -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT id,title,space_id,created_at FROM handbooks ORDER BY created_at DESC").fetchall()
    return rows_to_dicts(rows)


def get_handbook(hid: str) -> dict[str, Any] | None:
    r = get_conn().execute("SELECT * FROM handbooks WHERE id=?", (hid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["profile"] = json.loads(d["profile"])
    return d


def delete_handbook(hid: str) -> None:
    get_conn().execute("DELETE FROM handbooks WHERE id=?", (hid,))
    get_conn().commit()


# ---------- 个人学生档案（单用户，一行） ----------

_PROFILE_FIELDS = ("current_school", "major", "year", "rank_hint",
                   "goal_type", "target_school", "target_major", "timeline", "notes")


def get_student_profile() -> dict[str, Any]:
    r = get_conn().execute("SELECT * FROM student_profile WHERE id=1").fetchone()
    if not r:
        empty = {k: "" for k in _PROFILE_FIELDS}
        empty.update({"flags": [], "learner_personas": [], "updated_at": 0})
        return empty
    d = dict(r)
    for key in ("flags", "learner_personas"):
        try:
            d[key] = json.loads(d.get(key) or "[]")
        except ValueError:
            d[key] = []
    return d


def save_student_profile(fields: dict) -> dict[str, Any]:
    """整行覆盖保存（前端表单总是提交完整档案）。"""
    clean = {k: (fields.get(k) or "").strip()[:120] for k in _PROFILE_FIELDS}
    flags = json.dumps([str(f).strip()[:40] for f in (fields.get("flags") or []) if str(f).strip()],
                       ensure_ascii=False)
    personas = json.dumps([str(p).strip()[:40] for p in (fields.get("learner_personas") or []) if str(p).strip()],
                          ensure_ascii=False)
    c = get_conn()
    c.execute(
        "INSERT INTO student_profile(id,current_school,major,year,rank_hint,flags,goal_type,"
        "target_school,target_major,timeline,notes,learner_personas,updated_at) "
        "VALUES(1,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET current_school=excluded.current_school, major=excluded.major, "
        "year=excluded.year, rank_hint=excluded.rank_hint, flags=excluded.flags, "
        "goal_type=excluded.goal_type, target_school=excluded.target_school, "
        "target_major=excluded.target_major, timeline=excluded.timeline, notes=excluded.notes, "
        "learner_personas=excluded.learner_personas, updated_at=excluded.updated_at",
        (clean["current_school"], clean["major"], clean["year"], clean["rank_hint"], flags,
         clean["goal_type"] or "考研", clean["target_school"], clean["target_major"],
         clean["timeline"], clean["notes"], personas, now()))
    c.commit()
    return get_student_profile()


# ---------- 知识点依赖图（缺陷传播用） ----------

def set_space_edges(space_id: str, edges: list[dict], source: str) -> int:
    """整体替换某来源（llm / curriculum）的依赖边。edge: {from, to}。"""
    c = get_conn()
    c.execute("DELETE FROM concept_edges WHERE space_id=? AND source=?", (space_id, source))
    n = 0
    for e in edges:
        f, t = (e.get("from") or "").strip()[:80], (e.get("to") or "").strip()[:80]
        if not f or not t or f == t:
            continue
        cur = c.execute("INSERT OR IGNORE INTO concept_edges(space_id,from_point,to_point,source,created_at) "
                        "VALUES(?,?,?,?,?)", (space_id, f, t, source, now()))
        n += max(0, cur.rowcount)  # 被 UNIQUE 忽略的重复边 rowcount=0，不计入「新增」
    c.commit()
    return n


def count_space_edges(space_id: str, source: str) -> int:
    r = get_conn().execute("SELECT COUNT(*) AS n FROM concept_edges WHERE space_id=? AND source=?",
                           (space_id, source)).fetchone()
    return r["n"]


def list_edges(space_id: str) -> list[dict[str, Any]]:
    return rows_to_dicts(get_conn().execute(
        "SELECT from_point, to_point, source FROM concept_edges WHERE space_id=?", (space_id,)).fetchall())


# ---------- 课程表（学涯规划） ----------

def replace_schedule(term: str, courses: list[dict]) -> int:
    """整体替换某学期的课程表（导入/编辑保存都走这条路径，简单且不会重复）。"""
    c = get_conn()
    c.execute("DELETE FROM course_schedule WHERE term=?", (term,))
    n = 0
    for t in courses:
        name = (t.get("course") or "").strip()
        if not name:
            continue
        try:
            raw_day = int(t.get("day") or 0)
        except (TypeError, ValueError):
            raw_day = 0
        day = min(7, max(0, raw_day))  # 0 表示星期未定，保留原始语义而不强行归入周一
        c.execute(
            "INSERT INTO course_schedule(id,term,day,period,course,teacher,room,weeks,kind,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (new_id(), term, day, (t.get("period") or "").strip()[:20], name[:80],
             (t.get("teacher") or "").strip()[:40], (t.get("room") or "").strip()[:40],
             (t.get("weeks") or "").strip()[:40], (t.get("kind") or "").strip()[:12], now()))
        n += 1
    c.commit()
    return n


def list_schedule(term: str) -> list[dict[str, Any]]:
    return rows_to_dicts(get_conn().execute(
        "SELECT * FROM course_schedule WHERE term=? ORDER BY day, period, course", (term,)).fetchall())


def list_schedule_terms() -> list[dict[str, Any]]:
    # 按最近一次写入时间排序（学期名混合"2025-2026-1"与"大二上"等格式时字符串序不可靠）
    return rows_to_dicts(get_conn().execute(
        "SELECT term, COUNT(*) AS courses FROM course_schedule GROUP BY term "
        "ORDER BY MAX(created_at) DESC").fetchall())


def delete_schedule(term: str) -> None:
    get_conn().execute("DELETE FROM course_schedule WHERE term=?", (term,))
    get_conn().commit()


# ---------- 学涯规划（目标导向学习计划） ----------

def save_career_plan(title: str, meta: dict, summary: str, tasks: list[dict], markdown: str) -> str:
    c = get_conn()
    pid = new_id()
    c.execute(
        "INSERT INTO career_plans(id,title,school,major,goal_type,target,term,horizon,summary,tasks,markdown,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (pid, title[:120], (meta.get("school") or "")[:60], (meta.get("major") or "")[:60],
         (meta.get("goal_type") or "")[:20], (meta.get("target") or "")[:120],
         (meta.get("term") or "")[:20], (meta.get("horizon") or "")[:20],
         summary[:200], json.dumps(tasks, ensure_ascii=False), markdown, now()))
    c.commit()
    return pid


def list_career_plans() -> list[dict[str, Any]]:
    rows = get_conn().execute(
        "SELECT id,title,school,major,goal_type,target,term,horizon,summary,created_at "
        "FROM career_plans ORDER BY created_at DESC").fetchall()
    return rows_to_dicts(rows)


def get_career_plan(pid: str) -> dict[str, Any] | None:
    r = get_conn().execute("SELECT * FROM career_plans WHERE id=?", (pid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["tasks"] = json.loads(d["tasks"])
    except ValueError:
        d["tasks"] = []
    return d


def toggle_career_task(pid: str, task_id: str, done: bool) -> dict[str, Any] | None:
    plan = get_career_plan(pid)
    if not plan:
        return None
    hit = None
    for t in plan["tasks"]:
        if t.get("id") == task_id:
            t["done"] = bool(done)
            t["done_at"] = now() if done else 0
            hit = t
    if not hit:
        return None
    c = get_conn()
    c.execute("UPDATE career_plans SET tasks=? WHERE id=?",
              (json.dumps(plan["tasks"], ensure_ascii=False), pid))
    # 计划内打卡同步到已推送到课程空间的任务（同来源且内容一致），两处状态不再各管各的
    c.execute(
        "UPDATE plan_tasks SET done=?, done_at=? WHERE source_plan=? AND content=?",
        (1 if done else 0, now() if done else 0, pid, hit.get("content") or ""))
    c.commit()
    return hit


def delete_career_plan(pid: str) -> dict[str, int]:
    """删除学涯计划，并移除它同步到各空间的任务（计划是任务的唯一来源）。"""
    c = get_conn()
    pushed = c.execute("DELETE FROM plan_tasks WHERE source_plan=?", (pid,)).rowcount
    c.execute("DELETE FROM career_plans WHERE id=?", (pid,))
    c.commit()
    return {"deleted_plan": 1, "deleted_pushed_tasks": pushed}


# ---------- 自定义培养方案（导入本校培养手册解析入库） ----------

def save_syllabus_custom(school: str, major: str, data: dict, source: str = "") -> None:
    get_conn().execute(
        "INSERT INTO syllabus_custom(school,major,data,source,updated_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(school,major) DO UPDATE SET data=excluded.data, "
        "source=excluded.source, updated_at=excluded.updated_at",
        (school[:60], major[:80], json.dumps(data, ensure_ascii=False), source[:200], now()))
    get_conn().commit()


def get_syllabus_custom(school: str, major: str) -> dict[str, Any] | None:
    """精确匹配 → 导入时登记的别名 → 专业名相似度回落
    （导入时的存储键来自 LLM 抽取/模板名，与用户查询表述可能存在漂移）。"""
    c = get_conn()
    r = c.execute("SELECT * FROM syllabus_custom WHERE school=? AND major=?",
                  (school, major)).fetchone()
    if not r:
        import difflib
        best, best_score = None, 0.0
        for row in c.execute("SELECT * FROM syllabus_custom WHERE school=?", (school,)).fetchall():
            try:
                aliases = json.loads(row["data"]).get("aliases") or []
            except (ValueError, AttributeError):
                aliases = []
            score = 1.0 if major in aliases else 0.0
            ratio = difflib.SequenceMatcher(None, row["major"], major).ratio()
            if ratio > score:
                score = ratio
            if score > best_score:
                best, best_score = row, score
        r = best if best and best_score >= 0.55 else None
    if not r:
        return None
    d = dict(r)
    try:
        d["data"] = json.loads(d["data"])
    except ValueError:
        d["data"] = {}
    return d


def list_syllabus_custom(school: str = "") -> list[dict[str, Any]]:
    if school:
        rows = get_conn().execute(
            "SELECT school,major,source,updated_at FROM syllabus_custom WHERE school=? "
            "ORDER BY major", (school,)).fetchall()
    else:
        rows = get_conn().execute(
            "SELECT school,major,source,updated_at FROM syllabus_custom ORDER BY school, major").fetchall()
    return rows_to_dicts(rows)


# ---------- 已修课程（完成度审核的数据源，用户级、不绑空间） ----------

def add_taken_course(name: str, credit: float = 0.0, grade: str = "",
                     semester: str = "", status: str = "done") -> dict[str, Any]:
    """新增一门已修/修读中课程；同名（归一化后）幂等覆盖。绩点在此统一换算。"""
    from . import audit
    name = (name or "").strip()[:100]
    if not name:
        raise ValueError("课程名不能为空")
    c = get_conn()
    norm = audit.norm_name(name)
    existing = None
    for row in c.execute("SELECT id,name FROM taken_courses").fetchall():
        if audit.norm_name(row["name"]) == norm:
            existing = row["id"]
            break
    gpa = audit.grade_to_gpa(grade)
    if existing:
        c.execute("UPDATE taken_courses SET name=?, credit=?, grade=?, gpa=?, semester=?, status=? WHERE id=?",
                  (name, round(float(credit or 0), 2), (grade or "").strip()[:20], gpa,
                   (semester or "").strip()[:30], status if status in ("done", "taking") else "done", existing))
        tid = existing
    else:
        tid = new_id()
        c.execute("INSERT INTO taken_courses(id,name,credit,grade,gpa,semester,status,created_at) "
                  "VALUES(?,?,?,?,?,?,?,?)",
                  (tid, name, round(float(credit or 0), 2), (grade or "").strip()[:20], gpa,
                   (semester or "").strip()[:30], status if status in ("done", "taking") else "done", now()))
    c.commit()
    r = c.execute("SELECT * FROM taken_courses WHERE id=?", (tid,)).fetchone()
    return dict(r)


def list_taken_courses() -> list[dict[str, Any]]:
    return rows_to_dicts(get_conn().execute(
        "SELECT * FROM taken_courses ORDER BY semester, created_at").fetchall())


def delete_taken_course(cid: str) -> bool:
    c = get_conn()
    n = c.execute("DELETE FROM taken_courses WHERE id=?", (cid,)).rowcount
    c.commit()
    return n > 0


def clear_taken_courses() -> int:
    c = get_conn()
    n = c.execute("SELECT COUNT(*) AS n FROM taken_courses").fetchone()["n"]
    c.execute("DELETE FROM taken_courses")
    c.commit()
    return n


# ---------- 全局题库（出过的题入库复用，省 token + 正确率可统计） ----------

def add_to_question_bank(space_id: str, questions: list[dict], difficulty: int = 1) -> int:
    """把出过的题写入题库（按题干去重）。question 列存整题 JSON（含 answer/options/knowledge_point），
    复用出题时才能还原完整题面与标准答案；老库的纯文本行由读取端降级兼容。"""
    c = get_conn()
    added = 0
    for q in questions:
        if not isinstance(q, dict) or not q.get("question"):
            continue
        qtext = q["question"].strip()
        if len(qtext) < 5:
            continue
        # 去重：同空间同题干不重复入库（题干含 % _ 时须转义，否则会误判重复静默丢题）
        existing = c.execute(
            "SELECT id FROM question_bank WHERE space_id=? AND question LIKE ? ESCAPE '\\'",
            (space_id, f"%{like_escape(qtext[:50])}%")).fetchone()
        if existing:
            continue
        c.execute(
            "INSERT INTO question_bank(id,space_id,knowledge_point,question,qtype,difficulty,times_used,created_at) "
            "VALUES(?,?,?,?,?,?,0,?)",
            (new_id(), space_id, q.get("knowledge_point", ""), json.dumps(q, ensure_ascii=False),
             q.get("type", ""), difficulty, now()))
        added += 1
    c.commit()
    return added


def query_question_bank(space_id: str, points: list[str], limit: int = 5) -> list[dict]:
    """按知识点查题库中已有的题（模糊匹配）。"""
    import difflib
    c = get_conn()
    rows = c.execute(
        "SELECT * FROM question_bank WHERE space_id=? ORDER BY times_used ASC, created_at DESC LIMIT 50",
        (space_id,)).fetchall()
    matched = []
    for r in rows:
        d = dict(r)
        kp = d.get("knowledge_point", "")
        if not kp:
            continue
        for pt in points:
            ratio = difflib.SequenceMatcher(None, kp, pt).ratio()
            if ratio >= 0.5 or pt in kp or kp in pt:
                try:
                    d["question_obj"] = json.loads(d["question"])
                except ValueError:
                    d["question_obj"] = {"question": d["question"], "type": d.get("qtype", "")}
                matched.append(d)
                break
        if len(matched) >= limit:
            break
    return matched


def mark_question_used(qb_id: str, correct: bool) -> None:
    """标记题库中某题被使用过一次，记录是否答对。"""
    c = get_conn()
    c.execute(
        "UPDATE question_bank SET times_used=times_used+1, times_correct=times_correct+?, last_used_at=? WHERE id=?",
        (1 if correct else 0, now(), qb_id))
    c.commit()


def question_bank_stats(space_id: str) -> dict:
    c = get_conn()
    total = c.execute("SELECT COUNT(*) AS n FROM question_bank WHERE space_id=?", (space_id,)).fetchone()["n"]
    used = c.execute("SELECT COUNT(*) AS n FROM question_bank WHERE space_id=? AND times_used>0",
                     (space_id,)).fetchone()["n"]
    return {"total": total, "used": used}
