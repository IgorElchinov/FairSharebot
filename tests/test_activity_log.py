from __future__ import annotations

import logging

from fairsharebot.activity_log import log_incoming, reply


async def test_log_incoming_includes_chat_and_user_context(
    caplog, update_factory, user_factory, chat_factory
):
    user = user_factory(1, username="alice", first_name="Alice")
    chat = chat_factory(100, type_="group")
    update, _ = update_factory(user=user, chat=chat, text="/pay 10 coffee")

    with caplog.at_level(logging.DEBUG, logger="fairsharebot.activity"):
        log_incoming(update)

    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "chat_id=100" in message
    assert "type=group" in message
    assert "user_id=1" in message
    assert "@alice" in message
    assert "/pay 10 coffee" in message


async def test_reply_sends_message_and_logs_it(caplog, update_factory, user_factory, chat_factory):
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, _ = update_factory(user=user, chat=chat, text="/balance")

    with caplog.at_level(logging.DEBUG, logger="fairsharebot.activity"):
        await reply(update, "Everyone's settled up.")

    update.effective_message.reply_text.assert_awaited_once_with("Everyone's settled up.")
    assert any("Everyone's settled up." in r.getMessage() for r in caplog.records)


async def test_reply_uses_effective_message_not_message(update_factory, user_factory, chat_factory):
    # Regression test: reply() must work even when update.message is None
    # (edited-message updates), which crashed every handler before this fix.
    user = user_factory(1, username="alice")
    chat = chat_factory(100)
    update, _ = update_factory(user=user, chat=chat, text="/help", edited=True)

    assert update.message is None

    await reply(update, "hi")

    update.effective_message.reply_text.assert_awaited_once_with("hi")
