from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable

from ..models import User


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_user(row: sqlite3.Row) -> User:
    return User(id=row["telegram_user_id"], username=row["username"], display_name=row["display_name"])


def upsert_user(conn: sqlite3.Connection, *, user_id: int, username: str | None, display_name: str) -> None:
    normalized_username = username.lower() if username else None
    conn.execute(
        """
        INSERT INTO users (telegram_user_id, username, display_name, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(telegram_user_id) DO UPDATE SET
            username = excluded.username,
            display_name = excluded.display_name,
            updated_at = excluded.updated_at
        """,
        (user_id, normalized_username, display_name, _now()),
    )


def upsert_chat_user(conn: sqlite3.Connection, *, chat_id: int, user_id: int) -> None:
    conn.execute(
        """
        INSERT INTO chat_users (chat_id, user_id, last_seen_at)
        VALUES (?, ?, ?)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET last_seen_at = excluded.last_seen_at
        """,
        (chat_id, user_id, _now()),
    )


def get_user(conn: sqlite3.Connection, user_id: int) -> User | None:
    row = conn.execute(
        "SELECT telegram_user_id, username, display_name FROM users WHERE telegram_user_id = ?",
        (user_id,),
    ).fetchone()
    return _row_to_user(row) if row else None


def resolve_username(conn: sqlite3.Connection, *, chat_id: int, username: str) -> User | None:
    normalized = username.lstrip("@").lower()
    row = conn.execute(
        """
        SELECT u.telegram_user_id, u.username, u.display_name
        FROM users u
        JOIN chat_users cu ON cu.user_id = u.telegram_user_id
        WHERE cu.chat_id = ? AND u.username = ?
        """,
        (chat_id, normalized),
    ).fetchone()
    return _row_to_user(row) if row else None


def get_display_names(conn: sqlite3.Connection, user_ids: Iterable[int]) -> dict[int, str]:
    names: dict[int, str] = {}
    for user_id in user_ids:
        user = get_user(conn, user_id)
        names[user_id] = user.display_name if user else f"user {user_id}"
    return names
