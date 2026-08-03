from __future__ import annotations

import logging

from telegram import Chat, Update
from telegram import User as TgUser

logger = logging.getLogger("fairsharebot.activity")


def _chat_label(chat: Chat | None) -> str:
    if chat is None:
        return "chat=unknown"
    label = f"chat_id={chat.id} type={chat.type}"
    if chat.title:
        label += f" title={chat.title!r}"
    return label


def _user_label(user: TgUser | None) -> str:
    if user is None:
        return "user=unknown"
    username = f"@{user.username}" if user.username else "(no username)"
    return f"user_id={user.id} username={username} name={user.full_name!r}"


def log_incoming(update: Update) -> None:
    """Logs every incoming update at DEBUG level, with chat and user context.

    Set LOG_LEVEL=DEBUG (in .env) for a verbose mode that shows every
    interaction FairSharebot sees, and every reply it sends (see reply()
    below) - useful while testing with friends.
    """
    chat = update.effective_chat
    user = update.effective_user
    message = update.effective_message
    text = message.text if message is not None else None
    logger.debug("<- %s | %s | text=%r", _chat_label(chat), _user_label(user), text)


async def reply(update: Update, text: str, *, redact: bool = False) -> None:
    """Sends a reply and logs it at DEBUG level.

    Uses effective_message rather than update.message: update.message is None
    for edited-message updates, which previously crashed every handler that
    called update.message.reply_text(...) directly on an edited command.

    Pass redact=True for any reply that can contain a secret (e.g.
    /exportkey's private key) - the message still sends normally, it just
    never reaches the log file, including under LOG_LEVEL=DEBUG.
    """
    chat = update.effective_chat
    user = update.effective_user
    logged_text = "<redacted>" if redact else text
    logger.debug("-> %s | %s | reply=%r", _chat_label(chat), _user_label(user), logged_text)
    await update.effective_message.reply_text(text)
