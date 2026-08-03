from __future__ import annotations

import sqlite3

from ..config import ChainSettings
from ..db import crypto_repo
from ..models import ClosingSettlementResult, Payment, SplitInput, Transfer
from ..settlement import compute_transfers
from .allowance import ensure_allowance
from .client import ChainClientProtocol
from .units import cents_to_token_units, token_units_to_cents

NO_ALLOWANCE_ERROR = "wallet has no confirmed allowance on the Settlement contract yet"


async def _settle_transfers(
    conn: sqlite3.Connection,
    chain_client: ChainClientProtocol,
    chain_settings: ChainSettings,
    *,
    mnemonic: str,
    trip_id: int,
    payment_id: int | None,
    transfers: list[tuple[int, int, int]],
) -> tuple[list[tuple[int, int, int]], list[tuple[int, int, int]]]:
    """Shared by settle_payment_onchain and run_closing_settlement:
    transfers is (from_user_id, to_user_id, amount_cents) triples. Ensures a
    wallet + allowance for everyone involved, submits one settleBatch call
    for whoever has a confirmed allowance, and records a failed
    crypto_transfers row (never included in the batch) for whoever doesn't -
    Settlement.settleBatch is all-or-nothing, so one missing allowance would
    otherwise block payment for everyone else in the same batch. Never
    raises - a chain failure must not roll back or block the off-chain
    record, which stays authoritative regardless.

    Returns (submitted, failed) as (from_user_id, to_user_id, amount_cents)
    triples, mirroring the input shape."""
    ready_addresses: list[tuple[str, str, int]] = []
    ready_meta: list[tuple[int, int, int]] = []
    failed: list[tuple[int, int, int]] = []

    for from_user_id, to_user_id, amount_cents in transfers:
        if amount_cents <= 0:
            continue

        from_wallet = await ensure_allowance(
            conn, chain_client, chain_settings, mnemonic=mnemonic, user_id=from_user_id
        )
        to_wallet = await ensure_allowance(
            conn, chain_client, chain_settings, mnemonic=mnemonic, user_id=to_user_id
        )
        token_amount = cents_to_token_units(amount_cents)

        if from_wallet.allowance_granted_at is None:
            crypto_repo.record_transfer_attempt(
                conn,
                trip_id=trip_id,
                payment_id=payment_id,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                from_address=from_wallet.address,
                to_address=to_wallet.address,
                token_amount=token_amount,
                tx_hash=None,
                status="failed",
                error_message=NO_ALLOWANCE_ERROR,
            )
            failed.append((from_user_id, to_user_id, amount_cents))
            continue

        ready_addresses.append((from_wallet.address, to_wallet.address, token_amount))
        ready_meta.append((from_user_id, to_user_id, amount_cents))

    submitted: list[tuple[int, int, int]] = []
    if not ready_addresses:
        return submitted, failed

    try:
        tx_hash = await chain_client.settle_batch(ready_addresses)
        status, error_message = "pending", None
    except Exception as exc:  # noqa: BLE001 - see docstring: must never propagate
        tx_hash, status, error_message = None, "failed", str(exc)

    for (from_user_id, to_user_id, amount_cents), (from_addr, to_addr, token_amount) in zip(
        ready_meta, ready_addresses
    ):
        crypto_repo.record_transfer_attempt(
            conn,
            trip_id=trip_id,
            payment_id=payment_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            from_address=from_addr,
            to_address=to_addr,
            token_amount=token_amount,
            tx_hash=tx_hash,
            status=status,
            error_message=error_message,
        )
        (submitted if status == "pending" else failed).append((from_user_id, to_user_id, amount_cents))

    return submitted, failed


async def settle_payment_onchain(
    conn: sqlite3.Connection,
    chain_client: ChainClientProtocol,
    chain_settings: ChainSettings,
    *,
    mnemonic: str,
    payment: Payment,
    splits: list[SplitInput],
) -> None:
    """Settles one /pay immediately: pulls each split participant's share
    straight to the payer's wallet in a single on-chain batch."""
    transfers = [
        (split.user_id, payment.payer_id, split.computed_amount_cents)
        for split in splits
        if split.user_id != payment.payer_id
    ]
    if not transfers:
        return
    await _settle_transfers(
        conn,
        chain_client,
        chain_settings,
        mnemonic=mnemonic,
        trip_id=payment.trip_id,
        payment_id=payment.id,
        transfers=transfers,
    )


def _compute_settled_deltas(conn: sqlite3.Connection, trip_id: int) -> dict[int, int]:
    """Net cents already moved on-chain for this trip, from confirmed
    crypto_transfers rows only - pending/failed rows haven't actually
    resolved anything yet."""
    deltas: dict[int, int] = {}
    for transfer in crypto_repo.get_confirmed_transfers_for_trip(conn, trip_id):
        cents = token_units_to_cents(transfer.token_amount)
        deltas[transfer.to_user_id] = deltas.get(transfer.to_user_id, 0) + cents
        deltas[transfer.from_user_id] = deltas.get(transfer.from_user_id, 0) - cents
    return deltas


async def run_closing_settlement(
    conn: sqlite3.Connection,
    chain_client: ChainClientProtocol,
    chain_settings: ChainSettings,
    *,
    mnemonic: str,
    trip_id: int,
    balances: dict[int, int],
) -> ClosingSettlementResult:
    """/closetrip's safety net for token-mode trips: nets whatever hasn't
    actually settled on-chain yet (residual = full off-chain balance minus
    what's already confirmed on-chain) and submits a fresh, minimal transfer
    plan for just that residual - not a raw retry of failed rows, which
    would double-count anything already partially netted by later payments."""
    settled = _compute_settled_deltas(conn, trip_id)
    residual_balances = {
        user_id: balances.get(user_id, 0) - settled.get(user_id, 0)
        for user_id in set(balances) | set(settled)
    }
    transfer_plan = compute_transfers(residual_balances)
    transfers = [(t.from_user_id, t.to_user_id, t.amount_cents) for t in transfer_plan]

    submitted, failed = await _settle_transfers(
        conn,
        chain_client,
        chain_settings,
        mnemonic=mnemonic,
        trip_id=trip_id,
        payment_id=None,
        transfers=transfers,
    )
    return ClosingSettlementResult(
        submitted=[Transfer(from_user_id=f, to_user_id=t, amount_cents=a) for f, t, a in submitted],
        failed=[Transfer(from_user_id=f, to_user_id=t, amount_cents=a) for f, t, a in failed],
    )
