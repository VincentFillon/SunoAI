"""
history_index.py — Lightweight SQLite index for session history.

Created next to the executable (PyInstaller-aware via `sys.frozen`).
Powers fast pagination, full-text search, and cumulative usage queries
without re-parsing every markdown file on every keystroke.

Schema:
    sessions(id, file_path, file_mtime, created_at, intent_excerpt,
             provider, model, generation_count, vocal_presence, language,
             total_input_tokens, total_output_tokens, total_cost_usd)
    sessions_fts (FTS5 virtual table over intent_excerpt + provider + model)

If FTS5 is not available on the runtime sqlite3 build, queries fall back
to LIKE — slower but still correct.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
from pathlib import Path
from dataclasses import dataclass

# ============================================================
# PATHS
# ============================================================

_BASE_DIR = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
DB_PATH = str(_BASE_DIR / "history.db")

# Connection is per-thread; SQLite objects are not safe across threads.
_thread_local = threading.local()


def _conn() -> sqlite3.Connection:
    c = getattr(_thread_local, "conn", None)
    if c is None:
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA synchronous=NORMAL;")
        _thread_local.conn = c
        _ensure_schema(c)
    return c


# ============================================================
# SCHEMA
# ============================================================

_HAS_FTS5: bool | None = None


def _check_fts5(c: sqlite3.Connection) -> bool:
    global _HAS_FTS5
    if _HAS_FTS5 is not None:
        return _HAS_FTS5
    try:
        c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(a)")
        c.execute("DROP TABLE _fts5_probe")
        _HAS_FTS5 = True
    except sqlite3.OperationalError:
        _HAS_FTS5 = False
    return _HAS_FTS5


def _ensure_schema(c: sqlite3.Connection) -> None:
    c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id                   TEXT PRIMARY KEY,
            file_path            TEXT NOT NULL UNIQUE,
            file_mtime           REAL NOT NULL,
            created_at           TEXT NOT NULL,
            intent_excerpt       TEXT,
            provider             TEXT,
            model                TEXT,
            generation_count     INTEGER,
            vocal_presence       TEXT,
            language             TEXT,
            total_input_tokens   INTEGER,
            total_output_tokens  INTEGER,
            total_cost_usd       REAL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sessions_path    ON sessions(file_path);
    """)
    if _check_fts5(c):
        c.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
                intent_excerpt, provider, model, content='sessions', content_rowid='rowid'
            );
            CREATE TRIGGER IF NOT EXISTS sessions_ai AFTER INSERT ON sessions BEGIN
              INSERT INTO sessions_fts(rowid, intent_excerpt, provider, model)
              VALUES (new.rowid, new.intent_excerpt, new.provider, new.model);
            END;
            CREATE TRIGGER IF NOT EXISTS sessions_ad AFTER DELETE ON sessions BEGIN
              INSERT INTO sessions_fts(sessions_fts, rowid, intent_excerpt, provider, model)
              VALUES('delete', old.rowid, old.intent_excerpt, old.provider, old.model);
            END;
            CREATE TRIGGER IF NOT EXISTS sessions_au AFTER UPDATE ON sessions BEGIN
              INSERT INTO sessions_fts(sessions_fts, rowid, intent_excerpt, provider, model)
              VALUES('delete', old.rowid, old.intent_excerpt, old.provider, old.model);
              INSERT INTO sessions_fts(rowid, intent_excerpt, provider, model)
              VALUES (new.rowid, new.intent_excerpt, new.provider, new.model);
            END;
        """)
    c.commit()


# ============================================================
# ROW MODEL
# ============================================================

@dataclass
class SessionRow:
    id: str
    file_path: str
    file_mtime: float
    created_at: str
    intent_excerpt: str
    provider: str
    model: str
    generation_count: int
    vocal_presence: str
    language: str
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: float | None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> "SessionRow":
        return cls(
            id=r["id"],
            file_path=r["file_path"],
            file_mtime=r["file_mtime"],
            created_at=r["created_at"],
            intent_excerpt=r["intent_excerpt"] or "",
            provider=r["provider"] or "",
            model=r["model"] or "",
            generation_count=r["generation_count"] or 0,
            vocal_presence=r["vocal_presence"] or "",
            language=r["language"] or "",
            total_input_tokens=r["total_input_tokens"] or 0,
            total_output_tokens=r["total_output_tokens"] or 0,
            total_cost_usd=r["total_cost_usd"],
        )


# ============================================================
# UPSERT / DELETE
# ============================================================

def upsert_from_parsed(parsed: dict) -> None:
    """Insert/update a session row from a parsed file dict (from core._parse_session_file)."""
    if not parsed:
        return
    sd = parsed.get("session_data") or {}
    gens = parsed.get("generations") or []
    fp = parsed["filepath"]
    try:
        mtime = os.path.getmtime(fp)
    except OSError:
        return
    session_id = sd.get("id") or os.path.splitext(os.path.basename(fp))[0]
    intent = (sd.get("user_intent") or "").strip()
    if not intent:
        intent = " / ".join(filter(None, [sd.get("style", ""), sd.get("artist", "")]))
    intent_excerpt = intent[:200]
    usage = sd.get("usage") or []
    total_in = sum((u.get("input_tokens") or 0) for u in usage)
    total_out = sum((u.get("output_tokens") or 0) for u in usage)
    costs = [u.get("cost_usd") for u in usage]
    total_cost = sum(c for c in costs if c is not None) if any(c is not None for c in costs) else None
    created_at = gens[0]["ts"] if gens else session_id
    c = _conn()
    c.execute("""
        INSERT INTO sessions
          (id, file_path, file_mtime, created_at, intent_excerpt, provider, model,
           generation_count, vocal_presence, language,
           total_input_tokens, total_output_tokens, total_cost_usd)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          file_path=excluded.file_path,
          file_mtime=excluded.file_mtime,
          created_at=excluded.created_at,
          intent_excerpt=excluded.intent_excerpt,
          provider=excluded.provider,
          model=excluded.model,
          generation_count=excluded.generation_count,
          vocal_presence=excluded.vocal_presence,
          language=excluded.language,
          total_input_tokens=excluded.total_input_tokens,
          total_output_tokens=excluded.total_output_tokens,
          total_cost_usd=excluded.total_cost_usd
    """, (
        session_id, fp, mtime, created_at, intent_excerpt,
        sd.get("provider", ""), sd.get("model", ""),
        len(gens), sd.get("vocal_presence", ""), sd.get("detected_language", ""),
        total_in, total_out, total_cost,
    ))
    c.commit()


def delete_session(session_id: str) -> None:
    c = _conn()
    c.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    c.commit()


def delete_by_path(file_path: str) -> None:
    c = _conn()
    c.execute("DELETE FROM sessions WHERE file_path = ?", (file_path,))
    c.commit()


def get_by_path(file_path: str) -> SessionRow | None:
    c = _conn()
    row = c.execute("SELECT * FROM sessions WHERE file_path = ?", (file_path,)).fetchone()
    return SessionRow.from_row(row) if row else None


# ============================================================
# QUERIES
# ============================================================

def count(query: str = "") -> int:
    c = _conn()
    if not query.strip():
        return c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    if _check_fts5(c):
        try:
            return c.execute(
                "SELECT COUNT(*) FROM sessions_fts WHERE sessions_fts MATCH ?",
                (_fts_query(query),),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            pass
    q = f"%{query.strip().lower()}%"
    return c.execute(
        "SELECT COUNT(*) FROM sessions WHERE "
        "LOWER(intent_excerpt) LIKE ? OR LOWER(provider) LIKE ? OR LOWER(model) LIKE ?",
        (q, q, q),
    ).fetchone()[0]


def list_sessions(query: str = "", offset: int = 0, limit: int = 15) -> list[SessionRow]:
    c = _conn()
    if not query.strip():
        rows = c.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [SessionRow.from_row(r) for r in rows]
    if _check_fts5(c):
        try:
            rows = c.execute(
                """SELECT s.* FROM sessions_fts f
                   JOIN sessions s ON s.rowid = f.rowid
                   WHERE f MATCH ?
                   ORDER BY s.id DESC LIMIT ? OFFSET ?""",
                (_fts_query(query), limit, offset),
            ).fetchall()
            return [SessionRow.from_row(r) for r in rows]
        except sqlite3.OperationalError:
            pass
    q = f"%{query.strip().lower()}%"
    rows = c.execute(
        "SELECT * FROM sessions WHERE "
        "LOWER(intent_excerpt) LIKE ? OR LOWER(provider) LIKE ? OR LOWER(model) LIKE ? "
        "ORDER BY id DESC LIMIT ? OFFSET ?",
        (q, q, q, limit, offset),
    ).fetchall()
    return [SessionRow.from_row(r) for r in rows]


def all_paths() -> list[str]:
    c = _conn()
    rows = c.execute("SELECT file_path FROM sessions").fetchall()
    return [r["file_path"] for r in rows]


def _fts_query(s: str) -> str:
    """Sanitize an FTS5 query — tokens joined with AND, wildcards on each token."""
    tokens = [t for t in s.strip().split() if t]
    if not tokens:
        return "*"
    safe = []
    for t in tokens:
        # Escape double quotes; quote each token to disable FTS special chars
        t2 = t.replace('"', '""')
        safe.append(f'"{t2}"*')
    return " AND ".join(safe)


# ============================================================
# USAGE AGGREGATES
# ============================================================

def usage_aggregates(year_month: str | None = None) -> list[dict]:
    """Sum tokens and cost grouped by (provider, model).

    `year_month` like "2026-05" filters by created_at prefix; None = all time.
    """
    c = _conn()
    if year_month:
        rows = c.execute(
            """SELECT provider, model,
                      SUM(total_input_tokens)  AS inp,
                      SUM(total_output_tokens) AS outp,
                      SUM(total_cost_usd)      AS cost,
                      COUNT(*)                 AS n
               FROM sessions
               WHERE substr(created_at, 1, 7) = ?
               GROUP BY provider, model
               ORDER BY cost DESC NULLS LAST""",
            (year_month,),
        ).fetchall()
    else:
        rows = c.execute(
            """SELECT provider, model,
                      SUM(total_input_tokens)  AS inp,
                      SUM(total_output_tokens) AS outp,
                      SUM(total_cost_usd)      AS cost,
                      COUNT(*)                 AS n
               FROM sessions
               GROUP BY provider, model
               ORDER BY cost DESC NULLS LAST"""
        ).fetchall()
    return [dict(r) for r in rows]


# ============================================================
# REINDEX
# ============================================================

def reindex(outputs_dir: str, parse_fn) -> tuple[int, int]:
    """Walk outputs_dir, upsert new/modified files, delete missing ones.

    `parse_fn(filepath) -> parsed_dict | None` (typically core._parse_session_file).
    Returns (upserts, deletes).
    """
    import glob as _glob
    upserts = 0
    deletes = 0
    seen = set()
    pattern = os.path.join(outputs_dir, "*.md")
    for fp in _glob.glob(pattern):
        seen.add(fp)
        try:
            mtime = os.path.getmtime(fp)
        except OSError:
            continue
        row = get_by_path(fp)
        if row and row.file_mtime >= mtime:
            continue
        parsed = parse_fn(fp)
        if parsed:
            upsert_from_parsed(parsed)
            upserts += 1
    for fp in all_paths():
        if fp not in seen and not os.path.exists(fp):
            delete_by_path(fp)
            deletes += 1
    return upserts, deletes
