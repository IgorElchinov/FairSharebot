from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, MessageEntity, User

from fairsharebot.config import Settings
from fairsharebot.db.init_db import init_db


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite3"
    init_db(path)
    return path


@pytest.fixture
def settings(db_path):
    return Settings(bot_token="test-token", db_path=db_path, log_level="INFO")


@pytest.fixture
def user_factory():
    def make_user(user_id: int, *, username: str | None = None, first_name: str = "Test") -> User:
        return User(id=user_id, is_bot=False, first_name=first_name, username=username)

    return make_user


@pytest.fixture
def chat_factory():
    def make_chat(chat_id: int = 100, type_: str = "group") -> Chat:
        return Chat(id=chat_id, type=type_)

    return make_chat


@pytest.fixture
def update_factory():
    # telegram.Message/Update instances are frozen (can't monkeypatch reply_text
    # onto them), so handler tests use MagicMock stand-ins that expose the same
    # attributes the handlers actually touch.
    def make_update(
        *,
        user: User,
        chat: Chat,
        text: str = "",
        args: list[str] | None = None,
        reply_to_user: User | None = None,
        mentioned_users: list[User] | None = None,
        new_chat_members: list[User] | None = None,
    ):
        message = MagicMock()
        message.reply_text = AsyncMock()
        message.date = datetime.now(timezone.utc)
        message.text = text
        message.from_user = user
        message.new_chat_members = new_chat_members or []

        if reply_to_user is not None:
            reply_message = MagicMock()
            reply_message.from_user = reply_to_user
            message.reply_to_message = reply_message
        else:
            message.reply_to_message = None

        message.entities = [
            MessageEntity(type=MessageEntity.TEXT_MENTION, offset=0, length=1, user=mentioned)
            for mentioned in (mentioned_users or [])
        ]

        update = MagicMock()
        update.effective_user = user
        update.effective_chat = chat
        update.effective_message = message
        update.message = message

        context = SimpleNamespace(args=args or [], bot_data={})
        return update, context

    return make_update
