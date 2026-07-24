# FairSharebot

FairSharebot is a lightweight Telegram bot that splits shared trip expenses - no
registration, no spreadsheets. See @vibecoding/IDEA.md for the original product idea and
@vibecoding/PLAN.md for the implementation plan (data model, the Telegram mention-resolution
approach, the settlement algorithm, and the phased build order).

Phases 0-6 of the plan are done: trip lifecycle, all three `/pay` split types (equal, exact,
weighted), balances, final settlement, trip history, and polish (error handler, input
validation, logging, branding). Remaining work is the explicitly-deferred future list at the
end of PLAN.md (reminders, `/cancelpayment`, payer override, receipt OCR, multi-currency) -
nothing there is started.

## Stack

- Python 3.11+, `python-telegram-bot` (PTB) v21.x async, stdlib `sqlite3` (no ORM).
- Setup: copy `.env.example` to `.env`, set `BOT_TOKEN` (from @BotFather).
- Run locally: `python -m fairsharebot` (long polling, no webhook/public URL needed).
- Tests: `pytest -q` (dev deps in `requirements-dev.txt`). No network access needed - handler
  tests build `Update`/`Context` objects directly (see `tests/conftest.py`), and
  parsing/settlement logic is tested as pure functions.

## Debugging a running bot

Logs go to both the console and `./logs/fairsharebot.log` (rotating, configurable via
`LOG_DIR`) - **check the log file first** when something goes wrong. `handlers/error.py`
catches any exception a command handler raises, replies to the chat with a generic message,
and logs the full traceback; the real cause is only visible in the log, never in the chat.

Set `LOG_LEVEL=DEBUG` for verbose mode: `activity_log.py`'s `log_incoming()` (called once,
centrally, from `handlers/observe.py` since it sees every update) and `reply()` (used by every
handler instead of calling `update.message.reply_text()` directly) log every interaction with
chat/user context (id, username, chat type/title). Only `fairsharebot`'s own logger honors
this - `python-telegram-bot`'s transport-level DEBUG logging is unconditionally capped at
WARNING in `logging_conf.py`, since it fires on every long-poll cycle regardless of activity
and would drown out anything useful.

The SQLite file at `./data/fairsharebot.sqlite3` (configurable via `DB_PATH`) is the only
persisted state. Don't delete it (or the `data/`/`logs/` directories) while the bot is
running unless you intend to wipe its data - `get_connection()` opens a fresh connection per
command rather than holding one open, so a mid-run deletion doesn't crash the process, it
just silently starts writing into a brand-new schema-less file on the next command (surfaces
as `sqlite3.OperationalError: no such table: ...`).

## Project layout

```
fairsharebot/
  __main__.py       # entrypoint: python -m fairsharebot
  config.py         # env-based settings (Settings dataclass)
  logging_conf.py   # console + rotating file logging setup
  activity_log.py   # log_incoming()/reply() - the verbose-mode logging helpers
  identity.py       # resolves @mentions/replies/text_mentions to known users
  settlement.py     # balance and settlement-transfer computation
  db/               # schema.sql + repository layer (sqlite)
  handlers/         # one module per command, plus observe.py and error.py
  utils/            # /pay grammar parsing, message formatting
tests/
assets/              # logo + BotFather copy (description, commands, etc.)
```

## Conventions

- Money is always integer cents internally, parsed from user input via `decimal.Decimal`.
- Repository functions (`db/*_repo.py`) take an open `sqlite3.Connection` and do no I/O of
  their own beyond that connection - callers own the `get_connection()` context manager.
- `settlement.py` functions are pure (no I/O), which is what makes them cheap to unit test.
- Handlers always reply via `activity_log.reply(update, text)`, never
  `update.message.reply_text(...)` directly - `update.message` is `None` for edited-message
  updates (only `effective_message` is populated then), which used to crash every handler.
- Split-participant dedup happens after resolving a ref to a user id, not on the ref string
  (see `_custom_splits` in `handlers/payment.py`) - `me` and `@own_username` are different
  strings that can resolve to the same person.
