from __future__ import annotations

from telegram.ext import Application, CommandHandler

from .start_help import help_command, start_command


def register_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
