from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ..errors import PaymentNotFoundError
from ..models import Payment, PaymentSplit, SplitInput


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_payment(row: sqlite3.Row) -> Payment:
    return Payment(
        id=row["id"],
        trip_id=row["trip_id"],
        payer_id=row["payer_id"],
        amount_cents=row["amount_cents"],
        description=row["description"],
        split_type=row["split_type"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def _row_to_split(row: sqlite3.Row) -> PaymentSplit:
    return PaymentSplit(
        id=row["id"],
        payment_id=row["payment_id"],
        user_id=row["user_id"],
        weight=row["weight"],
        computed_amount_cents=row["computed_amount_cents"],
    )


def add_payment(
    conn: sqlite3.Connection,
    *,
    trip_id: int,
    payer_id: int,
    amount_cents: int,
    description: str,
    split_type: str,
    created_by: int,
) -> Payment:
    cursor = conn.execute(
        """
        INSERT INTO payments
            (trip_id, payer_id, amount_cents, description, split_type, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (trip_id, payer_id, amount_cents, description, split_type, created_by, _now()),
    )
    row = conn.execute("SELECT * FROM payments WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row_to_payment(row)


def add_splits(conn: sqlite3.Connection, *, payment_id: int, splits: list[SplitInput]) -> None:
    conn.executemany(
        """
        INSERT INTO payment_splits (payment_id, user_id, weight, computed_amount_cents)
        VALUES (?, ?, ?, ?)
        """,
        [(payment_id, split.user_id, split.weight, split.computed_amount_cents) for split in splits],
    )


def get_payment(conn: sqlite3.Connection, payment_id: int) -> Payment | None:
    row = conn.execute(
        "SELECT * FROM payments WHERE id = ? AND deleted_at IS NULL",
        (payment_id,),
    ).fetchone()
    return _row_to_payment(row) if row else None


def cancel_payment(conn: sqlite3.Connection, payment_id: int) -> Payment:
    payment = get_payment(conn, payment_id)
    if payment is None:
        raise PaymentNotFoundError(payment_id)
    conn.execute("UPDATE payments SET deleted_at = ? WHERE id = ?", (_now(), payment_id))
    return payment


def get_trip_payments(conn: sqlite3.Connection, trip_id: int) -> list[Payment]:
    rows = conn.execute(
        "SELECT * FROM payments WHERE trip_id = ? AND deleted_at IS NULL ORDER BY id",
        (trip_id,),
    ).fetchall()
    return [_row_to_payment(row) for row in rows]


def get_trip_splits(conn: sqlite3.Connection, trip_id: int) -> list[PaymentSplit]:
    rows = conn.execute(
        """
        SELECT ps.*
        FROM payment_splits ps
        JOIN payments p ON p.id = ps.payment_id
        WHERE p.trip_id = ? AND p.deleted_at IS NULL
        ORDER BY ps.id
        """,
        (trip_id,),
    ).fetchall()
    return [_row_to_split(row) for row in rows]
