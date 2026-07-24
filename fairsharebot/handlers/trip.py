from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..config import Settings
from ..db.connection import get_connection
from ..db.trips_repo import close_trip, create_trip
from ..db.users_repo import upsert_chat_user, upsert_user
from ..errors import NoOpenTripError, TripAlreadyOpenError


def _default_trip_name(update: Update) -> str:
    date = update.effective_message.date
    return f"Trip {date:%Y-%m-%d}"


async def start_trip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    chat = update.effective_chat
    user = update.effective_user

    name = " ".join(context.args) if context.args else _default_trip_name(update)

    with get_connection(settings.db_path) as conn:
        upsert_user(conn, user_id=user.id, username=user.username, display_name=user.full_name)
        upsert_chat_user(conn, chat_id=chat.id, user_id=user.id)
        try:
            trip = create_trip(conn, chat_id=chat.id, name=name, created_by=user.id)
        except TripAlreadyOpenError:
            await update.message.reply_text(
                "A trip is already open in this chat. Use /closetrip to close it first."
            )
            return

    await update.message.reply_text(
        f"Trip started: {trip.name}\n"
        "Record payments with /pay, then /closetrip when you're done."
    )


async def close_trip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    chat = update.effective_chat

    with get_connection(settings.db_path) as conn:
        try:
            trip = close_trip(conn, chat.id)
        except NoOpenTripError:
            await update.message.reply_text("There's no open trip in this chat to close.")
            return

    await update.message.reply_text(
        f"Trip closed: {trip.name}\nSettlement is coming in a future update."
    )
