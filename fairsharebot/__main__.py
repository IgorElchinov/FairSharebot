from __future__ import annotations

import logging

from telegram.ext import Application

from .config import ConfigError, load_settings
from .db.init_db import init_db
from .handlers import register_handlers
from .logging_conf import configure_logging


def main() -> None:
    try:
        settings = load_settings()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from None

    configure_logging(settings)

    init_db(settings.db_path)

    app = Application.builder().token(settings.bot_token).build()
    app.bot_data["settings"] = settings
    if settings.chain is not None:
        # Imported lazily so a cash-only deployment (chain=None, the default)
        # never pays the cost of importing web3/eth_account at all.
        from .chain.client import Web3ChainClient

        app.bot_data["chain_client"] = Web3ChainClient(
            rpc_url=settings.chain.rpc_url,
            token_address=settings.chain.token_address,
            settlement_address=settings.chain.settlement_address,
            relayer_private_key=settings.chain.relayer_private_key,
            owner_private_key=settings.chain.owner_private_key,
        )
    register_handlers(app)

    if settings.webhook_url:
        logging.getLogger(__name__).info("FairSharebot starting (webhook)...")
        app.run_webhook(
            listen="0.0.0.0",
            port=settings.port,
            url_path=settings.bot_token,
            webhook_url=f"{settings.webhook_url.rstrip('/')}/{settings.bot_token}",
        )
    else:
        logging.getLogger(__name__).info("FairSharebot starting (polling)...")
        app.run_polling()


if __name__ == "__main__":
    main()
