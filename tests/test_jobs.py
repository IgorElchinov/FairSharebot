from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from eth_account import Account

from fairsharebot.db import crypto_repo, trips_repo, users_repo
from fairsharebot.db.connection import get_connection
from fairsharebot.handlers.jobs import (
    LOW_GAS_BALANCE_WEI,
    PENDING_TIMEOUT_SECONDS,
    poll_pending_transfers,
    poll_relayer_gas_balance,
)


def _make_trip_and_users(conn):
    users_repo.upsert_user(conn, user_id=1, username="alice", display_name="Alice")
    users_repo.upsert_user(conn, user_id=2, username="bob", display_name="Bob")
    trip = trips_repo.create_trip(conn, chat_id=1, name="Trip", created_by=1, settlement_mode="token")
    return trip


def _make_context(settings, chain_client):
    return SimpleNamespace(bot_data={"settings": settings, "chain_client": chain_client})


async def test_poll_does_nothing_when_chain_not_configured(settings, fake_chain_client):
    context = _make_context(settings, fake_chain_client)
    # Should not raise even though settings.chain is None.
    await poll_pending_transfers(context)


async def test_poll_confirms_a_settled_transfer(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        trip = _make_trip_and_users(conn)
        transfer = crypto_repo.record_transfer_attempt(
            conn, trip_id=trip.id, payment_id=None, from_user_id=2, to_user_id=1,
            from_address="0xA", to_address="0xB", token_amount=10, tx_hash="0xabc", status="pending",
        )
    fake_chain_client.receipt_statuses["0xabc"] = "confirmed"

    context = _make_context(chain_settings, fake_chain_client)
    await poll_pending_transfers(context)

    with get_connection(db_path) as conn:
        remaining_pending = crypto_repo.get_pending_transfers(conn)
        confirmed = crypto_repo.get_confirmed_transfers_for_trip(conn, trip.id)

    assert remaining_pending == []
    assert [t.id for t in confirmed] == [transfer.id]


async def test_poll_marks_a_failed_receipt_as_failed(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        trip = _make_trip_and_users(conn)
        crypto_repo.record_transfer_attempt(
            conn, trip_id=trip.id, payment_id=None, from_user_id=2, to_user_id=1,
            from_address="0xA", to_address="0xB", token_amount=10, tx_hash="0xdead", status="pending",
        )
    fake_chain_client.receipt_statuses["0xdead"] = "failed"

    context = _make_context(chain_settings, fake_chain_client)
    await poll_pending_transfers(context)

    with get_connection(db_path) as conn:
        assert crypto_repo.get_pending_transfers(conn) == []


async def test_poll_leaves_still_pending_transfer_alone(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        trip = _make_trip_and_users(conn)
        transfer = crypto_repo.record_transfer_attempt(
            conn, trip_id=trip.id, payment_id=None, from_user_id=2, to_user_id=1,
            from_address="0xA", to_address="0xB", token_amount=10, tx_hash="0xpending", status="pending",
        )
    # No receipt_statuses entry -> get_receipt_status returns None (not yet mined).

    context = _make_context(chain_settings, fake_chain_client)
    await poll_pending_transfers(context)

    with get_connection(db_path) as conn:
        still_pending = crypto_repo.get_pending_transfers(conn)

    assert [t.id for t in still_pending] == [transfer.id]


async def test_poll_times_out_a_stale_pending_transfer(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        trip = _make_trip_and_users(conn)
        transfer = crypto_repo.record_transfer_attempt(
            conn, trip_id=trip.id, payment_id=None, from_user_id=2, to_user_id=1,
            from_address="0xA", to_address="0xB", token_amount=10, tx_hash="0xstale", status="pending",
        )
        # Backdate created_at past the timeout, simulating a stuck mempool tx.
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=PENDING_TIMEOUT_SECONDS + 60)).isoformat()
        conn.execute("UPDATE crypto_transfers SET created_at = ? WHERE id = ?", (stale_time, transfer.id))

    context = _make_context(chain_settings, fake_chain_client)
    await poll_pending_transfers(context)

    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM crypto_transfers WHERE id = ?", (transfer.id,)).fetchone()

    assert row["status"] == "failed"
    assert "timed out" in row["error_message"]


def _make_context_with_bot(settings, chain_client):
    return SimpleNamespace(bot_data={"settings": settings, "chain_client": chain_client}, bot=AsyncMock())


async def test_gas_poll_does_nothing_when_chain_not_configured(settings, fake_chain_client):
    context = _make_context_with_bot(settings, fake_chain_client)
    await poll_relayer_gas_balance(context)
    context.bot.send_message.assert_not_called()


async def test_gas_poll_alerts_operator_when_balance_low(chain_settings, fake_chain_client):
    relayer_address = Account.from_key(chain_settings.chain.relayer_private_key).address
    fake_chain_client.native_balances[relayer_address] = LOW_GAS_BALANCE_WEI - 1

    context = _make_context_with_bot(chain_settings, fake_chain_client)
    await poll_relayer_gas_balance(context)

    context.bot.send_message.assert_awaited_once()
    kwargs = context.bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == chain_settings.chain.owner_telegram_user_id
    assert relayer_address in kwargs["text"]


async def test_gas_poll_does_not_alert_when_balance_healthy(chain_settings, fake_chain_client):
    relayer_address = Account.from_key(chain_settings.chain.relayer_private_key).address
    fake_chain_client.native_balances[relayer_address] = LOW_GAS_BALANCE_WEI * 100

    context = _make_context_with_bot(chain_settings, fake_chain_client)
    await poll_relayer_gas_balance(context)

    context.bot.send_message.assert_not_called()
