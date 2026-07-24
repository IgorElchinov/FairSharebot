from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fairsharebot.handlers.error import handle_error


async def test_handle_error_replies_with_friendly_message(update_factory, user_factory, chat_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, _ = update_factory(user=user, chat=chat, text="/pay boom taxi")

    context = SimpleNamespace(error=ValueError("boom"))

    await handle_error(update, context)

    update.message.reply_text.assert_awaited_once()
    reply = update.message.reply_text.call_args[0][0]
    assert "went wrong" in reply.lower()


async def test_handle_error_survives_non_update_object():
    context = SimpleNamespace(error=ValueError("boom"))

    # Should not raise even when `update` isn't a telegram.Update (e.g. a
    # network error during polling itself, which PTB can also route here).
    await handle_error("not an update", context)


async def test_handle_error_survives_reply_failure(update_factory, user_factory, chat_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, _ = update_factory(user=user, chat=chat, text="/pay boom taxi")
    update.message.reply_text = AsyncMock(side_effect=RuntimeError("network down"))

    context = SimpleNamespace(error=ValueError("boom"))

    # Should not raise even if notifying the chat itself fails.
    await handle_error(update, context)
