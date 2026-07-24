from __future__ import annotations

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .observe import observe_message
from .start_help import help_command, start_command
from .trip import close_trip_command, start_trip_command


def register_handlers(app: Application) -> None:
    # Runs in a separate, lower-priority group so it observes every message
    # (including commands) without interfering with command dispatch.
    app.add_handler(MessageHandler(filters.ALL, observe_message, block=False), group=-1)

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("starttrip", start_trip_command))
    app.add_handler(CommandHandler("closetrip", close_trip_command))
