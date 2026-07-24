from __future__ import annotations

from fairsharebot.db.connection import get_connection
from fairsharebot.db.trips_repo import get_open_trip
from fairsharebot.handlers.trip import close_trip_command, start_trip_command


async def test_start_trip_creates_open_trip(db_path, settings, update_factory, user_factory, chat_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, context = update_factory(user=user, chat=chat, args=["Ski", "trip"])
    context.bot_data["settings"] = settings

    await start_trip_command(update, context)

    update.message.reply_text.assert_awaited_once()
    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
    assert trip is not None
    assert trip.name == "Ski trip"


async def test_start_trip_uses_default_name_without_args(
    db_path, settings, update_factory, user_factory, chat_factory
):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, context = update_factory(user=user, chat=chat)
    context.bot_data["settings"] = settings

    await start_trip_command(update, context)

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
    assert trip is not None
    assert trip.name.startswith("Trip ")


async def test_start_trip_rejects_second_open_trip(
    db_path, settings, update_factory, user_factory, chat_factory
):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)

    update1, context1 = update_factory(user=user, chat=chat, args=["Trip", "A"])
    context1.bot_data["settings"] = settings
    await start_trip_command(update1, context1)

    update2, context2 = update_factory(user=user, chat=chat, args=["Trip", "B"])
    context2.bot_data["settings"] = settings
    await start_trip_command(update2, context2)

    reply = update2.message.reply_text.call_args[0][0]
    assert "already open" in reply.lower()


async def test_close_trip(db_path, settings, update_factory, user_factory, chat_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)

    update1, context1 = update_factory(user=user, chat=chat, args=["Trip"])
    context1.bot_data["settings"] = settings
    await start_trip_command(update1, context1)

    update2, context2 = update_factory(user=user, chat=chat)
    context2.bot_data["settings"] = settings
    await close_trip_command(update2, context2)

    update2.message.reply_text.assert_awaited_once()
    with get_connection(db_path) as conn:
        assert get_open_trip(conn, 100) is None


async def test_close_trip_without_open_trip(db_path, settings, update_factory, user_factory, chat_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, context = update_factory(user=user, chat=chat)
    context.bot_data["settings"] = settings

    await close_trip_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "no open trip" in reply.lower()
