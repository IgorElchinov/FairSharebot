from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..activity_log import reply

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
    "/cansel <id> (or /cancelpayment <id>) - undo a payment (see /trip <id> for payment ids)\n"
    "/balance - show current balances for the open trip\n"
    "/closetrip - close the trip and settle up\n"
    "/trips - list past trips in this chat\n"
    "/trip <id> - see the full breakdown for a specific trip\n\n"
    "Tip: reply to someone's message with /pay to include them without @mentioning.\n"
    "Note: exact/weighted splits need 'me' or '@username' - people without a "
    "username can only be included via the equal-split 'for' form.\n\n"
    "If this bot has crypto payments configured:\n"
    "/starttriptoken [name] - start a trip that settles automatically on-chain\n"
    "/walletbalance - show your token-mode wallet's balance\n"
    "/linkwallet - link your own wallet instead of the auto-created one\n"
    "/exportkey - reveal your auto-created wallet's private key (DM only)"
)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, START_MESSAGE)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, HELP_MESSAGE)
