from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..config import Settings
from ..db.connection import get_connection
from ..db.payments_repo import get_trip_payments, get_trip_splits
from ..db.trips_repo import get_open_trip
from ..db.users_repo import get_display_names
from ..settlement import compute_balances, compute_transfers
from ..utils.formatting import format_cents, format_transfers


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    chat = update.effective_chat

    with get_connection(settings.db_path) as conn:
        trip = get_open_trip(conn, chat.id)
        if trip is None:
            await update.message.reply_text(
                "There's no open trip in this chat. Start one with /starttrip."
            )
            return

        payments = get_trip_payments(conn, trip.id)
        splits = get_trip_splits(conn, trip.id)
        balances = compute_balances(payments, splits)
        names = get_display_names(conn, balances.keys())

    lines = [f"Balances for {trip.name}:"]
    if not payments:
        lines.append("No payments recorded yet.")
    elif all(net_cents == 0 for net_cents in balances.values()):
        lines.append("Everyone's settled up.")
    else:
        for user_id, net_cents in sorted(balances.items(), key=lambda item: -item[1]):
            if net_cents == 0:
                continue
            verb = "is owed" if net_cents > 0 else "owes"
            lines.append(f"{names[user_id]} {verb} {format_cents(abs(net_cents))}")

        lines.append("")
        lines.append("Suggested settlement (preview, trip is still open):")
        lines.append(format_transfers(compute_transfers(balances), names))

    await update.message.reply_text("\n".join(lines))
