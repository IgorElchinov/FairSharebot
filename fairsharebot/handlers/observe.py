from __future__ import annotations

from telegram import Update
from telegram import User as TgUser
from telegram.ext import ContextTypes

from ..config import Settings
from ..db.connection import get_connection
from ..db.users_repo import upsert_chat_user, upsert_user


def _observed_users(update: Update) -> list[TgUser]:
    message = update.effective_message
    if message is None:
        return []

    users: list[TgUser] = []

    if message.from_user is not None:
        users.append(message.from_user)

    if message.reply_to_message is not None and message.reply_to_message.from_user is not None:
        users.append(message.reply_to_message.from_user)

    for entity in message.entities or []:
        if entity.type == "text_mention" and entity.user is not None:
            users.append(entity.user)

    users.extend(message.new_chat_members or [])

    return users


async def observe_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    if chat is None:
        return

    users = [user for user in _observed_users(update) if not user.is_bot]
    if not users:
        return

    settings: Settings = context.bot_data["settings"]
    with get_connection(settings.db_path) as conn:
        for user in users:
            upsert_user(conn, user_id=user.id, username=user.username, display_name=user.full_name)
            upsert_chat_user(conn, chat_id=chat.id, user_id=user.id)
