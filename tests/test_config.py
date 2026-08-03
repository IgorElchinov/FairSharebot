from __future__ import annotations

import pytest

from fairsharebot.config import ConfigError, load_settings


def test_load_settings_requires_bot_token(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("")

    with pytest.raises(ConfigError):
        load_settings(env_file)


def test_load_settings_reads_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_DIR", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("BOT_TOKEN=test-token\nDB_PATH=./somewhere.sqlite3\n")

    settings = load_settings(env_file)

    assert settings.bot_token == "test-token"
    assert str(settings.db_path) == "somewhere.sqlite3"
    assert settings.log_level == "INFO"
    assert str(settings.log_dir) == "logs"


def test_load_settings_reads_log_dir_override(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("LOG_DIR", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("BOT_TOKEN=test-token\nLOG_DIR=./somewhere-else/logs\n")

    settings = load_settings(env_file)

    assert str(settings.log_dir) == "somewhere-else/logs"


_CHAIN_ENV_VARS = [
    "WALLET_MASTER_MNEMONIC",
    "RELAYER_PRIVATE_KEY",
    "BASE_RPC_URL",
    "CHAIN_ID",
    "TOKEN_ADDRESS",
    "SETTLEMENT_ADDRESS",
    "OWNER_TELEGRAM_USER_ID",
]


def _clear_chain_env(monkeypatch):
    for var in _CHAIN_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_load_settings_leaves_chain_unset_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    _clear_chain_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("BOT_TOKEN=test-token\n")

    settings = load_settings(env_file)

    assert settings.chain is None


def test_load_settings_loads_chain_settings_when_fully_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    _clear_chain_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BOT_TOKEN=test-token\n"
        "WALLET_MASTER_MNEMONIC=test test test test test test test test test test test junk\n"
        "RELAYER_PRIVATE_KEY=0xabc\n"
        "BASE_RPC_URL=https://sepolia.base.org\n"
        "CHAIN_ID=84532\n"
        "TOKEN_ADDRESS=0xToken\n"
        "SETTLEMENT_ADDRESS=0xSettlement\n"
        "OWNER_TELEGRAM_USER_ID=42\n"
        "WALLET_LINK_BASE_URL=https://example.com/wallet/\n"
    )

    settings = load_settings(env_file)

    assert settings.chain is not None
    assert settings.chain.rpc_url == "https://sepolia.base.org"
    assert settings.chain.chain_id == 84532
    assert settings.chain.token_address == "0xToken"
    assert settings.chain.settlement_address == "0xSettlement"
    assert settings.chain.owner_telegram_user_id == 42
    assert settings.chain.link_base_url == "https://example.com/wallet"
    assert settings.chain.wallet_master_mnemonic.startswith("test test")
    assert settings.chain.relayer_private_key == "0xabc"


def test_load_settings_raises_if_chain_partially_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    _clear_chain_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BOT_TOKEN=test-token\n"
        "WALLET_MASTER_MNEMONIC=test test test test test test test test test test test junk\n"
    )

    with pytest.raises(ConfigError):
        load_settings(env_file)


def test_chain_settings_repr_never_leaks_secrets(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    _clear_chain_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BOT_TOKEN=test-token\n"
        "WALLET_MASTER_MNEMONIC=super-secret-mnemonic\n"
        "RELAYER_PRIVATE_KEY=0xsupersecretkey\n"
        "BASE_RPC_URL=https://sepolia.base.org\n"
        "CHAIN_ID=84532\n"
        "TOKEN_ADDRESS=0xToken\n"
        "SETTLEMENT_ADDRESS=0xSettlement\n"
        "OWNER_TELEGRAM_USER_ID=42\n"
        "WALLET_LINK_BASE_URL=https://example.com/wallet\n"
    )

    settings = load_settings(env_file)

    rendered = repr(settings.chain)
    assert "super-secret-mnemonic" not in rendered
    assert "0xsupersecretkey" not in rendered
