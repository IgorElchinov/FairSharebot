from __future__ import annotations

from telegram.ext import Application, MessageHandler

from fairsharebot.handlers import register_handlers
from fairsharebot.handlers.observe import observe_message


def test_observe_message_is_registered_blocking():
    # Regression test: observe_message previously ran with block=False,
    # meaning it executed concurrently with the command handler for the same
    # update. Both independently write to SQLite for the same sender
    # (upsert_user/upsert_chat_user), and SQLite only allows one writer at a
    # time - that race surfaced as "sqlite3.OperationalError: database is
    # locked" once processing genuinely overlapped. observe_message must run
    # to completion before command dispatch continues.
    app = Application.builder().token("test-token").build()
    register_handlers(app)

    observe_handlers = [
        handler
        for handler in app.handlers[-1]
        if isinstance(handler, MessageHandler) and handler.callback is observe_message
    ]

    assert len(observe_handlers) == 1
    # PTB represents the default (blocking) value as a truthy DefaultValue
    # sentinel, not literal True, so check truthiness rather than identity.
    assert observe_handlers[0].block
    assert bool(observe_handlers[0].block) is True
