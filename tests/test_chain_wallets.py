from __future__ import annotations

import pytest

from fairsharebot.chain.wallets import (
    derive_address,
    derive_private_key_hex,
    export_private_key,
    get_or_create_custodial_wallet,
)
from fairsharebot.db import crypto_repo, users_repo
from fairsharebot.db.connection import get_connection
from fairsharebot.errors import NoCustodialWalletError

# The standard anvil/hardhat test mnemonic - well-known vector, pinned here so
# a regression in the derivation path (wrong coin type, wrong hardening, etc.)
# is caught immediately rather than only showing up as "money went to the
# wrong address" later.
TEST_MNEMONIC = "test test test test test test test test test test test junk"
INDEX_0_ADDRESS = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
INDEX_0_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


def test_derive_address_matches_known_vector():
    assert derive_address(TEST_MNEMONIC, 0) == INDEX_0_ADDRESS


def test_derive_private_key_matches_known_vector():
    assert derive_private_key_hex(TEST_MNEMONIC, 0) == INDEX_0_KEY


def test_derive_address_is_deterministic():
    assert derive_address(TEST_MNEMONIC, 7) == derive_address(TEST_MNEMONIC, 7)


def test_derive_address_differs_per_index():
    assert derive_address(TEST_MNEMONIC, 0) != derive_address(TEST_MNEMONIC, 1)


def _make_user(conn, user_id: int) -> None:
    users_repo.upsert_user(conn, user_id=user_id, username=f"user{user_id}", display_name=f"User {user_id}")


def test_allocate_derivation_index_starts_at_zero_and_increments(db_path):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        assert crypto_repo.allocate_derivation_index(conn) == 0
        crypto_repo.insert_custodial_wallet(conn, user_id=1, derivation_index=0, address="0xabc")
        assert crypto_repo.allocate_derivation_index(conn) == 1


def test_get_or_create_custodial_wallet_creates_once_and_reuses(db_path):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        first = get_or_create_custodial_wallet(conn, mnemonic=TEST_MNEMONIC, user_id=1)
        second = get_or_create_custodial_wallet(conn, mnemonic=TEST_MNEMONIC, user_id=1)

    assert first.address == second.address
    assert first.custody_type == "custodial"
    assert first.address == INDEX_0_ADDRESS


def test_get_or_create_custodial_wallet_assigns_distinct_indices_per_user(db_path):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        _make_user(conn, 2)
        alice = get_or_create_custodial_wallet(conn, mnemonic=TEST_MNEMONIC, user_id=1)
        bob = get_or_create_custodial_wallet(conn, mnemonic=TEST_MNEMONIC, user_id=2)

    assert alice.address != bob.address


def test_export_private_key_recovers_derived_key(db_path):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        get_or_create_custodial_wallet(conn, mnemonic=TEST_MNEMONIC, user_id=1)
        key = export_private_key(conn, mnemonic=TEST_MNEMONIC, user_id=1)

    assert key == INDEX_0_KEY


def test_export_private_key_still_works_after_switching_to_external_wallet(db_path):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        get_or_create_custodial_wallet(conn, mnemonic=TEST_MNEMONIC, user_id=1)
        crypto_repo.upsert_wallet(conn, user_id=1, address="0xExternalWallet", custody_type="external")

        wallet = crypto_repo.get_wallet(conn, 1)
        key = export_private_key(conn, mnemonic=TEST_MNEMONIC, user_id=1)

    assert wallet.custody_type == "external"
    assert wallet.address == "0xExternalWallet"
    assert key == INDEX_0_KEY


def test_export_private_key_raises_if_never_custodial(db_path):
    with get_connection(db_path) as conn:
        _make_user(conn, 1)
        with pytest.raises(NoCustodialWalletError):
            export_private_key(conn, mnemonic=TEST_MNEMONIC, user_id=1)
