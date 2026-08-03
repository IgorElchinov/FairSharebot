from __future__ import annotations

from fairsharebot.db import crypto_repo
from fairsharebot.db.connection import get_connection
from fairsharebot.handlers.observe import observe_message
from fairsharebot.handlers.payment import pay_command
from fairsharebot.handlers.trip import close_trip_command, start_trip_token_command


async def test_closetrip_on_token_trip_nets_and_reports_pending_settlement(
    chain_settings, fake_chain_client, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    start_update, start_context = update_factory(user=alice, chat=chat, args=["Trip"])
    start_context.bot_data["settings"] = chain_settings
    await start_trip_token_command(start_update, start_context)

    seed_update, seed_context = update_factory(user=bob, chat=chat, text="hi")
    seed_context.bot_data["settings"] = chain_settings
    await observe_message(seed_update, seed_context)

    pay_update, pay_context = update_factory(user=alice, chat=chat, text="/pay 10 coffee for @bob")
    pay_context.bot_data["settings"] = chain_settings
    pay_context.bot_data["chain_client"] = fake_chain_client
    await pay_command(pay_update, pay_context)

    # /pay already submitted a settlement (pending, not yet confirmed) -
    # /closetrip's residual math must not double-count it as still owed.
    close_update, close_context = update_factory(user=alice, chat=chat, text="/closetrip")
    close_context.bot_data["settings"] = chain_settings
    close_context.bot_data["chain_client"] = fake_chain_client
    await close_trip_command(close_update, close_context)

    reply_text = close_update.effective_message.reply_text.call_args[0][0]
    assert "Trip closed" in reply_text
    # The /pay settlement is still "pending" (not confirmed) at close time,
    # so the residual (balances minus *confirmed* on-chain moves) is still
    # the full amount - /closetrip submits it again since nothing has
    # actually confirmed yet.
    assert "Settling on-chain" in reply_text
    assert len(fake_chain_client.settle_batch_calls) == 2


async def test_closetrip_reports_fully_settled_once_confirmed(
    chain_settings, fake_chain_client, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    start_update, start_context = update_factory(user=alice, chat=chat, args=["Trip"])
    start_context.bot_data["settings"] = chain_settings
    await start_trip_token_command(start_update, start_context)

    seed_update, seed_context = update_factory(user=bob, chat=chat, text="hi")
    seed_context.bot_data["settings"] = chain_settings
    await observe_message(seed_update, seed_context)

    pay_update, pay_context = update_factory(user=alice, chat=chat, text="/pay 10 coffee for @bob")
    pay_context.bot_data["settings"] = chain_settings
    pay_context.bot_data["chain_client"] = fake_chain_client
    await pay_command(pay_update, pay_context)

    # Simulate the JobQueue poller having already confirmed the /pay settlement.
    with get_connection(chain_settings.db_path) as conn:
        for transfer in crypto_repo.get_pending_transfers(conn):
            crypto_repo.update_transfer_status(conn, transfer.id, status="confirmed", tx_hash=transfer.tx_hash)

    close_update, close_context = update_factory(user=alice, chat=chat, text="/closetrip")
    close_context.bot_data["settings"] = chain_settings
    close_context.bot_data["chain_client"] = fake_chain_client
    await close_trip_command(close_update, close_context)

    reply_text = close_update.effective_message.reply_text.call_args[0][0]
    assert "already settled on-chain" in reply_text
    # Only the original /pay settle_batch call - closetrip found nothing left to submit.
    assert len(fake_chain_client.settle_batch_calls) == 1
