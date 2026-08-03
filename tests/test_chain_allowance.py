from __future__ import annotations

from fairsharebot.chain import allowance as allowance_module
from fairsharebot.chain.allowance import ensure_allowance
from fairsharebot.db import crypto_repo, users_repo
from fairsharebot.db.connection import get_connection

MNEMONIC = "test test test test test test test test test test test junk"


def _make_user(conn, user_id: int) -> None:
    users_repo.upsert_user(conn, user_id=user_id, username=f"user{user_id}", display_name=f"User {user_id}")


async def test_ensure_allowance_creates_custodial_wallet_and_grants_allowance(
    db_path, chain_settings, fake_chain_client
):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        wallet = await ensure_allowance(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC, user_id=1
        )

    assert wallet.custody_type == "custodial"
    assert wallet.allowance_granted_at is not None
    assert len(fake_chain_client.permit_calls) == 1
    assert fake_chain_client.permit_calls[0]["owner"] == wallet.address
    assert fake_chain_client.permit_calls[0]["spender"] == chain_settings.chain.settlement_address


async def test_ensure_allowance_is_idempotent_once_granted(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        await ensure_allowance(conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC, user_id=1)
        await ensure_allowance(conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC, user_id=1)

    assert len(fake_chain_client.permit_calls) == 1


async def test_ensure_allowance_does_not_grant_for_external_wallet(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        crypto_repo.upsert_wallet(conn, user_id=1, address="0xExternalWallet", custody_type="external")

        wallet = await ensure_allowance(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC, user_id=1
        )

    assert wallet.custody_type == "external"
    assert wallet.allowance_granted_at is None
    assert fake_chain_client.permit_calls == []


async def test_ensure_allowance_leaves_wallet_unmarked_if_permit_never_confirms(
    db_path, chain_settings, fake_chain_client, monkeypatch
):
    monkeypatch.setattr(allowance_module, "RECEIPT_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(allowance_module, "RECEIPT_POLL_ATTEMPTS", 2)

    async def never_confirms(tx_hash):
        return None

    fake_chain_client.get_receipt_status = never_confirms

    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        wallet = await ensure_allowance(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC, user_id=1
        )

    assert wallet.allowance_granted_at is None
    assert len(fake_chain_client.permit_calls) == 1
