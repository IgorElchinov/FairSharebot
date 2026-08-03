from __future__ import annotations

from fairsharebot.chain.settlement_service import NO_ALLOWANCE_ERROR, settle_payment_onchain
from fairsharebot.chain.units import cents_to_token_units
from fairsharebot.db import crypto_repo, payments_repo, trips_repo, users_repo
from fairsharebot.db.connection import get_connection
from fairsharebot.models import SplitInput

MNEMONIC = "test test test test test test test test test test test junk"


def _make_user(conn, user_id: int) -> None:
    users_repo.upsert_user(conn, user_id=user_id, username=f"user{user_id}", display_name=f"User {user_id}")


def _setup_payment(conn, *, payer_id: int, split_user_ids: list[int], amount_cents_each: int = 1000):
    trip = trips_repo.create_trip(conn, chat_id=1, name="Trip", created_by=payer_id, settlement_mode="token")
    payment = payments_repo.add_payment(
        conn,
        trip_id=trip.id,
        payer_id=payer_id,
        amount_cents=amount_cents_each * len(split_user_ids),
        description="dinner",
        split_type="equal",
        created_by=payer_id,
    )
    splits = [SplitInput(user_id=uid, computed_amount_cents=amount_cents_each) for uid in split_user_ids]
    return payment, splits


async def test_settles_payer_and_participants_via_one_batch(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        for uid in (1, 2, 3):
            _make_user(conn, uid)
        payment, splits = _setup_payment(conn, payer_id=1, split_user_ids=[1, 2, 3])

        await settle_payment_onchain(
            conn,
            fake_chain_client,
            chain_settings.chain,
            mnemonic=MNEMONIC,
            payment=payment,
            splits=splits,
        )

        transfers = crypto_repo.get_pending_transfers(conn)

    # payer (user 1) excluded from the batch - they're the recipient, not a debtor.
    assert len(fake_chain_client.settle_batch_calls) == 1
    assert len(fake_chain_client.settle_batch_calls[0]) == 2
    assert {t.from_user_id for t in transfers} == {2, 3}
    assert all(t.to_user_id == 1 for t in transfers)
    assert all(t.status == "pending" for t in transfers)
    assert all(t.token_amount == cents_to_token_units(1000) for t in transfers)


async def test_participants_without_allowance_are_recorded_as_failed_and_excluded_from_batch(
    db_path, chain_settings, fake_chain_client
):
    with get_connection(db_path) as conn:
        for uid in (1, 2, 3):
            _make_user(conn, uid)
        # user 3 has an external wallet with no allowance granted yet.
        crypto_repo.upsert_wallet(conn, user_id=3, address="0xExternalNoAllowance", custody_type="external")

        payment, splits = _setup_payment(conn, payer_id=1, split_user_ids=[1, 2, 3])

        await settle_payment_onchain(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC, payment=payment, splits=splits
        )

        all_transfers = crypto_repo.get_pending_transfers(conn)
        failed_rows = [
            t for t in _all_crypto_transfers(conn) if t.status == "failed"
        ]

    # Only user 2 (custodial, allowance auto-granted) makes it into the batch.
    assert len(fake_chain_client.settle_batch_calls) == 1
    assert len(fake_chain_client.settle_batch_calls[0]) == 1
    assert [t.from_user_id for t in all_transfers] == [2]

    assert len(failed_rows) == 1
    assert failed_rows[0].from_user_id == 3
    assert failed_rows[0].error_message == NO_ALLOWANCE_ERROR


async def test_no_batch_submitted_when_payer_pays_only_for_self(db_path, chain_settings, fake_chain_client):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        payment, splits = _setup_payment(conn, payer_id=1, split_user_ids=[1])

        await settle_payment_onchain(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC, payment=payment, splits=splits
        )

    assert fake_chain_client.settle_batch_calls == []


async def test_settle_batch_exception_is_recorded_as_failed_not_raised(db_path, chain_settings, fake_chain_client):
    async def boom(transfers):
        raise RuntimeError("rpc exploded")

    fake_chain_client.settle_batch = boom

    with get_connection(db_path) as conn:
        for uid in (1, 2):
            _make_user(conn, uid)
        payment, splits = _setup_payment(conn, payer_id=1, split_user_ids=[1, 2])

        await settle_payment_onchain(
            conn, fake_chain_client, chain_settings.chain, mnemonic=MNEMONIC, payment=payment, splits=splits
        )

        rows = _all_crypto_transfers(conn)

    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert "rpc exploded" in rows[0].error_message


def _all_crypto_transfers(conn):
    rows = conn.execute("SELECT * FROM crypto_transfers ORDER BY id").fetchall()
    from fairsharebot.db.crypto_repo import _row_to_transfer

    return [_row_to_transfer(row) for row in rows]
