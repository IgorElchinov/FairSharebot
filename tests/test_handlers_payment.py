from __future__ import annotations

from fairsharebot.db.connection import get_connection
from fairsharebot.db.payments_repo import get_trip_payments, get_trip_splits
from fairsharebot.db.trips_repo import get_open_trip
from fairsharebot.handlers.payment import cancel_payment_command, pay_command
from fairsharebot.handlers.trip import start_trip_command
from fairsharebot.settlement import compute_balances


async def _start_trip(settings, update_factory, user, chat):
    update, context = update_factory(user=user, chat=chat, args=["Trip"])
    context.bot_data["settings"] = settings
    await start_trip_command(update, context)


async def test_pay_equal_split_between_sender_and_mention(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    # bob must be known to the bot before he can be @mentioned by username
    seed_update, seed_context = update_factory(user=bob, chat=chat, text="hi")
    seed_context.bot_data["settings"] = settings
    from fairsharebot.handlers.observe import observe_message

    await observe_message(seed_update, seed_context)

    update, context = update_factory(user=alice, chat=chat, text="/pay 10 coffee for @bob")
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    update.message.reply_text.assert_awaited_once()
    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        payments = get_trip_payments(conn, trip.id)
        splits = get_trip_splits(conn, trip.id)

    assert len(payments) == 1
    assert payments[0].amount_cents == 1000
    balances = compute_balances(payments, splits)
    assert balances == {1: 500, 2: -500}


async def test_pay_with_reply_to_no_for_keyword(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    update, context = update_factory(user=alice, chat=chat, text="/pay 10 coffee", reply_to_user=bob)
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        payments = get_trip_payments(conn, trip.id)
        splits = get_trip_splits(conn, trip.id)

    balances = compute_balances(payments, splits)
    assert balances == {1: 500, 2: -500}


async def test_pay_odd_amount_distributes_remainder_cents(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    carol = user_factory(3, username="carol")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    update, context = update_factory(
        user=alice, chat=chat, text="/pay 10 pizza for Bob Carol", mentioned_users=[bob, carol]
    )
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        splits = get_trip_splits(conn, trip.id)

    total = sum(split.computed_amount_cents for split in splits)
    assert total == 1000
    amounts = sorted(split.computed_amount_cents for split in splits)
    assert amounts == [333, 333, 334]


async def test_pay_unknown_username_does_not_persist(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    update, context = update_factory(user=alice, chat=chat, text="/pay 10 coffee for @ghost")
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "ghost" in reply.lower()

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        payments = get_trip_payments(conn, trip.id)

    assert payments == []


async def test_pay_without_open_trip(db_path, settings, update_factory, user_factory, chat_factory):
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, context = update_factory(user=alice, chat=chat, text="/pay 10 coffee")
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "no open trip" in reply.lower()


async def test_pay_invalid_amount(db_path, settings, update_factory, user_factory, chat_factory):
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    update, context = update_factory(user=alice, chat=chat, text="/pay notanumber coffee")
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "valid amount" in reply.lower()


async def _seed_user(settings, update_factory, chat, user):
    seed_update, seed_context = update_factory(user=user, chat=chat, text="hi")
    seed_context.bot_data["settings"] = settings
    from fairsharebot.handlers.observe import observe_message

    await observe_message(seed_update, seed_context)


async def test_pay_exact_split_persists_specified_amounts(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)
    await _seed_user(settings, update_factory, chat, bob)

    update, context = update_factory(
        user=alice, chat=chat, text="/pay 90 dinner split me=30 @bob=60"
    )
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    update.message.reply_text.assert_awaited_once()
    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        payments = get_trip_payments(conn, trip.id)
        splits = get_trip_splits(conn, trip.id)

    assert payments[0].split_type == "exact"
    balances = compute_balances(payments, splits)
    assert balances == {1: 6000, 2: -6000}


async def test_pay_exact_split_mismatched_sum_does_not_persist(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    update, context = update_factory(
        user=alice, chat=chat, text="/pay 90 dinner split me=30 @bob=30"
    )
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "add up to" in reply.lower()

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        payments = get_trip_payments(conn, trip.id)

    assert payments == []


async def test_pay_exact_split_unknown_user_does_not_persist(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    update, context = update_factory(
        user=alice, chat=chat, text="/pay 90 dinner split me=30 @ghost=60"
    )
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "ghost" in reply.lower()

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        payments = get_trip_payments(conn, trip.id)

    assert payments == []


async def test_pay_shares_split_persists_weighted_amounts(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)
    await _seed_user(settings, update_factory, chat, bob)

    update, context = update_factory(
        user=alice, chat=chat, text="/pay 90 rent shares me=1 @bob=2"
    )
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        payments = get_trip_payments(conn, trip.id)
        splits = get_trip_splits(conn, trip.id)

    assert payments[0].split_type == "shares"
    by_user = {s.user_id: s for s in splits}
    assert by_user[1].computed_amount_cents == 3000
    assert by_user[2].computed_amount_cents == 6000
    assert by_user[2].weight == 2.0


async def test_pay_exact_split_rejects_same_user_via_me_and_own_username(
    db_path, settings, update_factory, user_factory, chat_factory
):
    # alice's own username is "alice" - "me" and "@alice" both resolve to her.
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    update, context = update_factory(
        user=alice, chat=chat, text="/pay 90 dinner split me=30 @alice=30 @bob=30"
    )
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "more than once" in reply.lower()

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        payments = get_trip_payments(conn, trip.id)

    assert payments == []


async def test_pay_shares_split_rejects_same_user_via_me_and_own_username(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)
    await _seed_user(settings, update_factory, chat, bob)

    update, context = update_factory(
        user=alice, chat=chat, text="/pay 90 rent shares me=1 @alice=1 @bob=1"
    )
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "more than once" in reply.lower()


async def test_pay_equal_split_dedupes_mentioning_self(
    db_path, settings, update_factory, user_factory, chat_factory
):
    # Equal split resolves participants into a dict keyed by user id, so
    # mentioning yourself alongside others doesn't create a duplicate share -
    # unlike exact/shares splits, this never needed a fix.
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)
    await _seed_user(settings, update_factory, chat, bob)

    update, context = update_factory(user=alice, chat=chat, text="/pay 90 taxi for @alice @bob")
    context.bot_data["settings"] = settings

    await pay_command(update, context)

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        splits = get_trip_splits(conn, trip.id)

    assert len(splits) == 2
    assert sum(s.computed_amount_cents for s in splits) == 9000


async def test_pay_works_on_edited_message(db_path, settings, update_factory, user_factory, chat_factory):
    # update.message is None for edited-message updates - only
    # effective_message is populated. Handlers must use effective_message.
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    update, context = update_factory(user=alice, chat=chat, text="/pay 10 coffee", edited=True)
    context.bot_data["settings"] = settings

    assert update.message is None

    await pay_command(update, context)

    update.effective_message.reply_text.assert_awaited_once()
    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        payments = get_trip_payments(conn, trip.id)

    assert len(payments) == 1


async def test_cancel_payment_removes_it_from_balances(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    bob = user_factory(2, username="bob")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    pay_update, pay_context = update_factory(user=alice, chat=chat, text="/pay 10 coffee", reply_to_user=bob)
    pay_context.bot_data["settings"] = settings
    await pay_command(pay_update, pay_context)

    with get_connection(db_path) as conn:
        trip = get_open_trip(conn, 100)
        payment_id = get_trip_payments(conn, trip.id)[0].id

    update, context = update_factory(user=alice, chat=chat, args=[str(payment_id)])
    context.bot_data["settings"] = settings
    await cancel_payment_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert f"cancelled payment #{payment_id}" in reply.lower()
    assert "10.00" in reply

    with get_connection(db_path) as conn:
        payments = get_trip_payments(conn, trip.id)
        splits = get_trip_splits(conn, trip.id)

    assert payments == []
    assert splits == []


async def test_cancel_payment_without_open_trip(db_path, settings, update_factory, user_factory, chat_factory):
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, context = update_factory(user=alice, chat=chat, args=["1"])
    context.bot_data["settings"] = settings

    await cancel_payment_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "no open trip" in reply.lower()


async def test_cancel_payment_invalid_id(db_path, settings, update_factory, user_factory, chat_factory):
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    update, context = update_factory(user=alice, chat=chat, args=["notanid"])
    context.bot_data["settings"] = settings

    await cancel_payment_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "usage" in reply.lower()


async def test_cancel_payment_unknown_id_in_open_trip(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    chat = chat_factory(100)

    await _start_trip(settings, update_factory, alice, chat)

    update, context = update_factory(user=alice, chat=chat, args=["999"])
    context.bot_data["settings"] = settings

    await cancel_payment_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert "no payment #999" in reply.lower()


async def test_cancel_payment_from_other_chats_trip_is_rejected(
    db_path, settings, update_factory, user_factory, chat_factory
):
    alice = user_factory(1, username="alice")
    chat_a = chat_factory(100)
    chat_b = chat_factory(200)

    await _start_trip(settings, update_factory, alice, chat_a)
    pay_update, pay_context = update_factory(user=alice, chat=chat_a, text="/pay 10 coffee")
    pay_context.bot_data["settings"] = settings
    await pay_command(pay_update, pay_context)

    with get_connection(db_path) as conn:
        trip_a = get_open_trip(conn, 100)
        payment_id = get_trip_payments(conn, trip_a.id)[0].id

    await _start_trip(settings, update_factory, alice, chat_b)

    update, context = update_factory(user=alice, chat=chat_b, args=[str(payment_id)])
    context.bot_data["settings"] = settings
    await cancel_payment_command(update, context)

    reply = update.message.reply_text.call_args[0][0]
    assert f"no payment #{payment_id}" in reply.lower()

    with get_connection(db_path) as conn:
        assert get_trip_payments(conn, trip_a.id) != []
