from __future__ import annotations

import asyncio
import sqlite3
import time

from ..config import ChainSettings
from ..db import crypto_repo
from ..models import Wallet
from .client import ChainClientProtocol
from .permit import MAX_UINT256, build_permit_typed_data, sign_permit_with_key
from .wallets import export_private_key, get_or_create_custodial_wallet

# A standing allowance, not a per-payment permit - long-lived on purpose so a
# custodial wallet only ever needs this done once.
_PERMIT_DEADLINE_SECONDS = 60 * 60 * 24 * 365
RECEIPT_POLL_INTERVAL_SECONDS = 0.5
RECEIPT_POLL_ATTEMPTS = 20


async def ensure_allowance(
    conn: sqlite3.Connection,
    chain_client: ChainClientProtocol,
    chain_settings: ChainSettings,
    *,
    mnemonic: str,
    user_id: int,
) -> Wallet:
    """Makes sure user_id's active wallet has a standing max allowance on the
    Settlement contract, granting one automatically and invisibly for
    custodial wallets (the bot holds the key, so it just signs and submits).
    External wallets can only get their allowance granted by the user
    signing it themselves during /linkwallet - if that hasn't happened yet,
    this returns the wallet unchanged rather than trying to force it."""
    wallet = crypto_repo.get_wallet(conn, user_id)
    if wallet is None:
        wallet = get_or_create_custodial_wallet(conn, mnemonic=mnemonic, user_id=user_id)

    if wallet.allowance_granted_at is not None or wallet.custody_type != "custodial":
        return wallet

    private_key = export_private_key(conn, mnemonic=mnemonic, user_id=user_id)
    nonce = await chain_client.get_permit_nonce(wallet.address)
    deadline = int(time.time()) + _PERMIT_DEADLINE_SECONDS
    typed_data = build_permit_typed_data(
        token_address=chain_settings.token_address,
        chain_id=chain_settings.chain_id,
        owner=wallet.address,
        spender=chain_settings.settlement_address,
        value=MAX_UINT256,
        nonce=nonce,
        deadline=deadline,
    )
    v, r, s = sign_permit_with_key(private_key, typed_data)
    tx_hash = await chain_client.submit_permit(
        owner=wallet.address,
        spender=chain_settings.settlement_address,
        value=MAX_UINT256,
        deadline=deadline,
        v=v,
        r=r,
        s=s,
    )

    status = await wait_for_receipt(chain_client, tx_hash)
    if status == "confirmed":
        crypto_repo.mark_allowance_granted(conn, user_id)
        wallet = crypto_repo.get_wallet(conn, user_id)
    return wallet


async def wait_for_receipt(chain_client: ChainClientProtocol, tx_hash: str) -> str | None:
    """Polls until a tx is mined (or gives up) - shared by ensure_allowance
    above and the /linkwallet web app's own permit submission."""
    for _ in range(RECEIPT_POLL_ATTEMPTS):
        status = await chain_client.get_receipt_status(tx_hash)
        if status is not None:
            return status
        await asyncio.sleep(RECEIPT_POLL_INTERVAL_SECONDS)
    return None
