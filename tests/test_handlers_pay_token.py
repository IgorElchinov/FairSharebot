from __future__ import annotations

from fairsharebot.db import crypto_repo
from fairsharebot.db.connection import get_connection
from fairsharebot.db.trips_repo import get_open_trip
from fairsharebot.handlers.observe import observe_message
from fairsharebot.handlers.payment import pay_command
from fairsharebot.handlers.trip import start_trip_token_command


async def _start_token_trip(chain_settings, update_factory, user, chat):
    update, context = update_factory(user=user, chat=chat, args=["Trip"])
    context.bot_data["settings"] = chain_settings
    await start_trip_token_command(update, context)


async def test_pay_on_token_trip_settles_immediately_on_chain(
    chain_settings, fake_chain_client, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    await _start_token_trip(chain_settings, update_factory, alice, chat)

    seed_update, seed_context = update_factory(user=bob, chat=chat, text="hi")
    seed_context.bot_data["settings"] = chain_settings
    await observe_message(seed_update, seed_context)

    update, context = update_factory(user=alice, chat=chat, text="/pay 10 coffee for @bob")
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    await pay_command(update, context)

    with get_connection(chain_settings.db_path) as conn:
        trip = get_open_trip(conn, 100)
        pending = crypto_repo.get_pending_transfers(conn)
        payer_wallet = crypto_repo.get_wallet(conn, 1)
        bob_wallet = crypto_repo.get_wallet(conn, 2)

    assert trip.settlement_mode == "token"
    # bob owes half of 10 = 5.00 -> 5 * 10**18 base units
    assert len(pending) == 1
    assert pending[0].from_user_id == 2
    assert pending[0].to_user_id == 1
    assert pending[0].token_amount == 5 * 10**18
    assert len(fake_chain_client.settle_batch_calls) == 1
    assert payer_wallet is not None
    assert bob_wallet is not None
    assert bob_wallet.allowance_granted_at is not None

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "Recorded" in reply_text
    assert "error" not in reply_text.lower()


async def test_pay_on_cash_trip_never_touches_chain_layer(
    settings, fake_chain_client, update_factory, user_factory, chat_factory
):
    """Regression guard: a cash-mode trip must not call the chain client at
    all, even if one happens to be present in bot_data."""
    from fairsharebot.handlers.trip import start_trip_command

    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    update0, context0 = update_factory(user=alice, chat=chat, args=["Trip"])
    context0.bot_data["settings"] = settings
    await start_trip_command(update0, context0)

    seed_update, seed_context = update_factory(user=bob, chat=chat, text="hi")
    seed_context.bot_data["settings"] = settings
    await observe_message(seed_update, seed_context)

    update, context = update_factory(user=alice, chat=chat, text="/pay 10 coffee for @bob")
    context.bot_data["settings"] = settings
    context.bot_data["chain_client"] = fake_chain_client

    await pay_command(update, context)

    assert fake_chain_client.settle_batch_calls == []
    assert fake_chain_client.permit_calls == []
    with get_connection(settings.db_path) as conn:
        assert crypto_repo.get_wallet(conn, 1) is None
        assert crypto_repo.get_wallet(conn, 2) is None


async def test_pay_on_token_trip_reports_note_when_settlement_raises_unexpectedly(
    chain_settings, fake_chain_client, update_factory, user_factory, chat_factory, monkeypatch
):
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    await _start_token_trip(chain_settings, update_factory, alice, chat)
    seed_update, seed_context = update_factory(user=bob, chat=chat, text="hi")
    seed_context.bot_data["settings"] = chain_settings
    await observe_message(seed_update, seed_context)

    import fairsharebot.handlers.payment as payment_module

    async def boom(*args, **kwargs):
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(payment_module, "settle_payment_onchain", boom)

    update, context = update_factory(user=alice, chat=chat, text="/pay 10 coffee for @bob")
    context.bot_data["settings"] = chain_settings
    context.bot_data["chain_client"] = fake_chain_client

    await pay_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "Recorded" in reply_text
    assert "/closetrip will retry" in reply_text

    with get_connection(chain_settings.db_path) as conn:
        trip = get_open_trip(conn, 100)
        payments = conn.execute("SELECT * FROM payments WHERE trip_id = ?", (trip.id,)).fetchall()
    assert len(payments) == 1
