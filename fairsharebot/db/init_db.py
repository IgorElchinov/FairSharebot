from __future__ import annotations

from pathlib import Path

from .connection import get_connection

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def init_db(db_path: Path) -> None:
    schema = SCHEMA_PATH.read_text()
    with get_connection(db_path) as conn:
        conn.executescript(schema)
