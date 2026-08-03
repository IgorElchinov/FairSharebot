from __future__ import annotations

from fairsharebot.db.connection import get_connection
from fairsharebot.db.trips_repo import get_open_trip
from fairsharebot.handlers.trip import start_trip_token_command


async def test_starttriptoken_refuses_when_chain_not_configured(
    settings, user_factory, chat_factory, update_factory
):
    user = user_factory(1, username="alice")
    update, context = update_factory(user=user, chat=chat_factory(), args=["Ski", "trip"])
    context.bot_data["settings"] = settings

    await start_trip_token_command(update, context)

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "aren't configured" in reply_text
    with get_connection(settings.db_path) as conn:
        assert get_open_trip(conn, 100) is None


async def test_starttriptoken_creates_token_mode_trip(
    chain_settings, user_factory, chat_factory, update_factory
):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, context = update_factory(user=user, chat=chat, args=["Ski", "trip"])
    context.bot_data["settings"] = chain_settings

    await start_trip_token_command(update, context)

    with get_connection(chain_settings.db_path) as conn:
        trip = get_open_trip(conn, 100)

    assert trip is not None
    assert trip.settlement_mode == "token"
    assert trip.token_address == chain_settings.chain.token_address

    reply_text = update.effective_message.reply_text.call_args[0][0]
    assert "Token trip started" in reply_text


async def test_starttriptoken_rejects_second_open_trip(chain_settings, user_factory, chat_factory, update_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update1, context1 = update_factory(user=user, chat=chat, args=["Trip", "1"])
    context1.bot_data["settings"] = chain_settings
    await start_trip_token_command(update1, context1)

    update2, context2 = update_factory(user=user, chat=chat, args=["Trip", "2"])
    context2.bot_data["settings"] = chain_settings
    await start_trip_token_command(update2, context2)

    reply_text = update2.effective_message.reply_text.call_args[0][0]
    assert "already open" in reply_text
