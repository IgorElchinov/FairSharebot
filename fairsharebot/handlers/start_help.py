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
    "/pay <amount> <description> for @user1 @user2 - equal split\n"
    "/pay <amount> <description> split me=30 @alice=30 @bob=30 - exact amounts\n"
    "/pay <amount> <description> shares me=1 @alice=1 @bob=2 - weighted split\n"
    "/balance - show current balances for the open trip\n"
    "/closetrip - close the trip and settle up\n"
    "/trips - list past trips in this chat\n\n"
    "Tip: reply to someone's message with /pay to include them without @mentioning.\n"
    "Note: exact/weighted splits need 'me' or '@username' - people without a "
    "username can only be included via the equal-split 'for' form."
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(START_MESSAGE)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_MESSAGE)
