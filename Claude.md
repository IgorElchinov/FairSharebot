# FairSharebot

FairSharebot is a lightweight Telegram bot that splits shared trip expenses - no
registration, no spreadsheets. See @vibecoding/IDEA.md for the original product idea and
@vibecoding/PLAN.md for the implementation plan (data model, the Telegram mention-resolution
approach, the settlement algorithm, and the phased build order).

Phases 0-6 of the plan are done: trip lifecycle, all three `/pay` split types (equal, exact,
weighted), balances, final settlement, trip history, and polish (error handler, input
validation, logging, branding). `/cancelpayment` (soft-delete via the `payments.deleted_at`
column reserved for it in the schema) has also been built ahead of its originally-planned
phase. Remaining work from the original plan is the rest of the explicitly-deferred future
list (reminders, payer override, receipt OCR, multi-currency) - nothing there is started.

A second, opt-in-per-trip feature has since been added on top: **token-mode trips**, which
settle a trip's splits with FairSharebot's own ERC-20 token on Base instead of just tracking
cash balances. `/starttrip` and cash trips are completely unaffected - see "Token mode
(crypto payments)" below for how it works and where the code lives.

## Stack

- Python 3.11+, `python-telegram-bot` (PTB) v21.x async (with the `job-queue` extra, for
  token-mode's polling jobs), stdlib `sqlite3` (no ORM).
- Setup: copy `.env.example` to `.env`, set `BOT_TOKEN` (from @BotFather). Token mode needs a
  further block of chain env vars, all optional and gated behind `WALLET_MASTER_MNEMONIC` being
  set at all (see "Token mode" below) - a cash-only deployment can ignore them entirely.
- Run locally: `python -m fairsharebot` (long polling, no webhook/public URL needed).
- Tests: `pytest -q` (dev deps in `requirements-dev.txt`). No network access needed - handler
  tests build `Update`/`Context` objects directly (see `tests/conftest.py`), and
  parsing/settlement logic is tested as pure functions. The chain layer is tested the same way,
  against a hand-rolled `FakeChainClient` (also in `tests/conftest.py`) implementing
  `ChainClientProtocol` - real chain behavior is validated separately against a local `anvil`
  node or Base Sepolia, never in the pytest suite. Contracts have their own `forge test` suite
  in `contracts/` (Foundry; `forge install` after cloning, `lib/` isn't committed).

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
  config.py         # env-based settings (Settings + optional ChainSettings dataclass)
  logging_conf.py   # console + rotating file logging setup
  activity_log.py   # log_incoming()/reply() - the verbose-mode logging helpers
  identity.py       # resolves @mentions/replies/text_mentions to known users
  settlement.py     # balance and settlement-transfer computation (cash)
  db/               # schema.sql + repository layer (sqlite), incl. crypto_repo.py
  handlers/         # one module per command, plus observe.py, error.py, jobs.py (JobQueue)
  utils/            # /pay grammar parsing, money/token formatting
  chain/            # token-mode: wallets.py (HD derivation), permit.py (EIP-712),
                     #   allowance.py (ensure_allowance), client.py (ChainClientProtocol +
                     #   Web3ChainClient), settlement_service.py (settle_payment_onchain,
                     #   run_closing_settlement), units.py (cents <-> token base units)
  webapp/            # standalone /linkwallet signing-page web app - a SEPARATE process
                     #   (python -m fairsharebot.webapp), not imported by the bot itself
contracts/          # FairShareToken + Settlement (Solidity, Foundry project)
deployments/        # deployed contract addresses per network (base-sepolia.json, ...)
tests/
assets/              # logo + BotFather copy (description, commands, etc.)
```

## Conventions

- Money is always integer cents internally, parsed from user input via `decimal.Decimal`.
  Token amounts are base units (18 decimals) as a Python `int`, converted via
  `chain/units.py`'s `cents_to_token_units`/`token_units_to_cents` - the token is pegged 1
  token-cent = 1 real cent by fixed convention, not a live exchange rate.
- Repository functions (`db/*_repo.py`) take an open `sqlite3.Connection` and do no I/O of
  their own beyond that connection - callers own the `get_connection()` context manager. The
  chain layer's repo-like functions (`db/crypto_repo.py`) follow the same rule.
- `settlement.py` functions are pure (no I/O), which is what makes them cheap to unit test.
- Handlers always reply via `activity_log.reply(update, text)`, never
  `update.message.reply_text(...)` directly - `update.message` is `None` for edited-message
  updates (only `effective_message` is populated then), which used to crash every handler. Pass
  `redact=True` for any reply that can contain a secret (only `/exportkey` does today) - the
  message still sends, it just never reaches the log file, including under `LOG_LEVEL=DEBUG`.
- Split-participant dedup happens after resolving a ref to a user id, not on the ref string
  (see `_custom_splits` in `handlers/payment.py`) - `me` and `@own_username` are different
  strings that can resolve to the same person.

## Token mode (crypto payments)

Opt-in per trip via `/starttriptoken` instead of `/starttrip` (`trips.settlement_mode`). See the
README's "Token-mode trips" section for user-facing setup instructions (deploying contracts,
env vars, running the web app). Key things to know when touching this code:

- **Custody is hybrid.** Every user gets a custodial wallet automatically, deterministically
  HD-derived from `WALLET_MASTER_MNEMONIC` (`chain/wallets.py`) - the private key is never
  stored, only the `derivation_index`, recomputed on demand. `/linkwallet` swaps a user's active
  wallet for a self-custodied one (`fairsharebot/webapp`, a separate process); `/exportkey`
  (DM-only) re-derives and reveals a custodial key, which is why exporting it doesn't revoke
  the bot's own access - the mnemonic can always re-derive it again.
- **Settlement is allowance-based, not the bot signing arbitrary transfers.** Every wallet
  grants the `Settlement` contract a standing max allowance once (gaslessly, via EIP-2612
  `permit` - `chain/permit.py`, orchestrated by `chain/allowance.py`'s `ensure_allowance`).
  After that, the bot's relayer pulls funds via `Settlement.settleBatch`, which is
  **all-or-nothing per call** - one participant missing an allowance reverts the whole batch,
  which is why `settlement_service.py` filters ready-vs-not-ready participants before building
  each batch rather than submitting everyone and hoping.
- **Timing is hybrid.** `/pay` settles immediately (`settle_payment_onchain`); `/closetrip`
  nets whatever didn't actually confirm on-chain yet (`run_closing_settlement` - residual =
  full off-chain balance minus already-*confirmed* `crypto_transfers` rows, not a raw retry of
  failed rows, which would double-count anything superseded by a later payment).
  `handlers/jobs.py`'s `poll_pending_transfers` (every 15s) reconciles pending rows against
  chain receipts; a stuck tx times out after 10 minutes rather than polling forever.
- **The chain layer is swappable for tests** via `ChainClientProtocol` (`chain/client.py`) -
  `tests/conftest.py`'s `FakeChainClient` is what every offline test uses; `Web3ChainClient` is
  the real `AsyncWeb3` implementation, validated manually against a local `anvil` node (start
  one with `anvil`, deploy via `contracts/script/Deploy.s.sol`, point `BASE_RPC_URL` at
  `http://127.0.0.1:8545`) before trusting any change against real Base Sepolia funds.
- **Biggest structural risk, stated plainly** (see `chain/settlement_service.py`'s docstrings
  for more): the standing max allowance means a compromised relayer or contract-owner key can
  drain every wallet - custodial *and* linked - up to its allowance. Mitigated at this bot's
  scale by keeping the master seed, relayer key, and contract-owner key as three separate
  secrets, plus the `Settlement` contract's owner-only `pause()`. Not mitigated by a capped or
  auto-expiring allowance - that's a real trade-off made in exchange for zero-friction UX, not
  an oversight.
