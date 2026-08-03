from __future__ import annotations

from fairsharebot.chain.settlement_service import NO_ALLOWANCE_ERROR, run_closing_settlement
from fairsharebot.chain.units import cents_to_token_units
from fairsharebot.db import crypto_repo, trips_repo, users_repo
from fairsharebot.db.connection import get_connection

MNEMONIC = "test test test test test test test test test test test junk"


def _make_users(conn, *user_ids: int) -> None:
    for uid in user_ids:
        users_repo.upsert_user(conn, user_id=uid, username=f"user{uid}", display_name=f"User {uid}")


def _make_trip(conn, creator_id: int) -> int:
    trip = trips_repo.create_trip(conn, chat_id=1, name="Trip", created_by=creator_id, settlement_mode="token")
    return trip.id


async def test_full_residual_settled_when_nothing_confirmed_yet(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        _make_users(conn, 1, 2)
        trip_id = _make_trip(conn, 1)

        result = await run_closing_settlement(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC,
            trip_id=trip_id, balances={1: 1000, 2: -1000},
        )

    assert len(result.submitted) == 1
    assert result.submitted[0].from_user_id == 2
    assert result.submitted[0].to_user_id == 1
    assert result.submitted[0].amount_cents == 1000
    assert result.failed == []
    assert len(fake_chain_client.settle_batch_calls) == 1


async def test_already_confirmed_amount_is_excluded_from_residual(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        _make_users(conn, 1, 2)
        trip_id = _make_trip(conn, 1)

        # 600 of the 1000 owed already confirmed on-chain earlier (e.g. from
        # an immediate /pay settlement mid-trip).
        confirmed = crypto_repo.record_transfer_attempt(
            conn, trip_id=trip_id, payment_id=None, from_user_id=2, to_user_id=1,
            from_address="0xB", to_address="0xA", token_amount=cents_to_token_units(600),
            tx_hash="0xabc", status="pending",
        )
        crypto_repo.update_transfer_status(conn, confirmed.id, status="confirmed", tx_hash="0xabc")

        result = await run_closing_settlement(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC,
            trip_id=trip_id, balances={1: 1000, 2: -1000},
        )

    assert len(result.submitted) == 1
    assert result.submitted[0].amount_cents == 400
    assert len(fake_chain_client.settle_batch_calls) == 1
    submitted_batch = fake_chain_client.settle_batch_calls[0]
    assert submitted_batch[0][2] == cents_to_token_units(400)


async def test_fully_confirmed_leaves_nothing_to_submit(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        _make_users(conn, 1, 2)
        trip_id = _make_trip(conn, 1)

        confirmed = crypto_repo.record_transfer_attempt(
            conn, trip_id=trip_id, payment_id=None, from_user_id=2, to_user_id=1,
            from_address="0xB", to_address="0xA", token_amount=cents_to_token_units(1000),
            tx_hash="0xabc", status="pending",
        )
        crypto_repo.update_transfer_status(conn, confirmed.id, status="confirmed", tx_hash="0xabc")

        result = await run_closing_settlement(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC,
            trip_id=trip_id, balances={1: 1000, 2: -1000},
        )

    assert result.submitted == []
    assert result.failed == []
    assert fake_chain_client.settle_batch_calls == []


async def test_failed_prior_attempt_does_not_reduce_residual(db_path, chain_settings, fake_chain_client):
    """A 'failed' crypto_transfers row means nothing actually moved - the
    full amount must still be in the residual, unlike a confirmed one."""
    with get_connection(db_path) as conn:
        _make_users(conn, 1, 2)
        trip_id = _make_trip(conn, 1)

        crypto_repo.record_transfer_attempt(
            conn, trip_id=trip_id, payment_id=None, from_user_id=2, to_user_id=1,
            from_address="0xB", to_address="0xA", token_amount=cents_to_token_units(1000),
            tx_hash=None, status="failed", error_message="boom",
        )

        result = await run_closing_settlement(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC,
            trip_id=trip_id, balances={1: 1000, 2: -1000},
        )

    assert len(result.submitted) == 1
    assert result.submitted[0].amount_cents == 1000


async def test_participant_without_allowance_lands_in_failed_not_submitted(
    db_path, chain_settings, fake_chain_client
):
    with get_connection(db_path) as conn:
        _make_users(conn, 1, 2)
        trip_id = _make_trip(conn, 1)
        crypto_repo.upsert_wallet(conn, user_id=2, address="0xExternalNoAllowance", custody_type="external")

        result = await run_closing_settlement(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC,
            trip_id=trip_id, balances={1: 1000, 2: -1000},
        )

        failed_rows = [
            row for row in conn.execute("SELECT * FROM crypto_transfers WHERE trip_id = ?", (trip_id,)).fetchall()
        ]

    assert result.submitted == []
    assert len(result.failed) == 1
    assert result.failed[0].from_user_id == 2
    assert len(failed_rows) == 1
    assert failed_rows[0]["error_message"] == NO_ALLOWANCE_ERROR


async def test_no_transfers_needed_when_everyone_is_settled(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        _make_users(conn, 1, 2)
        trip_id = _make_trip(conn, 1)

        result = await run_closing_settlement(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC,
            trip_id=trip_id, balances={1: 0, 2: 0},
        )

    assert result.submitted == []
    assert result.failed == []
    assert fake_chain_client.settle_batch_calls == []
