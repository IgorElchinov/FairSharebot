from __future__ import annotations

from fairsharebot.db.connection import get_connection
from fairsharebot.db.trips_repo import get_open_trip
from fairsharebot.handlers.payment import pay_command
from fairsharebot.handlers.trip import (
    close_trip_command,
    list_trips_command,
    start_trip_command,
    trip_detail_command,
)


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


async def test_list_trips_empty(db_path, settings, update_factory, user_factory, chat_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, context = update_factory(user=user, chat=chat)
    context.bot_data["settings"] = settings

    await list_trips_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "no trips yet" in reply.lower()


async def test_list_trips_shows_open_and_closed_with_totals(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice", first_name="Alice")
    chat = chat_factory(100)

    start1, ctx1 = update_factory(user=alice, chat=chat, args=["Trip", "A"])
    ctx1.bot_data["settings"] = settings
    await start_trip_command(start1, ctx1)

    pay1, pay_ctx1 = update_factory(user=alice, chat=chat, text="/pay 15 lunch")
    pay_ctx1.bot_data["settings"] = settings
    await pay_command(pay1, pay_ctx1)

    close1, close_ctx1 = update_factory(user=alice, chat=chat)
    close_ctx1.bot_data["settings"] = settings
    await close_trip_command(close1, close_ctx1)

    start2, ctx2 = update_factory(user=alice, chat=chat, args=["Trip", "B"])
    ctx2.bot_data["settings"] = settings
    await start_trip_command(start2, ctx2)

    update, context = update_factory(user=alice, chat=chat)
    context.bot_data["settings"] = settings
    await list_trips_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "trip a" in reply.lower()
    assert "trip b" in reply.lower()
    assert "closed" in reply.lower()
    assert "open" in reply.lower()
    assert "15.00" in reply


async def test_trip_detail_requires_valid_id(db_path, settings, update_factory, user_factory, chat_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, context = update_factory(user=user, chat=chat, args=["notanid"])
    context.bot_data["settings"] = settings

    await trip_detail_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "usage" in reply.lower()


async def test_trip_detail_not_found(db_path, settings, update_factory, user_factory, chat_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, context = update_factory(user=user, chat=chat, args=["999"])
    context.bot_data["settings"] = settings

    await trip_detail_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "no trip #999" in reply.lower()


async def test_trip_detail_shows_breakdown_and_settlement(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice", first_name="Alice")
    bob = user_factory(2, username="bob", first_name="Bob")
    chat = chat_factory(100)

    start_update, start_context = update_factory(user=alice, chat=chat, args=["Trip"])
    start_context.bot_data["settings"] = settings
    await start_trip_command(start_update, start_context)

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)

    pay_update, pay_context = update_factory(user=alice, chat=chat, text="/pay 10 coffee", reply_to_user=bob)
    pay_context.bot_data["settings"] = settings
    await pay_command(pay_update, pay_context)

    close_update, close_context = update_factory(user=alice, chat=chat)
    close_context.bot_data["settings"] = settings
    await close_trip_command(close_update, close_context)

    update, context = update_factory(user=alice, chat=chat, args=[str(trip.id)])
    context.bot_data["settings"] = settings
    await trip_detail_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert f"trip #{trip.id}" in reply.lower()
    assert "alice paid 10.00 for coffee" in reply.lower()
    assert "bob pays alice 5.00" in reply.lower()


async def test_trip_detail_isolated_to_chat(db_path, settings, update_factory, user_factory, chat_factory):
    alice = user_factory(1, username="alice")
    chat_a = chat_factory(100)
    chat_b = chat_factory(200)

    start_update, start_context = update_factory(user=alice, chat=chat_a, args=["Trip A"])
    start_context.bot_data["settings"] = settings
    await start_trip_command(start_update, start_context)

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)

    update, context = update_factory(user=alice, chat=chat_b, args=[str(trip.id)])
    context.bot_data["settings"] = settings
    await trip_detail_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert f"no trip #{trip.id}" in reply.lower()
