from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .config import Settings

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 5

# python-telegram-bot's own libraries log every HTTP request/response and every
# long-polling cycle at DEBUG - that's raw transport noise, not useful "what is
# FairSharebot doing" output, and would drown out fairsharebot.activity's logs
# in verbose mode (long polling alone hits this every ~10s regardless of any
# user activity). Capped at WARNING unconditionally, independent of LOG_LEVEL.
# httpx specifically also logs full request URLs at INFO, which would leak the
# bot token (it's part of the URL path) if left uncapped.
_QUIET_LOGGERS = ("httpx", "httpcore", "telegram")


def configure_logging(settings: Settings) -> None:
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        settings.log_dir / "fairsharebot.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # FairSharebot's own logs (including the per-interaction activity log)
    # honor LOG_LEVEL - set it to DEBUG for a verbose mode that shows every
    # incoming update and every reply, with chat/user context.
    logging.getLogger("fairsharebot").setLevel(settings.log_level)

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
