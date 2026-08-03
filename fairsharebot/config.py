from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class ChainSettings:
    """Token-mode trips are gated on this being present at all (see
    load_settings): a cash-only deployment sets none of these env vars and
    Settings.chain stays None, so /starttriptoken and friends can refuse
    cleanly instead of half-working."""

    rpc_url: str
    chain_id: int
    token_address: str
    settlement_address: str
    owner_telegram_user_id: int
    # Public HTTPS base URL of the standalone /linkwallet signing-page web
    # app (fairsharebot/webapp), e.g. "https://yourdomain.com/wallet" - a
    # separate process from the bot itself, sharing only the domain.
    link_base_url: str
    # repr=False so a stray `logger.debug(settings)` or uncaught-exception
    # traceback can never print a secret that can move real value.
    wallet_master_mnemonic: str = field(repr=False)
    relayer_private_key: str = field(repr=False)
    # Optional: only needed to enable /minttoken. Deliberately a separate key
    # from relayer_private_key - minting and settlement are different roles.
    owner_private_key: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: Path
    log_level: str
    log_dir: Path
    webhook_url: str | None = None
    port: int = 8080
    chain: ChainSettings | None = None


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    load_dotenv(env_file)

    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        raise ConfigError(
            "BOT_TOKEN is not set. Copy .env.example to .env and fill in your "
            "bot token from @BotFather."
        )

    db_path = Path(os.environ.get("DB_PATH", "./data/fairsharebot.sqlite3"))
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    log_dir = Path(os.environ.get("LOG_DIR", "./logs"))
    # Unset by default, so local dev/tests keep running long-polling exactly as
    # before - only a deployment that sets WEBHOOK_URL (e.g. Replit) switches
    # __main__.py over to run_webhook().
    webhook_url = os.environ.get("WEBHOOK_URL") or None
    port = int(os.environ.get("PORT", "8080"))

    return Settings(
        bot_token=bot_token,
        db_path=db_path,
        log_level=log_level,
        log_dir=log_dir,
        webhook_url=webhook_url,
        port=port,
        chain=_load_chain_settings(),
    )


def _load_chain_settings() -> ChainSettings | None:
    # WALLET_MASTER_MNEMONIC is the gate: unset (the default for every
    # cash-only deployment today) means token mode is entirely off, and
    # nothing else in this function is even read.
    mnemonic = os.environ.get("WALLET_MASTER_MNEMONIC")
    if not mnemonic:
        return None

    required = {
        "BASE_RPC_URL": "rpc_url",
        "CHAIN_ID": "chain_id",
        "TOKEN_ADDRESS": "token_address",
        "SETTLEMENT_ADDRESS": "settlement_address",
        "RELAYER_PRIVATE_KEY": "relayer_private_key",
        "OWNER_TELEGRAM_USER_ID": "owner_telegram_user_id",
        "WALLET_LINK_BASE_URL": "link_base_url",
    }
    values: dict[str, str] = {}
    missing: list[str] = []
    for env_var in required:
        value = os.environ.get(env_var)
        if not value:
            missing.append(env_var)
        else:
            values[env_var] = value
    if missing:
        raise ConfigError(
            "WALLET_MASTER_MNEMONIC is set (token-mode trips enabled) but "
            f"{', '.join(missing)} is/are missing. Set all chain env vars or "
            "none of them."
        )

    return ChainSettings(
        rpc_url=values["BASE_RPC_URL"],
        chain_id=int(values["CHAIN_ID"]),
        token_address=values["TOKEN_ADDRESS"],
        settlement_address=values["SETTLEMENT_ADDRESS"],
        owner_telegram_user_id=int(values["OWNER_TELEGRAM_USER_ID"]),
        link_base_url=values["WALLET_LINK_BASE_URL"].rstrip("/"),
        wallet_master_mnemonic=mnemonic,
        relayer_private_key=values["RELAYER_PRIVATE_KEY"],
        owner_private_key=os.environ.get("OWNER_PRIVATE_KEY") or None,
    )
