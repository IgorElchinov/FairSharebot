from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import AsyncWeb3
from web3.exceptions import TransactionNotFound
from web3.providers.async_rpc import AsyncHTTPProvider

_ABI_DIR = Path(__file__).parent / "abi"


def _load_abi(name: str) -> list[dict]:
    return json.loads((_ABI_DIR / f"{name}.json").read_text())


class ChainClientProtocol(Protocol):
    """What the bot needs from the chain, kept narrow enough that tests can
    hand-roll a fake implementation instead of hitting a real network - the
    same "no live network calls in pytest" discipline conftest.py already
    applies to python-telegram-bot objects."""

    async def get_token_balance(self, address: str) -> int: ...

    async def get_native_balance(self, address: str) -> int: ...

    async def get_permit_nonce(self, owner: str) -> int: ...

    async def submit_permit(
        self, *, owner: str, spender: str, value: int, deadline: int, v: int, r: bytes, s: bytes
    ) -> str:
        """Relayer submits a pre-signed EIP-2612 permit on the token holder's
        behalf, paying gas itself. Returns the submitted tx hash."""
        ...

    async def settle_batch(self, transfers: list[tuple[str, str, int]]) -> str:
        """Relayer calls Settlement.settleBatch with (from, to, amount)
        triples. Returns the submitted tx hash."""
        ...

    async def mint(self, to: str, amount: int) -> str:
        """Owner mints new tokens to an address (/minttoken). Returns the
        submitted tx hash. Uses a separate owner key from the relayer's -
        minting and settlement are deliberately different roles/keys."""
        ...

    async def get_receipt_status(self, tx_hash: str) -> str | None:
        """'confirmed', 'failed', or None if not yet mined."""
        ...


class Web3ChainClient:
    """AsyncWeb3-backed implementation. One instance is created at startup and
    shared via bot_data - the nonce lock below only actually serializes
    relayer submissions (a /pay settlement racing a /closetrip retry) if
    every caller goes through this same instance."""

    def __init__(
        self,
        *,
        rpc_url: str,
        token_address: str,
        settlement_address: str,
        relayer_private_key: str,
        owner_private_key: str | None = None,
    ) -> None:
        self._w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self._token = self._w3.eth.contract(
            address=self._w3.to_checksum_address(token_address), abi=_load_abi("FairShareToken")
        )
        self._settlement = self._w3.eth.contract(
            address=self._w3.to_checksum_address(settlement_address), abi=_load_abi("Settlement")
        )
        self._relayer: LocalAccount = Account.from_key(relayer_private_key)
        # Only needed for /minttoken - a cash-only or self-funded deployment
        # never calls mint(), so this can stay unset.
        self._owner: LocalAccount | None = Account.from_key(owner_private_key) if owner_private_key else None
        self._nonce_lock = asyncio.Lock()

    async def get_token_balance(self, address: str) -> int:
        return await self._token.functions.balanceOf(self._w3.to_checksum_address(address)).call()

    async def get_native_balance(self, address: str) -> int:
        return await self._w3.eth.get_balance(self._w3.to_checksum_address(address))

    async def get_permit_nonce(self, owner: str) -> int:
        return await self._token.functions.nonces(self._w3.to_checksum_address(owner)).call()

    async def _send_from_relayer(self, contract_function) -> str:
        return await self._send_as(self._relayer, contract_function)

    async def _send_as(self, account: LocalAccount, contract_function) -> str:
        async with self._nonce_lock:
            nonce = await self._w3.eth.get_transaction_count(account.address, "pending")
            gas_price = await self._w3.eth.gas_price
            tx = await contract_function.build_transaction(
                {"from": account.address, "nonce": nonce, "gasPrice": gas_price}
            )
            signed = account.sign_transaction(tx)
            tx_hash = await self._w3.eth.send_raw_transaction(signed.rawTransaction)
            return tx_hash.hex()

    async def submit_permit(
        self, *, owner: str, spender: str, value: int, deadline: int, v: int, r: bytes, s: bytes
    ) -> str:
        fn = self._token.functions.permit(
            self._w3.to_checksum_address(owner),
            self._w3.to_checksum_address(spender),
            value,
            deadline,
            v,
            r,
            s,
        )
        return await self._send_from_relayer(fn)

    async def settle_batch(self, transfers: list[tuple[str, str, int]]) -> str:
        formatted = [
            (self._w3.to_checksum_address(from_addr), self._w3.to_checksum_address(to_addr), amount)
            for from_addr, to_addr, amount in transfers
        ]
        fn = self._settlement.functions.settleBatch(formatted)
        return await self._send_from_relayer(fn)

    async def mint(self, to: str, amount: int) -> str:
        if self._owner is None:
            raise RuntimeError("No owner key configured - set OWNER_PRIVATE_KEY to enable /minttoken")
        fn = self._token.functions.mint(self._w3.to_checksum_address(to), amount)
        return await self._send_as(self._owner, fn)

    async def get_receipt_status(self, tx_hash: str) -> str | None:
        try:
            receipt = await self._w3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return None
        if receipt is None:
            return None
        return "confirmed" if receipt["status"] == 1 else "failed"
