from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

START_MESSAGE = (
    "Hi! I'm FairSharebot.\n\n"
    "I help split shared trip expenses in this chat, no registration needed. "
    "Use /starttrip to start a trip, then record payments as you go. "
    "Send /help to see everything I can do."
)

HELP_MESSAGE = (
    "FairSharebot commands:\n\n"
    "/starttrip [name] - start a new trip in this chat\n"
    "/pay <amount> <description> for @user1 @user2 - record an equal-split payment\n"
    "/balance - show current balances for the open trip\n"
    "/closetrip - close the trip and settle up\n"
    "/trips - list past trips in this chat\n\n"
    "More payment styles (exact amounts, weighted shares) are coming soon."
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(START_MESSAGE)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_MESSAGE)
