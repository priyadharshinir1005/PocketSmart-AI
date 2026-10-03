import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings


def _connect() -> sqlite3.Connection:
    path: Path = settings.resolved_database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def _database_connection():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _database_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                planner_type TEXT NOT NULL,
                request_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_recommendations_user_created
                ON recommendations(user_id, created_at DESC);
            CREATE TABLE IF NOT EXISTS revoked_tokens (
                token_id TEXT PRIMARY KEY,
                expires_at INTEGER NOT NULL
            );
            """
        )


def create_user(username: str, email: str, password_hash: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with _database_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users(username, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (username.strip(), email.strip().lower(), password_hash, now),
        )
        row = conn.execute("SELECT id, username, email, created_at FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def get_user_by_username(username: str) -> dict[str, Any] | None:
    with _database_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with _database_connection() as conn:
        row = conn.execute("SELECT id, username, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def add_recommendation(
    user_id: int,
    planner_type: str,
    request_data: dict[str, Any],
    result_data: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with _database_connection() as conn:
        cursor = conn.execute(
            """INSERT INTO recommendations(user_id, planner_type, request_json, result_json, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, planner_type, json.dumps(request_data), json.dumps(result_data), source, now),
        )
        rec_id = cursor.lastrowid
    return {"id": rec_id, "created_at": now}


def get_recommendation(user_id: int, recommendation_id: int) -> dict[str, Any] | None:
    with _database_connection() as conn:
        row = conn.execute(
            "SELECT * FROM recommendations WHERE id = ? AND user_id = ?",
            (recommendation_id, user_id),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["request"] = json.loads(item.pop("request_json"))
    item["result"] = json.loads(item.pop("result_json"))
    return item


def list_recommendations(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    with _database_connection() as conn:
        rows = conn.execute(
            """SELECT id, planner_type, request_json, result_json, source, created_at
               FROM recommendations WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?""",
            (user_id, max(1, min(limit, 100))),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["request"] = json.loads(item.pop("request_json"))
        item["result"] = json.loads(item.pop("result_json"))
        result.append(item)
    return result


def recommendation_count(user_id: int) -> int:
    with _database_connection() as conn:
        row = conn.execute("SELECT COUNT(*) AS count FROM recommendations WHERE user_id = ?", (user_id,)).fetchone()
    return int(row["count"])


def revoke_token(token_id: str, expires_at: int) -> None:
    with _database_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO revoked_tokens(token_id, expires_at) VALUES (?, ?)", (token_id, expires_at))


def is_token_revoked(token_id: str) -> bool:
    with _database_connection() as conn:
        row = conn.execute("SELECT 1 FROM revoked_tokens WHERE token_id = ?", (token_id,)).fetchone()
    return row is not None


def cleanup_expired_tokens(now_epoch: int) -> None:
    with _database_connection() as conn:
        conn.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (now_epoch,))
