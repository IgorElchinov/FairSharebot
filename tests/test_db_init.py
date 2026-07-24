from __future__ import annotations

import sqlite3

import pytest

from fairsharebot.db.init_db import init_db

EXPECTED_TABLES = {"users", "chat_users", "trips", "payments", "payment_splits"}


def test_init_db_creates_expected_tables(tmp_path):
    db_path = tmp_path / "test.sqlite3"

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        conn.close()

    assert EXPECTED_TABLES <= tables


def test_init_db_is_idempotent(tmp_path):
    db_path = tmp_path / "test.sqlite3"

    init_db(db_path)
    init_db(db_path)  # should not raise


def test_only_one_open_trip_per_chat(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO users (telegram_user_id, display_name, updated_at) "
            "VALUES (1, 'Alice', '2026-01-01')"
        )
        conn.execute(
            "INSERT INTO trips (chat_id, name, created_by, created_at) "
            "VALUES (100, 'Trip A', 1, '2026-01-01')"
        )
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO trips (chat_id, name, created_by, created_at) "
                "VALUES (100, 'Trip B', 1, '2026-01-02')"
            )
            conn.commit()
    finally:
        conn.close()
