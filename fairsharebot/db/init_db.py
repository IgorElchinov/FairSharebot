from __future__ import annotations

import sqlite3
from pathlib import Path

from .connection import get_connection

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# CREATE TABLE IF NOT EXISTS is a no-op against an already-initialized DB, so
# it won't retroactively add columns introduced after a DB's first init (e.g.
# trips.settlement_mode, added for token-mode trips). This is the only
# migration mechanism the repo has - deliberately minimal, since ALTER TABLE
# ADD COLUMN can't add a CHECK constraint anyway (that lives in schema.sql for
# fresh DBs).
_COLUMN_MIGRATIONS = [
    ("trips", "settlement_mode", "settlement_mode TEXT NOT NULL CHECK (settlement_mode IN ('cash', 'token')) DEFAULT 'cash'"),
    ("trips", "token_address", "token_address TEXT"),
]


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db(db_path: Path) -> None:
    schema = SCHEMA_PATH.read_text()
    with get_connection(db_path) as conn:
        conn.executescript(schema)
        for table, column, ddl in _COLUMN_MIGRATIONS:
            _add_column_if_missing(conn, table, column, ddl)
