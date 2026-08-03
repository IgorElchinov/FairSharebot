from __future__ import annotations

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .admin import mint_token_command
from .balance import balance_command
from .error import handle_error
from .jobs import register_jobs
from .observe import observe_message
from .payment import cancel_payment_command, pay_command
from .start_help import help_command, start_command
from .trip import (
    close_trip_command,
    list_trips_command,
    start_trip_command,
    start_trip_token_command,
    trip_detail_command,
)
from .wallet import export_key_command, link_wallet_command, wallet_balance_command


def register_handlers(app: Application) -> None:
    # Runs in a separate, lower-priority group so it observes every message
    # before command dispatch. Deliberately blocking (the default): with
    # block=False this ran concurrently with the command handler for the same
    # update, and both independently write (upsert_user/upsert_chat_user) to
    # SQLite for the same sender - two concurrent writers is exactly what
    # SQLite's single-writer lock doesn't allow, and it surfaced as
    # "database is locked" once processing overlapped for real.
    app.add_handler(MessageHandler(filters.ALL, observe_message), group=-1)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("starttrip", start_trip_command))
    app.add_handler(CommandHandler("starttriptoken", start_trip_token_command))
    app.add_handler(CommandHandler("closetrip", close_trip_command))
    app.add_handler(CommandHandler("pay", pay_command))
    app.add_handler(CommandHandler(["cancelpayment", "cansel"], cancel_payment_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("trips", list_trips_command))
    app.add_handler(CommandHandler("trip", trip_detail_command))
    app.add_handler(CommandHandler("walletbalance", wallet_balance_command))
    app.add_handler(CommandHandler("linkwallet", link_wallet_command))
    app.add_handler(CommandHandler("exportkey", export_key_command))
    app.add_handler(CommandHandler("minttoken", mint_token_command))

    app.add_error_handler(handle_error)

    register_jobs(app)
