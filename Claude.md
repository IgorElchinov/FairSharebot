# FairSharebot

FairSharebot is lightweight easy-to-use telegram bot that manages your shared spendings during trips.

See @vibecoding/IDEA.md for the product idea and @vibecoding/PLAN.md for the implementation plan
(data model, command set, settlement algorithm, phased build order).

## Stack

- Python 3.11+, `python-telegram-bot` (PTB) v21.x async, stdlib `sqlite3` (no ORM).
- Run locally: `python -m fairsharebot` (long polling; copy `.env.example` to `.env` and set `BOT_TOKEN` first).
- Tests: `pytest -q` (dev deps in `requirements-dev.txt`).
