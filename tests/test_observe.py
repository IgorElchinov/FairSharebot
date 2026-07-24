from __future__ import annotations

from telegram import User

from fairsharebot.db.connection import get_connection
from fairsharebot.db.users_repo import get_user
from fairsharebot.handlers.observe import observe_message


async def test_observe_upserts_sender(db_path, settings, update_factory, user_factory, chat_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, context = update_factory(user=user, chat=chat, text="hello")
    context.bot_data["settings"] = settings

    await observe_message(update, context)

    with get_connection(db_path) as conn:
        stored = get_user(conn, 1)
    assert stored is not None
    assert stored.username == "alice"


async def test_observe_upserts_reply_to_user(db_path, settings, update_factory, user_factory, chat_factory):
    sender = user_factory(1, username="alice")
    replied = user_factory(2, username="bob")
    chat = chat_factory(100)
    update, context = update_factory(user=sender, chat=chat, text="thanks", reply_to_user=replied)
    context.bot_data["settings"] = settings

    await observe_message(update, context)

    with get_connection(db_path) as conn:
        stored = get_user(conn, 2)
    assert stored is not None
    assert stored.username == "bob"


async def test_observe_upserts_text_mentioned_user(
    db_path, settings, update_factory, user_factory, chat_factory
):
    sender = user_factory(1, username="alice")
    mentioned = user_factory(3, username=None, first_name="NoUsername")
    chat = chat_factory(100)
    update, context = update_factory(
        user=sender, chat=chat, text="hi there", mentioned_users=[mentioned]
    )
    context.bot_data["settings"] = settings

    await observe_message(update, context)

    with get_connection(db_path) as conn:
        stored = get_user(conn, 3)
    assert stored is not None
    assert stored.display_name == "NoUsername"


async def test_observe_upserts_new_chat_members(
    db_path, settings, update_factory, user_factory, chat_factory
):
    sender = user_factory(1, username="alice")
    newcomer = user_factory(4, username="dave")
    chat = chat_factory(100)
    update, context = update_factory(
        user=sender, chat=chat, text="", new_chat_members=[newcomer]
    )
    context.bot_data["settings"] = settings

    await observe_message(update, context)

    with get_connection(db_path) as conn:
        stored = get_user(conn, 4)
    assert stored is not None
    assert stored.username == "dave"


async def test_observe_skips_bots(db_path, settings, update_factory, chat_factory):
    bot_user = User(id=999, is_bot=True, first_name="SomeBot", username="somebot")
    chat = chat_factory(100)
    update, context = update_factory(user=bot_user, chat=chat, text="/start")
    context.bot_data["settings"] = settings

    await observe_message(update, context)

    with get_connection(db_path) as conn:
        stored = get_user(conn, 999)
    assert stored is None
