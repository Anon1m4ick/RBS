from __future__ import annotations

import sqlite3
import uuid
from datetime import UTC, datetime

from oblak_server.config import Settings
from oblak_server.security import hash_token


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def connect(settings: Settings) -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(settings: Settings) -> None:
    with connect(settings) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                token_hash TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS functions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id),
                name TEXT NOT NULL,
                code BLOB NOT NULL,
                requirements BLOB,
                code_sha256 TEXT NOT NULL,
                requirements_sha256 TEXT,
                status TEXT NOT NULL,
                verification_result TEXT,
                invoke_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                deleted_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_functions_user_id
                ON functions(user_id);

            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                event_type TEXT NOT NULL,
                actor_user_id TEXT,
                function_id TEXT,
                request_id TEXT,
                ip TEXT,
                outcome TEXT NOT NULL,
                details_json TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE
            );
            """
        )
        if settings.bootstrap_username and settings.bootstrap_token:
            ensure_user(conn, settings.bootstrap_username, settings.bootstrap_token)
        conn.commit()


def ensure_user(conn: sqlite3.Connection, username: str, token: str) -> sqlite3.Row:
    existing = conn.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if existing:
        return existing

    user_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO users (id, username, token_hash, active, created_at)
        VALUES (?, ?, ?, 1, ?)
        """,
        (user_id, username, hash_token(token), utc_now()),
    )
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def find_user_by_token_hash(conn: sqlite3.Connection, token_hash: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM users
        WHERE token_hash = ? AND active = 1
        """,
        (token_hash,),
    ).fetchone()
