from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..chain.allowance import wait_for_receipt
from ..chain.client import ChainClientProtocol
from ..chain.permit import MAX_UINT256, build_permit_typed_data, recover_ownership_signer, recover_permit_signer
from ..config import Settings
from ..db import crypto_repo
from ..db.connection import get_connection
from ..models import WalletLinkChallenge
from .notify import notify_user
from .templates import render_link_page

_PERMIT_DEADLINE_SECONDS = 60 * 60 * 24 * 365


class CompleteLinkRequest(BaseModel):
    address: str
    ownership_signature: str
    permit_signature: str


def _is_expired(challenge: WalletLinkChallenge) -> bool:
    return datetime.now(timezone.utc) > datetime.fromisoformat(challenge.expires_at)


def _parse_signature(hex_sig: str) -> tuple[int, bytes, bytes]:
    """MetaMask (and browser wallets generally) return personal_sign /
    eth_signTypedData_v4 signatures as 0x + 130 hex chars: r(32) + s(32) +
    v(1), the same layout recover_permit_signer/recover_ownership_signer
    expect."""
    raw = bytes.fromhex(hex_sig.removeprefix("0x"))
    if len(raw) != 65:
        raise HTTPException(400, "Malformed signature")
    r, s, v = raw[0:32], raw[32:64], raw[64]
    return v, r, s


def create_app(settings: Settings, chain_client: ChainClientProtocol) -> FastAPI:
    if settings.chain is None:
        raise ValueError("Settings.chain must be configured to run the wallet-linking web app")
    chain_settings = settings.chain

    app = FastAPI()

    # token -> {typed_data, deadline, address}. Bridges the two browser round
    # trips (fetch typed data, then submit signature) within one /linkwallet
    # session. Deliberately not persisted - if this process restarts
    # mid-flow, the user just runs /linkwallet again for a fresh link.
    pending_typed_data: dict[str, dict] = {}

    def _get_valid_challenge(token: str) -> WalletLinkChallenge:
        with get_connection(settings.db_path) as conn:
            challenge = crypto_repo.get_challenge(conn, token)
        if challenge is None or challenge.status != "pending" or _is_expired(challenge):
            raise HTTPException(410, "This link is invalid, expired, or was already used")
        return challenge

    @app.get("/link/{token}", response_class=HTMLResponse)
    async def link_page(token: str) -> str:
        _get_valid_challenge(token)
        return render_link_page(token=token)

    @app.get("/api/link/{token}")
    async def get_challenge(token: str) -> dict:
        challenge = _get_valid_challenge(token)
        return {"nonce_message": challenge.nonce, "expires_at": challenge.expires_at}

    @app.get("/api/link/{token}/typed-data")
    async def get_typed_data(token: str, address: str) -> dict:
        _get_valid_challenge(token)

        nonce = await chain_client.get_permit_nonce(address)
        deadline = int(time.time()) + _PERMIT_DEADLINE_SECONDS
        typed_data = build_permit_typed_data(
            token_address=chain_settings.token_address,
            chain_id=chain_settings.chain_id,
            owner=address,
            spender=chain_settings.settlement_address,
            value=MAX_UINT256,
            nonce=nonce,
            deadline=deadline,
        )
        pending_typed_data[token] = {"typed_data": typed_data, "deadline": deadline, "address": address}
        return {"typed_data": typed_data, "deadline": deadline}

    @app.post("/api/link/{token}/complete")
    async def complete_link(token: str, body: CompleteLinkRequest) -> dict:
        challenge = _get_valid_challenge(token)

        cached = pending_typed_data.get(token)
        if cached is None or cached["address"].lower() != body.address.lower():
            raise HTTPException(400, "No matching signing session - reload the page and try again")

        ownership_sig = bytes.fromhex(body.ownership_signature.removeprefix("0x"))
        ownership_signer = recover_ownership_signer(challenge.nonce, signature=ownership_sig)
        if ownership_signer.lower() != body.address.lower():
            raise HTTPException(400, "Ownership signature does not match the connected address")

        v, r, s = _parse_signature(body.permit_signature)
        permit_signer = recover_permit_signer(cached["typed_data"], v=v, r=r, s=s)
        if permit_signer.lower() != body.address.lower():
            raise HTTPException(400, "Permit signature does not match the connected address")

        # Persist verification + the new active wallet before any network
        # call, and close the connection immediately after - submit_permit
        # and wait_for_receipt can take real wall-clock time, and holding a
        # sqlite connection open across that would block the single writer.
        with get_connection(settings.db_path) as conn:
            crypto_repo.mark_challenge_verified(conn, token=token, verified_address=body.address)
            crypto_repo.upsert_wallet(
                conn, user_id=challenge.telegram_user_id, address=body.address, custody_type="external"
            )

        tx_hash = await chain_client.submit_permit(
            owner=body.address,
            spender=chain_settings.settlement_address,
            value=MAX_UINT256,
            deadline=cached["deadline"],
            v=v,
            r=r,
            s=s,
        )
        status = await wait_for_receipt(chain_client, tx_hash)

        if status == "confirmed":
            with get_connection(settings.db_path) as conn:
                crypto_repo.mark_allowance_granted(conn, challenge.telegram_user_id)

        pending_typed_data.pop(token, None)
        await notify_user(
            settings.bot_token,
            telegram_user_id=challenge.telegram_user_id,
            linked=(status == "confirmed"),
            address=body.address,
        )
        return {"status": "linked" if status == "confirmed" else "pending"}

    return app
