from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from ..activity_log import reply
from ..chain.wallets import export_private_key
from ..config import Settings
from ..db import crypto_repo
from ..db.connection import get_connection
from ..db.users_repo import upsert_user
from ..errors import NoCustodialWalletError
from ..utils.formatting import format_token_amount

_CHALLENGE_VALIDITY = timedelta(minutes=15)


async def wallet_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if settings.chain is None:
        await reply(update, "Token payments aren't configured for this bot.")
        return

    user = update.effective_user
    with get_connection(settings.db_path) as conn:
        wallet = crypto_repo.get_wallet(conn, user.id)

    if wallet is None:
        await reply(
            update,
            "You don't have a wallet yet - one is created automatically the "
            "first time you're part of a token-mode trip.",
        )
        return

    chain_client = context.bot_data["chain_client"]
    token_balance = await chain_client.get_token_balance(wallet.address)

    lines = [
        f"Wallet: {wallet.address} ({wallet.custody_type})",
        f"Token balance: {format_token_amount(token_balance)}",
    ]
    if wallet.custody_type == "custodial":
        native_balance = await chain_client.get_native_balance(wallet.address)
        lines.append(
            f"Native ETH balance: {format_token_amount(native_balance)} "
            "(you never need this - the bot's relayer always pays gas)"
        )
    await reply(update, "\n".join(lines))


async def link_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if settings.chain is None:
        await reply(update, "Token payments aren't configured for this bot.")
        return

    user = update.effective_user
    token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    nonce_message = (
        f"Link this wallet to FairSharebot\nTelegram user: {user.id}\nNonce: {secrets.token_hex(16)}"
    )

    with get_connection(settings.db_path) as conn:
        upsert_user(conn, user_id=user.id, username=user.username, display_name=user.full_name)
        crypto_repo.create_challenge(
            conn,
            token=token,
            user_id=user.id,
            nonce=nonce_message,
            expires_at=(now + _CHALLENGE_VALIDITY).isoformat(),
        )

    link = f"{settings.chain.link_base_url}/link/{token}"
    dm_text = (
        "Link your wallet to FairSharebot:\n"
        f"{link}\n\n"
        "This opens a page where you connect your wallet (e.g. MetaMask), sign "
        "two messages, and grant FairSharebot's Settlement contract a standing "
        "allowance - no gas required on your end. The link expires in 15 minutes."
    )
    try:
        await context.bot.send_message(chat_id=user.id, text=dm_text)
    except TelegramError:
        await reply(
            update,
            "I couldn't DM you - please start a private chat with me first "
            "(/start), then try /linkwallet again.",
        )
        return

    if update.effective_chat.id != user.id:
        await reply(update, "I've sent you a wallet-linking link in a DM.")


async def export_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if settings.chain is None:
        await reply(update, "Token payments aren't configured for this bot.")
        return

    if update.effective_chat.type != "private":
        await reply(
            update,
            "For your safety, /exportkey only works in a private chat with me - "
            "message me directly and try again.",
        )
        return

    user = update.effective_user
    with get_connection(settings.db_path) as conn:
        upsert_user(conn, user_id=user.id, username=user.username, display_name=user.full_name)
        try:
            private_key = export_private_key(
                conn, mnemonic=settings.chain.wallet_master_mnemonic, user_id=user.id
            )
        except NoCustodialWalletError:
            await reply(
                update,
                "You don't have a custodial wallet - there's nothing to export. One is "
                "created automatically the first time you're part of a token-mode trip.",
            )
            return

    await reply(
        update,
        "Your custodial wallet's private key:\n"
        f"{private_key}\n\n"
        "Import this into a wallet app (e.g. MetaMask) to control it directly. "
        "Important: the bot can still re-derive this exact key from its master seed, "
        "so exporting it does NOT remove the bot's own access. For real self-custody, "
        "generate a fresh wallet, move your funds there, then run /linkwallet with "
        "the new address.",
        redact=True,
    )
