from __future__ import annotations

import logging

from telegram.ext import Application

from .config import ConfigError, load_settings
from .db.init_db import init_db
from .handlers import register_handlers


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from None

    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs full request URLs at INFO, which would otherwise leak the bot
    # token (it's part of the URL path) into logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    init_db(settings.db_path)

    app = Application.builder().token(settings.bot_token).build()
    app.bot_data["settings"] = settings
    register_handlers(app)

    logging.getLogger(__name__).info("FairSharebot starting (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
