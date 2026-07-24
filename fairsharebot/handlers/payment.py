from __future__ import annotations

import sqlite3

from telegram import Update
from telegram import User as TgUser
from telegram.ext import ContextTypes

from ..config import Settings
from ..db.connection import get_connection
from ..db.payments_repo import add_payment, add_splits
from ..db.trips_repo import get_open_trip
from ..errors import ParseError, UnknownUserError
from ..identity import resolve_participants, resolve_ref
from ..models import SplitInput, User
from ..utils.formatting import format_cents
from ..utils.parsing import ParsedPayment, ParsedShare, parse_pay_command


def _equal_splits(amount_cents: int, participants: list[User]) -> tuple[list[SplitInput], str]:
    count = len(participants)
    base, remainder = divmod(amount_cents, count)
    splits = [
        SplitInput(user_id=participant.id, computed_amount_cents=base + (1 if index < remainder else 0))
        for index, participant in enumerate(participants)
    ]
    names = ", ".join(participant.display_name for participant in participants)
    return splits, f"Split equally among: {names}"


def _custom_splits(
    conn: sqlite3.Connection, *, chat_id: int, sender: TgUser, shares: list[ParsedShare]
) -> tuple[list[SplitInput], str]:
    splits: list[SplitInput] = []
    lines: list[str] = []
    for share in shares:
        user = resolve_ref(conn, chat_id=chat_id, sender=sender, ref=share.ref)
        splits.append(
            SplitInput(
                user_id=user.id,
                computed_amount_cents=share.computed_amount_cents,
                weight=share.weight,
            )
        )
        lines.append(f"{user.display_name}: {format_cents(share.computed_amount_cents)}")
    return splits, "Split:\n" + "\n".join(lines)


async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    chat = update.effective_chat
    sender = update.effective_user
    message = update.effective_message

    try:
        parsed: ParsedPayment = parse_pay_command(message)
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
            if parsed.split_type == "equal":
                participants = resolve_participants(
                    conn,
                    chat_id=chat.id,
                    sender=sender,
                    message=message,
                    mentioned_usernames=parsed.mentioned_usernames,
                    text_mentioned_users=parsed.text_mentioned_users,
                )
                splits, summary = _equal_splits(parsed.amount_cents, participants)
            else:
                splits, summary = _custom_splits(
                    conn, chat_id=chat.id, sender=sender, shares=parsed.shares
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
            split_type=parsed.split_type,
            created_by=sender.id,
        )
        add_splits(conn, payment_id=payment.id, splits=splits)

    description = parsed.description or "(no description)"
    await update.message.reply_text(
        f"Recorded: {format_cents(parsed.amount_cents)} for {description}\n{summary}"
    )
