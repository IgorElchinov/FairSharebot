from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..activity_log import reply
from ..config import Settings
from ..db.connection import get_connection
from ..db.payments_repo import get_trip_payments, get_trip_splits
from ..db.trips_repo import close_trip, create_trip, get_trip, list_trips_with_totals
from ..db.users_repo import get_display_names, upsert_chat_user, upsert_user
from ..errors import NoOpenTripError, TripAlreadyOpenError
from ..settlement import compute_balances, compute_transfers
from ..utils.formatting import format_cents, format_date, format_transfers


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
            await reply(
                update, "A trip is already open in this chat. Use /closetrip to close it first."
            )
            return

    await reply(
        update,
        f"Trip started: {trip.name}\n"
        "Record payments with /pay, then /closetrip when you're done.",
    )


async def close_trip_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    chat = update.effective_chat

    with get_connection(settings.db_path) as conn:
        try:
            trip = close_trip(conn, chat.id)
        except NoOpenTripError:
            await reply(update, "There's no open trip in this chat to close.")
            return

        payments = get_trip_payments(conn, trip.id)
        splits = get_trip_splits(conn, trip.id)
        balances = compute_balances(payments, splits)
        names = get_display_names(conn, balances.keys())

    lines = [f"Trip closed: {trip.name}"]
    if not payments:
        lines.append("No payments were recorded.")
    else:
        lines.append("Final settlement:")
        lines.append(format_transfers(compute_transfers(balances), names))

    await reply(update, "\n".join(lines))


async def list_trips_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    chat = update.effective_chat

    with get_connection(settings.db_path) as conn:
        trips_with_totals = list_trips_with_totals(conn, chat.id)

    if not trips_with_totals:
        await reply(update, "No trips yet in this chat. Start one with /starttrip.")
        return

    lines = ["Trips in this chat:"]
    for trip, total_cents in trips_with_totals:
        date_range = format_date(trip.created_at)
        if trip.closed_at:
            date_range += f" to {format_date(trip.closed_at)}"
        lines.append(
            f"#{trip.id} {trip.name} ({trip.status}) - {date_range} - total {format_cents(total_cents)}"
        )
    lines.append("")
    lines.append("Use /trip <id> to see the full breakdown for a trip.")

    await reply(update, "\n".join(lines))


async def trip_detail_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    chat = update.effective_chat

    if not context.args or not context.args[0].isdigit():
        await reply(update, "Usage: /trip <id> - see /trips for trip ids.")
        return

    trip_id = int(context.args[0])

    with get_connection(settings.db_path) as conn:
        trip = get_trip(conn, trip_id)
        if trip is None or trip.chat_id != chat.id:
            await reply(update, f"No trip #{trip_id} found in this chat. See /trips.")
            return

        payments = get_trip_payments(conn, trip.id)
        splits = get_trip_splits(conn, trip.id)
        balances = compute_balances(payments, splits)
        names = get_display_names(conn, {p.payer_id for p in payments} | set(balances.keys()))

    lines = [f"Trip #{trip.id}: {trip.name} ({trip.status})"]
    if not payments:
        lines.append("No payments were recorded.")
    else:
        lines.append("")
        lines.append("Payments:")
        for payment in payments:
            payer_name = names[payment.payer_id]
            description = payment.description or "(no description)"
            lines.append(
                f"- #{payment.id} {payer_name} paid {format_cents(payment.amount_cents)} for {description}"
            )

        lines.append("")
        lines.append("Settlement:")
        lines.append(format_transfers(compute_transfers(balances), names))

    await reply(update, "\n".join(lines))
