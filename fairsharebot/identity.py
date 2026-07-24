from __future__ import annotations

import sqlite3

from telegram import Message
from telegram import User as TgUser

from .db.users_repo import get_user, resolve_username, upsert_chat_user, upsert_user
from .errors import UnknownUserError
from .models import User


def _ensure_user(conn: sqlite3.Connection, chat_id: int, tg_user: TgUser) -> User:
    upsert_user(conn, user_id=tg_user.id, username=tg_user.username, display_name=tg_user.full_name)
    upsert_chat_user(conn, chat_id=chat_id, user_id=tg_user.id)
    resolved = get_user(conn, tg_user.id)
    assert resolved is not None
    return resolved


def resolve_participants(
    conn: sqlite3.Connection,
    *,
    chat_id: int,
    sender: TgUser,
    message: Message,
    mentioned_usernames: list[str],
    text_mentioned_users: list[TgUser],
) -> list[User]:
    """Resolves a command's beneficiaries to known users.

    Always resolvable: the sender, the reply-to target (if any), and any
    text_mention entities (Telegram embeds a full User object for these).
    Plain @username tokens are only resolvable if that user has been seen
    in this chat before; the first unresolvable one raises UnknownUserError
    so a payment is never partially recorded.
    """
    participants: dict[int, User] = {sender.id: _ensure_user(conn, chat_id, sender)}

    reply_to = message.reply_to_message
    if reply_to is not None and reply_to.from_user is not None and not reply_to.from_user.is_bot:
        reply_user = reply_to.from_user
        participants[reply_user.id] = _ensure_user(conn, chat_id, reply_user)

    for tg_user in text_mentioned_users:
        if tg_user.is_bot:
            continue
        participants[tg_user.id] = _ensure_user(conn, chat_id, tg_user)

    for username in mentioned_usernames:
        resolved = resolve_username(conn, chat_id=chat_id, username=username)
        if resolved is None:
            raise UnknownUserError(username)
        participants[resolved.id] = resolved

    return list(participants.values())


def resolve_ref(conn: sqlite3.Connection, *, chat_id: int, sender: TgUser, ref: str) -> User:
    """Resolves a single exact/shares split reference: "me" or a known @username."""
    if ref == "me":
        return _ensure_user(conn, chat_id, sender)

    resolved = resolve_username(conn, chat_id=chat_id, username=ref)
    if resolved is None:
        raise UnknownUserError(ref)
    return resolved
