from __future__ import annotations

from fairsharebot.handlers.balance import balance_command
from fairsharebot.handlers.payment import pay_command
from fairsharebot.handlers.trip import start_trip_command


async def test_balance_without_open_trip(db_path, settings, update_factory, user_factory, chat_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, context = update_factory(user=user, chat=chat)
    context.bot_data["settings"] = settings

    await balance_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "no open trip" in reply.lower()


async def test_balance_with_no_payments(db_path, settings, update_factory, user_factory, chat_factory):
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)

    start_update, start_context = update_factory(user=alice, chat=chat, args=["Trip"])
    start_context.bot_data["settings"] = settings
    await start_trip_command(start_update, start_context)

    update, context = update_factory(user=alice, chat=chat)
    context.bot_data["settings"] = settings
    await balance_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "no payments" in reply.lower()


async def test_balance_shows_preview_settlement(db_path, settings, update_factory, user_factory, chat_factory):
    alice = user_factory(1, username="alice", first_name="Alice")
    bob = user_factory(2, username="bob", first_name="Bob")
    chat = chat_factory(100)

    start_update, start_context = update_factory(user=alice, chat=chat, args=["Trip"])
    start_context.bot_data["settings"] = settings
    await start_trip_command(start_update, start_context)

    pay_update, pay_context = update_factory(user=alice, chat=chat, text="/pay 10 coffee", reply_to_user=bob)
    pay_context.bot_data["settings"] = settings
    await pay_command(pay_update, pay_context)

    update, context = update_factory(user=alice, chat=chat)
    context.bot_data["settings"] = settings
    await balance_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "preview" in reply.lower()
    assert "bob pays alice 5.00" in reply.lower()


async def test_balance_reports_settled_when_all_zero(db_path, settings, update_factory, user_factory, chat_factory):
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)

    start_update, start_context = update_factory(user=alice, chat=chat, args=["Trip"])
    start_context.bot_data["settings"] = settings
    await start_trip_command(start_update, start_context)

    pay_update, pay_context = update_factory(user=alice, chat=chat, text="/pay 10 coffee")
    pay_context.bot_data["settings"] = settings
    await pay_command(pay_update, pay_context)

    update, context = update_factory(user=alice, chat=chat)
    context.bot_data["settings"] = settings
    await balance_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "settled up" in reply.lower()
    assert "preview" not in reply.lower()
