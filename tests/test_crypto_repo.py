from __future__ import annotations

from fairsharebot.db import crypto_repo, trips_repo, users_repo
from fairsharebot.db.connection import get_connection


def _make_user(conn, user_id: int) -> None:
    users_repo.upsert_user(conn, user_id=user_id, username=f"user{user_id}", display_name=f"User {user_id}")


def test_upsert_wallet_creates_then_updates_and_resets_allowance(db_path):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        wallet = crypto_repo.upsert_wallet(conn, user_id=1, address="0xAAA", custody_type="custodial")
        assert wallet.address == "0xAAA"
        assert wallet.allowance_granted_at is None

        crypto_repo.mark_allowance_granted(conn, 1)
        granted = crypto_repo.get_wallet(conn, 1)
        assert granted.allowance_granted_at is not None

        # Switching address (e.g. via /linkwallet) must reset the allowance
        # flag - the new address has no standing allowance yet.
        switched = crypto_repo.upsert_wallet(conn, user_id=1, address="0xBBB", custody_type="external")
        assert switched.address == "0xBBB"
        assert switched.custody_type == "external"
        assert switched.allowance_granted_at is None


def test_get_wallet_returns_none_when_absent(db_path):
    with get_connection(db_path) as conn:
        assert crypto_repo.get_wallet(conn, 999) is None


def test_wallet_link_challenge_lifecycle(db_path):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        challenge = crypto_repo.create_challenge(
            conn, token="tok123", user_id=1, nonce="sign-this", expires_at="2099-01-01T00:00:00+00:00"
        )
        assert challenge.status == "pending"

        fetched = crypto_repo.get_challenge(conn, "tok123")
        assert fetched == challenge

        verified = crypto_repo.mark_challenge_verified(conn, token="tok123", verified_address="0xCCC")
        assert verified.status == "verified"
        assert verified.verified_address == "0xCCC"


def test_get_challenge_returns_none_for_unknown_token(db_path):
    with get_connection(db_path) as conn:
        assert crypto_repo.get_challenge(conn, "nope") is None


def _make_trip(conn, chat_id: int, creator_id: int) -> int:
    _make_user(conn, creator_id)
    trip = trips_repo.create_trip(conn, chat_id=chat_id, name="Test trip", created_by=creator_id)
    return trip.id


def test_record_and_update_transfer_attempt_round_trips_large_token_amount(db_path):
    with get_connection(db_path) as conn:
        trip_id = _make_trip(conn, chat_id=1, creator_id=1)
        _make_user(conn, 2)

        # 18-decimal amount that would overflow a naive float/REAL round-trip.
        big_amount = 123_456_789_012_345_678_901_234
        transfer = crypto_repo.record_transfer_attempt(
            conn,
            trip_id=trip_id,
            payment_id=None,
            from_user_id=1,
            to_user_id=2,
            from_address="0xFrom",
            to_address="0xTo",
            token_amount=big_amount,
            tx_hash=None,
            status="pending",
        )
        assert transfer.token_amount == big_amount
        assert transfer.status == "pending"

        updated = crypto_repo.update_transfer_status(
            conn, transfer.id, status="confirmed", tx_hash="0xdeadbeef"
        )
        assert updated.status == "confirmed"
        assert updated.tx_hash == "0xdeadbeef"
        assert updated.confirmed_at is not None


def test_get_pending_transfers_excludes_confirmed_and_failed(db_path):
    with get_connection(db_path) as conn:
        trip_id = _make_trip(conn, chat_id=1, creator_id=1)
        _make_user(conn, 2)

        pending = crypto_repo.record_transfer_attempt(
            conn, trip_id=trip_id, payment_id=None, from_user_id=1, to_user_id=2,
            from_address="0xA", to_address="0xB", token_amount=1, tx_hash="0x1", status="pending",
        )
        confirmed = crypto_repo.record_transfer_attempt(
            conn, trip_id=trip_id, payment_id=None, from_user_id=1, to_user_id=2,
            from_address="0xA", to_address="0xB", token_amount=2, tx_hash="0x2", status="pending",
        )
        crypto_repo.update_transfer_status(conn, confirmed.id, status="confirmed", tx_hash="0x2")
        crypto_repo.record_transfer_attempt(
            conn, trip_id=trip_id, payment_id=None, from_user_id=1, to_user_id=2,
            from_address="0xA", to_address="0xB", token_amount=3, tx_hash=None, status="failed",
            error_message="boom",
        )

        still_pending = crypto_repo.get_pending_transfers(conn)

    assert [t.id for t in still_pending] == [pending.id]


def test_get_confirmed_transfers_for_trip_scopes_by_trip(db_path):
    with get_connection(db_path) as conn:
        trip_a = _make_trip(conn, chat_id=1, creator_id=1)
        trip_b = _make_trip(conn, chat_id=2, creator_id=1)
        _make_user(conn, 2)

        t1 = crypto_repo.record_transfer_attempt(
            conn, trip_id=trip_a, payment_id=None, from_user_id=1, to_user_id=2,
            from_address="0xA", to_address="0xB", token_amount=10, tx_hash="0x1", status="pending",
        )
        crypto_repo.update_transfer_status(conn, t1.id, status="confirmed", tx_hash="0x1")

        t2 = crypto_repo.record_transfer_attempt(
            conn, trip_id=trip_b, payment_id=None, from_user_id=1, to_user_id=2,
            from_address="0xA", to_address="0xB", token_amount=20, tx_hash="0x2", status="pending",
        )
        crypto_repo.update_transfer_status(conn, t2.id, status="confirmed", tx_hash="0x2")

        trip_a_confirmed = crypto_repo.get_confirmed_transfers_for_trip(conn, trip_a)

    assert [t.id for t in trip_a_confirmed] == [t1.id]
