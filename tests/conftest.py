from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Chat, MessageEntity, User

from fairsharebot.chain.wallets import derive_address
from fairsharebot.config import ChainSettings, Settings
from fairsharebot.db.init_db import init_db

TEST_MNEMONIC = "test test test test test test test test test test test junk"
# High derivation indices so they never collide with custodial wallets that
# tests create starting from index 0.
_FAKE_TOKEN_ADDRESS = derive_address(TEST_MNEMONIC, 9998)
_FAKE_SETTLEMENT_ADDRESS = derive_address(TEST_MNEMONIC, 9999)


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.sqlite3"
    init_db(path)
    return path


@pytest.fixture
def settings(db_path, tmp_path):
    return Settings(bot_token="test-token", db_path=db_path, log_level="INFO", log_dir=tmp_path / "logs")


@pytest.fixture
def chain_settings(db_path, tmp_path):
    """A Settings instance with token mode enabled, for handler tests that
    need settings.chain to be non-None (e.g. /walletbalance, /pay on a
    token-mode trip)."""
    chain = ChainSettings(
        rpc_url="http://test-rpc.invalid",
        chain_id=31337,
        token_address=_FAKE_TOKEN_ADDRESS,
        settlement_address=_FAKE_SETTLEMENT_ADDRESS,
        owner_telegram_user_id=999,
        link_base_url="https://test.invalid/wallet",
        wallet_master_mnemonic=TEST_MNEMONIC,
        relayer_private_key="0x" + "11" * 32,
    )
    return Settings(
        bot_token="test-token",
        db_path=db_path,
        log_level="INFO",
        log_dir=tmp_path / "logs",
        chain=chain,
    )


class FakeChainClient:
    """Hand-rolled ChainClientProtocol implementation for tests - no real
    network calls, same philosophy as the MagicMock stand-ins below for
    python-telegram-bot objects. Real (non-fake) chain behavior is validated
    separately against a local anvil node / Base Sepolia, not in pytest."""

    def __init__(self):
        self.token_balances: dict[str, int] = {}
        self.native_balances: dict[str, int] = {}
        self.permit_nonces: dict[str, int] = {}
        self.settle_batch_calls: list[list[tuple[str, str, int]]] = []
        self.permit_calls: list[dict] = []
        self.mint_calls: list[tuple[str, int]] = []
        self.receipt_statuses: dict[str, str | None] = {}
        self._next_tx_id = 1

    def _next_tx_hash(self, prefix: str) -> str:
        tx_hash = f"0x{prefix}{self._next_tx_id:04d}"
        self._next_tx_id += 1
        return tx_hash

    async def get_token_balance(self, address: str) -> int:
        return self.token_balances.get(address, 0)

    async def get_native_balance(self, address: str) -> int:
        return self.native_balances.get(address, 0)

    async def get_permit_nonce(self, owner: str) -> int:
        return self.permit_nonces.get(owner, 0)

    async def submit_permit(self, **kwargs) -> str:
        self.permit_calls.append(kwargs)
        tx_hash = self._next_tx_hash("permit")
        self.receipt_statuses.setdefault(tx_hash, "confirmed")
        return tx_hash

    async def settle_batch(self, transfers: list[tuple[str, str, int]]) -> str:
        self.settle_batch_calls.append(transfers)
        tx_hash = self._next_tx_hash("settle")
        self.receipt_statuses.setdefault(tx_hash, "confirmed")
        return tx_hash

    async def mint(self, to: str, amount: int) -> str:
        self.mint_calls.append((to, amount))
        # Mirror the fake settle_batch's bookkeeping so /walletbalance-style
        # assertions in tests can see the minted balance land immediately.
        self.token_balances[to] = self.token_balances.get(to, 0) + amount
        tx_hash = self._next_tx_hash("mint")
        self.receipt_statuses.setdefault(tx_hash, "confirmed")
        return tx_hash

    async def get_receipt_status(self, tx_hash: str) -> str | None:
        return self.receipt_statuses.get(tx_hash)


@pytest.fixture
def fake_chain_client():
    return FakeChainClient()


@pytest.fixture
def user_factory():
    def make_user(user_id: int, *, username: str | None = None, first_name: str = "Test") -> User:
        return User(id=user_id, is_bot=False, first_name=first_name, username=username)

    return make_user


@pytest.fixture
def chat_factory():
    def make_chat(chat_id: int = 100, type_: str = "group") -> Chat:
        return Chat(id=chat_id, type=type_)

    return make_chat


@pytest.fixture
def update_factory():
    # telegram.Message/Update instances are frozen (can't monkeypatch reply_text
    # onto them), so handler tests use MagicMock stand-ins that expose the same
    # attributes the handlers actually touch.
    def make_update(
        *,
        user: User,
        chat: Chat,
        text: str = "",
        args: list[str] | None = None,
        reply_to_user: User | None = None,
        mentioned_users: list[User] | None = None,
        new_chat_members: list[User] | None = None,
        edited: bool = False,
    ):
        message = MagicMock()
        message.reply_text = AsyncMock()
        message.date = datetime.now(timezone.utc)
        message.text = text
        message.from_user = user
        message.new_chat_members = new_chat_members or []

        if reply_to_user is not None:
            reply_message = MagicMock()
            reply_message.from_user = reply_to_user
            message.reply_to_message = reply_message
        else:
            message.reply_to_message = None

        message.entities = [
            MessageEntity(type=MessageEntity.TEXT_MENTION, offset=0, length=1, user=mentioned)
            for mentioned in (mentioned_users or [])
        ]

        update = MagicMock()
        update.effective_user = user
        update.effective_chat = chat
        update.effective_message = message
        # Real telegram.Update.message is None for edited-message updates -
        # only effective_message is populated then. Handlers must use
        # effective_message (see fairsharebot/activity_log.py's reply()).
        update.message = None if edited else message

        context = SimpleNamespace(args=args or [], bot_data={})
        return update, context

    return make_update
