from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    # SQLite allows only one writer at a time. The application is expected to
    # process one update at a time (see handlers/__init__.py's comment on
    # observe_message), so this is defense-in-depth, not the primary fix, for
    # any writes that do briefly overlap: wait and retry for up to 5s instead
    # of failing immediately with "database is locked".
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def get_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
