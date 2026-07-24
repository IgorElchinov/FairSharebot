<p align="center">
  <img src="assets/logo.png" alt="FairSharebot logo" width="120" height="120">
</p>

<h1 align="center">FairSharebot</h1>

<p align="center">
  A lightweight Telegram bot that splits shared trip expenses - no registration, no spreadsheets.
</p>

Add it to a group chat, start a trip, log payments as they happen, and close the trip when
you're done. FairSharebot works out the fewest payments needed to settle everyone up.

This project is vibe-coded. [See VIBECODING.md for more details.](vibecoding/VIBECODING.md)
The implementation plan lives in [vibecoding/PLAN.md](vibecoding/PLAN.md).

## Setup

Requires Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt   # or requirements.txt for a non-dev install

cp .env.example .env
# edit .env and set BOT_TOKEN to a token from @BotFather
```

Run it:

```bash
python -m fairsharebot
```

This starts the bot with long polling - no public URL or webhook needed. A SQLite database
is created automatically at `./data/fairsharebot.sqlite3` (configurable via `DB_PATH`).

## Usage

All commands operate on the chat's currently open trip - there's no trip ID to pass around,
since only one trip can be open per chat at a time.

| Command | Example | What it does |
|---|---|---|
| `/starttrip [name]` | `/starttrip Barcelona weekend` | Starts a trip in this chat |
| `/pay` (equal split) | `/pay 90 taxi for @alice @bob` | Payer = you; split evenly among you + mentions |
| `/pay` (exact amounts) | `/pay 90 dinner split me=30 @alice=30 @bob=30` | Amounts must sum to the total |
| `/pay` (weighted split) | `/pay 90 rent shares me=1 @alice=1 @bob=2` | Split proportionally to weights |
| `/balance` | `/balance` | Current balances + a live settlement preview |
| `/closetrip` | `/closetrip` | Closes the trip and posts the final settlement |
| `/trips` | `/trips` | Lists past trips in this chat, with totals |
| `/trip <id>` | `/trip 3` | Full breakdown and settlement for any trip |

Tips:
- Reply to someone's message with `/pay` to include them without needing to `@mention` them.
- `me`/`@username` refer to yourself or a known chat member - exact and weighted splits can't
  reference someone who has no Telegram username *and* hasn't been `@mentioned`/replied to yet
  (there's no unambiguous way to write that as a `ref=value` token).
- Someone needs to have sent at least one message, been replied to, or been `@mentioned` in
  this chat before you can split a payment with them by `@username` - see the privacy mode
  note below if you want that to work from literally anyone's first message.

Run `/help` in the chat any time for the full command reference.

## Configuring the bot in BotFather

Message **@BotFather** to finish setting the bot up:

- `/setuserpic` - upload [`assets/logo.png`](assets/logo.png)
- `/setdescription` - paste [`assets/botfather/description.txt`](assets/botfather/description.txt)
- `/setshortdescription` - paste [`assets/botfather/short_description.txt`](assets/botfather/short_description.txt)
- `/setabouttext` - paste [`assets/botfather/about.txt`](assets/botfather/about.txt)
- `/setcommands` - paste [`assets/botfather/commands.txt`](assets/botfather/commands.txt) verbatim,
  so Telegram shows the `/` command menu with descriptions
- `/setprivacy` - **Disable**, so the bot can learn about chat members from any message, not
  just commands, replies to it, or `@mentions` of it. Without this, someone can only be
  `@username`-mentioned in a `/pay` after they've sent a command themselves.

## Testing

```bash
pytest -q
```

No network access or real Telegram credentials are needed - handler tests construct `Update`
objects directly, and the settlement/parsing logic is tested as pure functions.

## Project layout

See [vibecoding/PLAN.md](vibecoding/PLAN.md) for the full architecture (data model, the
Telegram mention-resolution problem, the settlement algorithm, and the phased build order).

```
fairsharebot/
  __main__.py       # entrypoint: python -m fairsharebot
  config.py         # env-based settings
  identity.py       # resolves @mentions/replies/text_mentions to known users
  settlement.py     # balance and settlement-transfer computation
  db/               # schema + repository layer (sqlite)
  handlers/         # one module per command
  utils/            # /pay grammar parsing, message formatting
tests/
```

## Known limitations / not yet built

- No reminders for who still owes money (planned; see `vibecoding/PLAN.md`).
- No way to edit or cancel a mistaken payment yet.
- No receipt OCR, no multi-currency conversion.
- Settlement minimizes the transaction count with a greedy heuristic, not an exact solver
  (see the docstring in `fairsharebot/settlement.py` for why that's a reasonable tradeoff).
