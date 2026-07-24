from __future__ import annotations

import logging

from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def handle_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catches any exception unhandled by a command handler, so one bad update
    can't silently drop a reply or take down the polling loop.

    `update` isn't always a telegram.Update - PTB also routes non-update errors
    (e.g. network errors during polling) through here - so this duck-types on
    effective_message rather than checking the type.
    """
    logger.error("Unhandled exception while processing an update", exc_info=context.error)

    message = getattr(update, "effective_message", None)
    if message is None:
        return

    try:
        await message.reply_text(
            "Something went wrong handling that. Please try again, and double-check "
            "the command syntax with /help if it keeps happening."
        )
    except Exception:
        logger.exception("Failed to notify the chat about a prior error")
