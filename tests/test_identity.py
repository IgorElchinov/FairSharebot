from __future__ import annotations

import pytest

from fairsharebot.db.connection import get_connection
from fairsharebot.db.users_repo import upsert_chat_user, upsert_user
from fairsharebot.errors import UnknownUserError
from fairsharebot.identity import resolve_participants


def test_resolves_sender_only(db_path, update_factory, user_factory, chat_factory):
    sender = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, _ = update_factory(user=sender, chat=chat, text="/pay 10 coffee")

    with get_connection(db_path) as conn:
        participants = resolve_participants(
            conn,
            chat_id=chat.id,
            sender=sender,
            message=update.message,
            mentioned_usernames=[],
            text_mentioned_users=[],
        )

    assert [p.id for p in participants] == [1]


def test_resolves_reply_to_target(db_path, update_factory, user_factory, chat_factory):
    sender = user_factory(1, username="alice")
    replied = user_factory(2, username="bob")
    chat = chat_factory(100)
    update, _ = update_factory(user=sender, chat=chat, text="/pay 10 coffee", reply_to_user=replied)

    with get_connection(db_path) as conn:
        participants = resolve_participants(
            conn,
            chat_id=chat.id,
            sender=sender,
            message=update.message,
            mentioned_usernames=[],
            text_mentioned_users=[],
        )

    assert {p.id for p in participants} == {1, 2}


def test_resolves_text_mentioned_user(db_path, update_factory, user_factory, chat_factory):
    sender = user_factory(1, username="alice")
    carol = user_factory(3, username=None, first_name="Carol")
    chat = chat_factory(100)
    update, _ = update_factory(user=sender, chat=chat, text="/pay 10 coffee for Carol")

    with get_connection(db_path) as conn:
        participants = resolve_participants(
            conn,
            chat_id=chat.id,
            sender=sender,
            message=update.message,
            mentioned_usernames=[],
            text_mentioned_users=[carol],
        )

    assert {p.id for p in participants} == {1, 3}


def test_resolves_known_username(db_path, update_factory, user_factory, chat_factory):
    sender = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, _ = update_factory(user=sender, chat=chat, text="/pay 10 coffee for @bob")

    with get_connection(db_path) as conn:
        upsert_user(conn, user_id=2, username="bob", display_name="Bob")
        upsert_chat_user(conn, chat_id=100, user_id=2)

        participants = resolve_participants(
            conn,
            chat_id=chat.id,
            sender=sender,
            message=update.message,
            mentioned_usernames=["bob"],
            text_mentioned_users=[],
        )

    assert {p.id for p in participants} == {1, 2}


def test_unknown_username_raises(db_path, update_factory, user_factory, chat_factory):
    sender = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, _ = update_factory(user=sender, chat=chat, text="/pay 10 coffee for @nobody")

    with get_connection(db_path) as conn:
        with pytest.raises(UnknownUserError):
            resolve_participants(
                conn,
                chat_id=chat.id,
                sender=sender,
                message=update.message,
                mentioned_usernames=["nobody"],
                text_mentioned_users=[],
            )


def test_bot_reply_target_is_ignored(db_path, update_factory, user_factory, chat_factory):
    from telegram import User

    sender = user_factory(1, username="alice")
    bot_user = User(id=99, is_bot=True, first_name="SomeBot", username="somebot")
    chat = chat_factory(100)
    update, _ = update_factory(user=sender, chat=chat, text="/pay 10 coffee", reply_to_user=bot_user)

    with get_connection(db_path) as conn:
        participants = resolve_participants(
            conn,
            chat_id=chat.id,
            sender=sender,
            message=update.message,
            mentioned_usernames=[],
            text_mentioned_users=[],
        )

    assert [p.id for p in participants] == [1]
