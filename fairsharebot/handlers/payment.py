from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..config import Settings
from ..db.connection import get_connection
from ..db.payments_repo import add_payment, add_splits
from ..db.trips_repo import get_open_trip
from ..errors import ParseError, UnknownUserError
from ..identity import resolve_participants
from ..models import SplitInput, User
from ..utils.formatting import format_cents
from ..utils.parsing import parse_pay_command


def _equal_splits(amount_cents: int, participants: list[User]) -> list[SplitInput]:
    count = len(participants)
    base, remainder = divmod(amount_cents, count)
    return [
        SplitInput(user_id=participant.id, computed_amount_cents=base + (1 if index < remainder else 0))
        for index, participant in enumerate(participants)
    ]


async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    chat = update.effective_chat
    sender = update.effective_user
    message = update.effective_message

    try:
        parsed = parse_pay_command(message)
    except ParseError as exc:
        await update.message.reply_text(str(exc))
        return

    with get_connection(settings.db_path) as conn:
        trip = get_open_trip(conn, chat.id)
        if trip is None:
            await update.message.reply_text(
                "There's no open trip in this chat. Start one with /starttrip."
            )
            return

        try:
            participants = resolve_participants(
                conn,
                chat_id=chat.id,
                sender=sender,
                message=message,
                mentioned_usernames=parsed.mentioned_usernames,
                text_mentioned_users=parsed.text_mentioned_users,
            )
        except UnknownUserError as exc:
            await update.message.reply_text(
                f"I don't know who @{exc.username} is yet — they need to send a message in "
                "this chat (or you can reply to one of their messages) before you can split "
                "with them."
            )
            return

        payment = add_payment(
            conn,
            trip_id=trip.id,
            payer_id=sender.id,
            amount_cents=parsed.amount_cents,
            description=parsed.description,
            split_type="equal",
            created_by=sender.id,
        )
        add_splits(conn, payment_id=payment.id, splits=_equal_splits(parsed.amount_cents, participants))

    names = ", ".join(participant.display_name for participant in participants)
    description = parsed.description or "(no description)"
    await update.message.reply_text(
        f"Recorded: {format_cents(parsed.amount_cents)} for {description}\nSplit equally among: {names}"
    )
