from __future__ import annotations

from fairsharebot.db.connection import get_connection
from fairsharebot.db.trips_repo import get_open_trip
from fairsharebot.handlers.payment import pay_command
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


async def test_close_trip_with_no_payments_skips_settlement(
    db_path, settings, update_factory, user_factory, chat_factory
):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)

    update1, context1 = update_factory(user=user, chat=chat, args=["Trip"])
    context1.bot_data["settings"] = settings
    await start_trip_command(update1, context1)

    update2, context2 = update_factory(user=user, chat=chat)
    context2.bot_data["settings"] = settings
    await close_trip_command(update2, context2)

    reply = update2.message.reply_text.call_args[0][0]
    assert "no payments" in reply.lower()


async def test_close_trip_posts_final_settlement(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice", first_name="Alice")
    bob = user_factory(2, username="bob", first_name="Bob")
    chat = chat_factory(100)

    update1, context1 = update_factory(user=alice, chat=chat, args=["Trip"])
    context1.bot_data["settings"] = settings
    await start_trip_command(update1, context1)

    pay_update, pay_context = update_factory(user=alice, chat=chat, text="/pay 10 coffee", reply_to_user=bob)
    pay_context.bot_data["settings"] = settings
    await pay_command(pay_update, pay_context)

    close_update, close_context = update_factory(user=alice, chat=chat)
    close_context.bot_data["settings"] = settings
    await close_trip_command(close_update, close_context)

    reply = close_update.message.reply_text.call_args[0][0]
    assert "final settlement" in reply.lower()
    assert "bob pays" in reply.lower()
    assert "5.00" in reply

    with get_connection(db_path) as conn:
        assert get_open_trip(conn, 100) is None


async def test_close_trip_already_settled_reports_no_transfers(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)

    update1, context1 = update_factory(user=alice, chat=chat, args=["Trip"])
    context1.bot_data["settings"] = settings
    await start_trip_command(update1, context1)

    pay_update, pay_context = update_factory(user=alice, chat=chat, text="/pay 10 coffee")
    pay_context.bot_data["settings"] = settings
    await pay_command(pay_update, pay_context)

    close_update, close_context = update_factory(user=alice, chat=chat)
    close_context.bot_data["settings"] = settings
    await close_trip_command(close_update, close_context)

    reply = close_update.message.reply_text.call_args[0][0]
    assert "no transfers needed" in reply.lower()
