from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ..errors import NoOpenTripError, TripAlreadyOpenError
from ..models import Trip


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_trip(row: sqlite3.Row) -> Trip:
    return Trip(
        id=row["id"],
        chat_id=row["chat_id"],
        name=row["name"],
        status=row["status"],
        currency=row["currency"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        closed_at=row["closed_at"],
    )


def get_open_trip(conn: sqlite3.Connection, chat_id: int) -> Trip | None:
    row = conn.execute(
        "SELECT * FROM trips WHERE chat_id = ? AND status = 'open'",
        (chat_id,),
    ).fetchone()
    return _row_to_trip(row) if row else None


def get_trip(conn: sqlite3.Connection, trip_id: int) -> Trip | None:
    row = conn.execute("SELECT * FROM trips WHERE id = ?", (trip_id,)).fetchone()
    return _row_to_trip(row) if row else None


def create_trip(conn: sqlite3.Connection, *, chat_id: int, name: str, created_by: int) -> Trip:
    if get_open_trip(conn, chat_id) is not None:
        raise TripAlreadyOpenError(chat_id)

    cursor = conn.execute(
        "INSERT INTO trips (chat_id, name, created_by, created_at) VALUES (?, ?, ?, ?)",
        (chat_id, name, created_by, _now()),
    )
    trip = get_trip(conn, cursor.lastrowid)
    assert trip is not None
    return trip


def close_trip(conn: sqlite3.Connection, chat_id: int) -> Trip:
    trip = get_open_trip(conn, chat_id)
    if trip is None:
        raise NoOpenTripError(chat_id)

    conn.execute(
        "UPDATE trips SET status = 'closed', closed_at = ? WHERE id = ?",
        (_now(), trip.id),
    )
    updated = get_trip(conn, trip.id)
    assert updated is not None
    return updated


def list_trips(conn: sqlite3.Connection, chat_id: int) -> list[Trip]:
    rows = conn.execute(
        "SELECT * FROM trips WHERE chat_id = ? ORDER BY id DESC",
        (chat_id,),
    ).fetchall()
    return [_row_to_trip(row) for row in rows]


def list_trips_with_totals(conn: sqlite3.Connection, chat_id: int) -> list[tuple[Trip, int]]:
    rows = conn.execute(
        """
        SELECT t.*, COALESCE(SUM(p.amount_cents), 0) AS total_cents
        FROM trips t
        LEFT JOIN payments p ON p.trip_id = t.id AND p.deleted_at IS NULL
        WHERE t.chat_id = ?
        GROUP BY t.id
        ORDER BY t.id DESC
        """,
        (chat_id,),
    ).fetchall()
    return [(_row_to_trip(row), row["total_cents"]) for row in rows]
