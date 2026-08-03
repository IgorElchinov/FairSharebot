from __future__ import annotations

import logging
from datetime import datetime, timezone

from eth_account import Account
from telegram.ext import Application, ContextTypes

from ..config import Settings
from ..db import crypto_repo
from ..db.connection import get_connection

logger = logging.getLogger("fairsharebot.jobs")

POLL_INTERVAL_SECONDS = 15
POLL_FIRST_DELAY_SECONDS = 10
# A stuck mempool tx shouldn't be polled forever - past this, mark it failed
# and let /closetrip's residual-netting safety net pick up the shortfall.
PENDING_TIMEOUT_SECONDS = 600

GAS_BALANCE_CHECK_INTERVAL_SECONDS = 60 * 60
GAS_BALANCE_CHECK_FIRST_DELAY_SECONDS = 60
# A dry relayer silently breaks *all* settlement with no other ops monitoring
# behind this bot - worth a cheap, low-value-in-ETH-terms alert threshold.
LOW_GAS_BALANCE_WEI = 10**16  # 0.01 native ETH


def _is_stale(created_at: str) -> bool:
    created = datetime.fromisoformat(created_at)
    age = (datetime.now(timezone.utc) - created).total_seconds()
    return age > PENDING_TIMEOUT_SECONDS


async def poll_pending_transfers(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trip-agnostic: scans every pending crypto_transfers row across all
    token-mode trips and reconciles it against the chain, since a settleBatch
    submitted during /pay doesn't confirm synchronously."""
    settings: Settings = context.bot_data["settings"]
    chain_client = context.bot_data.get("chain_client")
    if settings.chain is None or chain_client is None:
        return

    with get_connection(settings.db_path) as conn:
        for transfer in crypto_repo.get_pending_transfers(conn):
            if transfer.tx_hash is None:
                continue
            status = await chain_client.get_receipt_status(transfer.tx_hash)
            if status in ("confirmed", "failed"):
                crypto_repo.update_transfer_status(conn, transfer.id, status=status)
            elif _is_stale(transfer.created_at):
                crypto_repo.update_transfer_status(
                    conn, transfer.id, status="failed", error_message="timed out waiting for on-chain confirmation"
                )
                logger.warning("crypto_transfer %s timed out waiting for %s", transfer.id, transfer.tx_hash)


async def poll_relayer_gas_balance(context: ContextTypes.DEFAULT_TYPE) -> None:
    """DMs the operator if the relayer's native ETH balance runs low - a dry
    relayer silently breaks every settlement and there's no other ops
    monitoring for this bot, so this is cheap, high-value insurance."""
    settings: Settings = context.bot_data["settings"]
    chain_client = context.bot_data.get("chain_client")
    if settings.chain is None or chain_client is None:
        return

    relayer_address = Account.from_key(settings.chain.relayer_private_key).address
    balance = await chain_client.get_native_balance(relayer_address)
    if balance < LOW_GAS_BALANCE_WEI:
        logger.warning("relayer %s is low on gas: %d wei", relayer_address, balance)
        try:
            await context.bot.send_message(
                chat_id=settings.chain.owner_telegram_user_id,
                text=(
                    f"FairSharebot's relayer wallet ({relayer_address}) is low on gas: "
                    f"{balance} wei. Token-mode settlements will start failing once it "
                    "runs out - send it more native ETH."
                ),
            )
        except Exception:  # noqa: BLE001 - a failed alert must not crash the job loop
            logger.exception("could not DM operator about low relayer gas balance")


def register_jobs(app: Application) -> None:
    # Always scheduled - both jobs no-op when settings.chain is None, so this
    # doesn't depend on bot_data["settings"] already being set at
    # registration time (register_handlers is called without that guarantee
    # in some tests, and there's no reason to require it for something this
    # cheap).
    app.job_queue.run_repeating(
        poll_pending_transfers, interval=POLL_INTERVAL_SECONDS, first=POLL_FIRST_DELAY_SECONDS
    )
    app.job_queue.run_repeating(
        poll_relayer_gas_balance,
        interval=GAS_BALANCE_CHECK_INTERVAL_SECONDS,
        first=GAS_BALANCE_CHECK_FIRST_DELAY_SECONDS,
    )
