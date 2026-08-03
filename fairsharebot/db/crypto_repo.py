from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ..models import CryptoTransfer, Wallet, WalletLinkChallenge


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_wallet(row: sqlite3.Row) -> Wallet:
    return Wallet(
        telegram_user_id=row["telegram_user_id"],
        address=row["address"],
        custody_type=row["custody_type"],
        allowance_granted_at=row["allowance_granted_at"],
        linked_at=row["linked_at"],
        updated_at=row["updated_at"],
    )


def _row_to_challenge(row: sqlite3.Row) -> WalletLinkChallenge:
    return WalletLinkChallenge(
        token=row["token"],
        telegram_user_id=row["telegram_user_id"],
        nonce=row["nonce"],
        status=row["status"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        verified_address=row["verified_address"],
    )


def _row_to_transfer(row: sqlite3.Row) -> CryptoTransfer:
    return CryptoTransfer(
        id=row["id"],
        trip_id=row["trip_id"],
        payment_id=row["payment_id"],
        from_user_id=row["from_user_id"],
        to_user_id=row["to_user_id"],
        from_address=row["from_address"],
        to_address=row["to_address"],
        token_amount=int(row["token_amount"]),
        tx_hash=row["tx_hash"],
        status=row["status"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        confirmed_at=row["confirmed_at"],
    )


def get_wallet(conn: sqlite3.Connection, user_id: int) -> Wallet | None:
    row = conn.execute(
        "SELECT * FROM wallets WHERE telegram_user_id = ?", (user_id,)
    ).fetchone()
    return _row_to_wallet(row) if row else None


def allocate_derivation_index(conn: sqlite3.Connection) -> int:
    """Next sequential custodial-wallet derivation index, not derived from
    telegram_user_id - keeps index allocation independent of user identity so
    a retired/exported index is never implicitly reused."""
    row = conn.execute("SELECT MAX(derivation_index) AS max_index FROM custodial_wallets").fetchone()
    max_index = row["max_index"]
    return (max_index + 1) if max_index is not None else 0


def insert_custodial_wallet(
    conn: sqlite3.Connection, *, user_id: int, derivation_index: int, address: str
) -> None:
    conn.execute(
        """
        INSERT INTO custodial_wallets (telegram_user_id, derivation_index, address, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, derivation_index, address, _now()),
    )


def get_custodial_wallet(conn: sqlite3.Connection, user_id: int) -> tuple[int, str] | None:
    """Returns (derivation_index, address) for the user's most recently
    derived custodial wallet, even if they've since switched their active
    wallet to an external one via /linkwallet."""
    row = conn.execute(
        """
        SELECT derivation_index, address FROM custodial_wallets
        WHERE telegram_user_id = ?
        ORDER BY derivation_index DESC
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    return (row["derivation_index"], row["address"]) if row else None


def upsert_wallet(conn: sqlite3.Connection, *, user_id: int, address: str, custody_type: str) -> Wallet:
    """Sets a user's active wallet. Switching address always resets
    allowance_granted_at to NULL - a new address has no standing allowance on
    the Settlement contract yet, regardless of what the previous one had."""
    now = _now()
    conn.execute(
        """
        INSERT INTO wallets (telegram_user_id, address, custody_type, allowance_granted_at, linked_at, updated_at)
        VALUES (?, ?, ?, NULL, ?, ?)
        ON CONFLICT(telegram_user_id) DO UPDATE SET
            address = excluded.address,
            custody_type = excluded.custody_type,
            allowance_granted_at = NULL,
            updated_at = excluded.updated_at
        """,
        (user_id, address, custody_type, now, now),
    )
    return get_wallet(conn, user_id)  # type: ignore[return-value]


def mark_allowance_granted(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute(
        "UPDATE wallets SET allowance_granted_at = ?, updated_at = ? WHERE telegram_user_id = ?",
        (_now(), _now(), user_id),
    )


def create_challenge(
    conn: sqlite3.Connection, *, token: str, user_id: int, nonce: str, expires_at: str
) -> WalletLinkChallenge:
    now = _now()
    conn.execute(
        """
        INSERT INTO wallet_link_challenges (token, telegram_user_id, nonce, status, created_at, expires_at)
        VALUES (?, ?, ?, 'pending', ?, ?)
        """,
        (token, user_id, nonce, now, expires_at),
    )
    row = conn.execute("SELECT * FROM wallet_link_challenges WHERE token = ?", (token,)).fetchone()
    return _row_to_challenge(row)


def get_challenge(conn: sqlite3.Connection, token: str) -> WalletLinkChallenge | None:
    row = conn.execute("SELECT * FROM wallet_link_challenges WHERE token = ?", (token,)).fetchone()
    return _row_to_challenge(row) if row else None


def mark_challenge_verified(conn: sqlite3.Connection, *, token: str, verified_address: str) -> WalletLinkChallenge:
    conn.execute(
        "UPDATE wallet_link_challenges SET status = 'verified', verified_address = ? WHERE token = ?",
        (verified_address, token),
    )
    return get_challenge(conn, token)  # type: ignore[return-value]


def record_transfer_attempt(
    conn: sqlite3.Connection,
    *,
    trip_id: int,
    payment_id: int | None,
    from_user_id: int,
    to_user_id: int,
    from_address: str,
    to_address: str,
    token_amount: int,
    tx_hash: str | None,
    status: str,
    error_message: str | None = None,
) -> CryptoTransfer:
    cursor = conn.execute(
        """
        INSERT INTO crypto_transfers
            (trip_id, payment_id, from_user_id, to_user_id, from_address, to_address,
             token_amount, tx_hash, status, error_message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trip_id,
            payment_id,
            from_user_id,
            to_user_id,
            from_address,
            to_address,
            str(token_amount),
            tx_hash,
            status,
            error_message,
            _now(),
        ),
    )
    row = conn.execute("SELECT * FROM crypto_transfers WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row_to_transfer(row)


def update_transfer_status(
    conn: sqlite3.Connection,
    transfer_id: int,
    *,
    status: str,
    tx_hash: str | None = None,
    error_message: str | None = None,
) -> CryptoTransfer:
    confirmed_at = _now() if status == "confirmed" else None
    conn.execute(
        """
        UPDATE crypto_transfers
        SET status = ?, tx_hash = COALESCE(?, tx_hash), error_message = ?, confirmed_at = ?
        WHERE id = ?
        """,
        (status, tx_hash, error_message, confirmed_at, transfer_id),
    )
    row = conn.execute("SELECT * FROM crypto_transfers WHERE id = ?", (transfer_id,)).fetchone()
    return _row_to_transfer(row)


def get_pending_transfers(conn: sqlite3.Connection) -> list[CryptoTransfer]:
    rows = conn.execute("SELECT * FROM crypto_transfers WHERE status = 'pending' ORDER BY id").fetchall()
    return [_row_to_transfer(row) for row in rows]


def get_confirmed_transfers_for_trip(conn: sqlite3.Connection, trip_id: int) -> list[CryptoTransfer]:
    rows = conn.execute(
        "SELECT * FROM crypto_transfers WHERE trip_id = ? AND status = 'confirmed' ORDER BY id",
        (trip_id,),
    ).fetchall()
    return [_row_to_transfer(row) for row in rows]
