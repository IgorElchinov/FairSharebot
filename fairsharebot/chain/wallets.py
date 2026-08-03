from __future__ import annotations

import sqlite3

from eth_account import Account
from eth_account.signers.local import LocalAccount

from ..db import crypto_repo
from ..errors import NoCustodialWalletError
from ..models import Wallet

# HD wallet support is "unaudited" in eth_account's own words, but this is the
# standard library used across the ecosystem for exactly this purpose
# (e.g. Brownie, Ganache-derived tooling); the risk being flagged is around
# novel derivation logic, not this well-trodden BIP-32/39 path.
Account.enable_unaudited_hdwallet_features()

_DERIVATION_PATH_TEMPLATE = "m/44'/60'/0'/0/{index}"


def derive_account(mnemonic: str, index: int) -> LocalAccount:
    """Deterministically derives the account at a given index of one master
    mnemonic. Never persisted - callers recompute this on demand every time a
    custodial wallet's key is actually needed (signing, /exportkey)."""
    path = _DERIVATION_PATH_TEMPLATE.format(index=index)
    return Account.from_mnemonic(mnemonic, account_path=path)


def derive_address(mnemonic: str, index: int) -> str:
    return derive_account(mnemonic, index).address


def derive_private_key_hex(mnemonic: str, index: int) -> str:
    return derive_account(mnemonic, index).key.hex()


def get_or_create_custodial_wallet(conn: sqlite3.Connection, *, mnemonic: str, user_id: int) -> Wallet:
    """The "ensure" idiom identity.py's _ensure_user uses for users: return the
    existing custodial wallet if this user already has one on file (even if
    they've since linked an external wallet as their *active* one - this
    always refers to the custodial lineage), otherwise derive and persist a
    fresh one at the next sequential index."""
    existing = crypto_repo.get_custodial_wallet(conn, user_id)
    if existing is not None:
        _, address = existing
    else:
        index = crypto_repo.allocate_derivation_index(conn)
        address = derive_address(mnemonic, index)
        crypto_repo.insert_custodial_wallet(conn, user_id=user_id, derivation_index=index, address=address)

    wallet = crypto_repo.get_wallet(conn, user_id)
    if wallet is None or wallet.custody_type != "custodial":
        wallet = crypto_repo.upsert_wallet(conn, user_id=user_id, address=address, custody_type="custodial")
    return wallet


def export_private_key(conn: sqlite3.Connection, *, mnemonic: str, user_id: int) -> str:
    """Re-derives a user's original custodial private key on demand - the key
    itself is never stored, only the derivation_index. Works even after the
    user has switched their active wallet to an external one via /linkwallet,
    since custodial_wallets is an append-only ledger separate from `wallets`."""
    existing = crypto_repo.get_custodial_wallet(conn, user_id)
    if existing is None:
        raise NoCustodialWalletError(user_id)
    index, _address = existing
    return derive_private_key_hex(mnemonic, index)
