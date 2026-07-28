from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    bot_token: str
    db_path: Path
    log_level: str
    log_dir: Path
    webhook_url: str | None = None
    port: int = 8080


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
    )
