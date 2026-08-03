from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from ..activity_log import reply
from ..chain.allowance import ensure_allowance
from ..chain.units import parse_token_amount
from ..config import Settings
from ..db.connection import get_connection
from ..db.users_repo import upsert_chat_user, upsert_user
from ..errors import UnknownUserError
from ..identity import resolve_ref
from ..utils.formatting import format_token_amount


async def mint_token_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if settings.chain is None:
        await reply(update, "Token payments aren't configured for this bot.")
        return

    sender = update.effective_user
    if sender.id != settings.chain.owner_telegram_user_id:
        await reply(update, "Only the bot operator can mint tokens.")
        return

    if len(context.args) != 2:
        await reply(update, "Usage: /minttoken @user <amount>")
        return

    ref, amount_text = context.args
    # resolve_ref/UnknownUserError expect a normalized ref ("me" or a
    # leading-'@'-free username, same convention utils/parsing.py's
    # _normalize_ref uses for /pay) - otherwise the error message below ends
    # up double-prepending '@' (e.g. "I don't know who @@alice is yet").
    ref = ref[1:] if ref.startswith("@") and len(ref) > 1 else ref
    try:
        token_amount = parse_token_amount(amount_text)
    except ValueError as exc:
        await reply(update, str(exc))
        return

    chat = update.effective_chat
    with get_connection(settings.db_path) as conn:
        upsert_user(conn, user_id=sender.id, username=sender.username, display_name=sender.full_name)
        upsert_chat_user(conn, chat_id=chat.id, user_id=sender.id)
        try:
            target = resolve_ref(conn, chat_id=chat.id, sender=sender, ref=ref)
        except UnknownUserError as exc:
            await reply(
                update,
                f"I don't know who @{exc.username} is yet - they need to send a message in "
                "this chat first.",
            )
            return

        chain_client = context.bot_data["chain_client"]
        wallet = await ensure_allowance(
            conn,
            chain_client,
            settings.chain,
            mnemonic=settings.chain.wallet_master_mnemonic,
            user_id=target.id,
        )

    try:
        tx_hash = await chain_client.mint(wallet.address, token_amount)
    except Exception as exc:  # noqa: BLE001 - report the failure, don't crash the handler
        await reply(update, f"Minting failed: {exc}")
        return

    await reply(
        update,
        f"Minted {format_token_amount(token_amount)} tokens to {target.display_name} "
        f"({wallet.address}).\ntx: {tx_hash}",
    )
