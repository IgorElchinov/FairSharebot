FairSharebot Implementation Plan

 Context

 FairSharebot is meant to be a lightweight Telegram bot that makes splitting shared
 expenses on trips painless: add it to a group chat, record payments as they happen,
 and have it compute the minimum set of transactions needed to settle up when the
 trip ends — without anyone registering or doing setup. The repo currently only has
 README.md, IDEA.md, PROMPTS.md, and Claude.md — no code exists yet, so this
 plan defines the whole system from scratch.

 Decisions locked in with the user before writing this plan:
 - Splits: support equal splits and custom splits (exact amounts or weighted
 shares) from the first working version, not equal-only.
 - Participants: identified implicitly from activity (whoever pays or is named
 in a payment becomes a tracked participant) — no explicit /join step.
 - Reminders: explicitly deferred to a later phase; MVP just needs to not
 preclude adding it later.
 - Deployment: local long-polling only for now (python -m fairsharebot), no
 Docker/webhook work in this pass.

 Tech stack

 - python-telegram-bot (PTB) v21.x, async. Chosen over aiogram and
 pyTelegramBotAPI because its Update/Message/MessageEntity objects are
 plain network-free dataclasses that can be hand-built or loaded from JSON
 fixtures in tests (no live Telegram connection needed), and it ships a
 built-in JobQueue that the deferred reminders phase can reuse later for free.
 - Storage: stdlib sqlite3, no ORM. A handful of small tables and queries
 doesn't justify SQLAlchemy; a single-file DB keeps the bot "lightweight" as
 the project intends. Raw DDL in schema.sql, applied idempotently
 (CREATE TABLE IF NOT EXISTS) at startup, plus a thin repository layer of
 typed functions — no query builder. Money is stored as integer cents
 (parsed via decimal.Decimal) to avoid float rounding bugs.
 - Config: python-dotenv loads BOT_TOKEN from .env (gitignored;
 .env.example checked in), fail-fast if missing.
 - Testing: pytest + pytest-asyncio, no network calls anywhere in the
 suite.

 Project layout

 fairsharebot/
   __main__.py               # entrypoint: python -m fairsharebot, runs polling
   config.py                 # Settings: BOT_TOKEN, DB_PATH, LOG_LEVEL
   errors.py                 # NoOpenTripError, UnknownUserError, InvalidSplitError, ...
   models.py                 # dataclasses: User, Trip, Payment, PaymentSplit, Transfer
   identity.py               # mention/reply/text_mention -> user_id resolution
   settlement.py             # pure: compute_balances(), compute_transfers()
   db/
     connection.py           # get_connection() context manager, PRAGMAs
     schema.sql               # DDL for all tables + indexes
     init_db.py                # applies schema.sql at startup
     users_repo.py              # upsert_user, upsert_chat_user, resolve_username
     trips_repo.py                # create_trip, get_open_trip, close_trip, list_trips
     payments_repo.py              # add_payment, add_splits, get_trip_payments/splits
   handlers/
     observe.py               # low-priority handler: opportunistically upserts users
     start_help.py             # /start, /help
     trip.py                    # /starttrip, /closetrip, /trips
     payment.py                  # /pay (equal, exact, shares grammars)
     balance.py                   # /balance
   utils/
     parsing.py                # command text + entities -> ParsedPayment
     formatting.py               # money formatting, balance/settlement rendering
 tests/
   conftest.py                 # tmp sqlite fixture, fake Update/User/Message factories
   test_settlement.py
   test_identity.py
   test_parsing.py
   test_repository.py
   test_handlers_trip.py
   test_handlers_payment.py
 .env.example
 requirements.txt

 Data model

 All monetary values in integer cents.

 CREATE TABLE users (
   telegram_user_id INTEGER PRIMARY KEY,
   username          TEXT,        -- normalized lowercase, no leading '@'
   display_name      TEXT NOT NULL,
   updated_at        TEXT NOT NULL
 );
 CREATE INDEX idx_users_username ON users(username);

 -- scopes username resolution to "people seen in THIS chat"
 CREATE TABLE chat_users (
   chat_id       INTEGER NOT NULL,
   user_id       INTEGER NOT NULL REFERENCES users(telegram_user_id),
   last_seen_at  TEXT NOT NULL,
   PRIMARY KEY (chat_id, user_id)
 );

 CREATE TABLE trips (
   id          INTEGER PRIMARY KEY AUTOINCREMENT,
   chat_id     INTEGER NOT NULL,
   name        TEXT NOT NULL,
   status      TEXT NOT NULL CHECK (status IN ('open','closed')) DEFAULT 'open',
   currency    TEXT NOT NULL DEFAULT 'USD',   -- display only, no conversion
   created_by  INTEGER NOT NULL REFERENCES users(telegram_user_id),
   created_at  TEXT NOT NULL,
   closed_at   TEXT
 );
 -- enforces "one open trip per chat" at the DB level
 CREATE UNIQUE INDEX idx_trips_one_open_per_chat ON trips(chat_id) WHERE status = 'open';

 CREATE TABLE payments (
   id            INTEGER PRIMARY KEY AUTOINCREMENT,
   trip_id       INTEGER NOT NULL REFERENCES trips(id),
   payer_id      INTEGER NOT NULL REFERENCES users(telegram_user_id),
   amount_cents  INTEGER NOT NULL,
   description   TEXT NOT NULL DEFAULT '',
   split_type    TEXT NOT NULL CHECK (split_type IN ('equal','exact','shares')),
   created_by    INTEGER NOT NULL REFERENCES users(telegram_user_id),
   created_at    TEXT NOT NULL,
   deleted_at    TEXT   -- unused in MVP; reserved so /cancelpayment needs no migration later
 );
 CREATE INDEX idx_payments_trip ON payments(trip_id);

 CREATE TABLE payment_splits (
   id                    INTEGER PRIMARY KEY AUTOINCREMENT,
   payment_id            INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
   user_id               INTEGER NOT NULL REFERENCES users(telegram_user_id),
   weight                REAL,     -- only for split_type='shares'
   computed_amount_cents INTEGER NOT NULL
 );
 CREATE INDEX idx_splits_payment ON payment_splits(payment_id);

 trips_repo.create_trip() checks get_open_trip(chat_id) first and returns a
 friendly error before ever hitting the unique index, so users never see a raw
 SQL constraint failure.

 Reminders extension point (not built now): a future settlements table
 (trip_id, from_user_id, to_user_id, amount_cents, paid_back, paid_back_at) can
 be added purely additively later, since compute_transfers() is a pure function
 recomputed on demand — nothing today needs to persist the transfer plan.

 Identity resolution (the Telegram mention problem)

 Telegram only embeds a full User object (with numeric ID) in a message entity
 when the mentioned user has no username (text_mention). A plain @username
 mention is delivered as bare text — the bot cannot resolve it to an ID unless it
 has already seen that user in the chat.

 Population (handlers/observe.py, a low-priority non-blocking handler on all
 messages) upserts users/chat_users from every source that carries a real
 User object: the sender, reply_to_message.from_user, any text_mention
 entities, and new_chat_members.

 Resolution (identity.py, used when parsing /pay), in priority order:
 1. Reply-to-message sender (always resolvable, most reliable — called out in /help).
 2. text_mention entity (resolves directly).
 3. Plain @username mention — normalized and looked up in chat_users scoped to
 the current chat; if not found, raise UnknownUserError.
 4. me keyword → the command sender.

 Validation resolves all participants before any DB write, so a failure never
 leaves a partial payment. Error message is explicit about the real constraint:
 "I don't know who @xyz is yet — they need to send a message in this chat (or you
 can reply to one of their messages) before you can split with them."

 Commands

 All commands operate implicitly on the chat's open trip — no trip ID needed.

 ┌────────────────────┬──────────────────────────────────────────────┬────────────────────────────────────────────────────────────────┐
 │      Command       │                   Example                    │                            Behavior                            │
 ├────────────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ /start, /help      │                                              │ Greeting / full command reference with examples                │
 ├────────────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ /starttrip         │ /starttrip Barcelona weekend                 │ Opens a trip; errors if one's already open                     │
 ├────────────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ /pay equal         │ /pay 90 taxi for @alice @bob                 │ Payer = sender; split evenly among sender + mentions           │
 ├────────────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ /pay exact         │ /pay 90 dinner split me=30 @alice=30 @bob=30 │ Amounts must sum to total (validated)                          │
 ├────────────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ /pay shares        │ /pay 90 rent shares me=1 @alice=1 @bob=2     │ Weighted split, deterministic cent rounding                    │
 ├────────────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ /balance           │                                              │ Net balance per participant + live settlement preview          │
 ├────────────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ /closetrip         │                                              │ Locks the trip, computes and posts final settlement            │
 ├────────────────────┼──────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
 │ /trips, /trip <id> │                                              │ List past trips / recompute a specific closed trip's breakdown │
 └────────────────────┴──────────────────────────────────────────────┴────────────────────────────────────────────────────────────────┘

 Deferred/out of scope (documented in /help and code, not built now): payer
 override (paidby=), reminders, receipt OCR, multi-currency conversion.
 (/cancelpayment, originally planned for this deferred list, was built ahead
 of schedule using the deleted_at column reserved for it below.)

 Settlement algorithm (settlement.py, pure functions, no I/O)

 - compute_balances(payments, splits) -> {user_id: net_cents}: payer gains the
 full amount, each split participant loses their share.
 - compute_transfers(balances) -> list[Transfer]: greedy largest-debtor /
 largest-creditor matching — repeatedly settle min(credit, debt) between the
 biggest creditor and biggest debtor until all balances are zero.
 - Honesty note (goes in the module docstring): minimizing transaction count
 exactly is NP-hard in general; the greedy heuristic is what virtually every
 Splitwise-style tool uses, always produces at most n-1 transfers, and is
 usually optimal for realistic group sizes — but it is not provably minimal in
 every case. An exact solver is out of scope.
 - Invariant tests: sum(balances.values()) == 0 always; transfers fully
 reconcile the original balances.

 Testing strategy

 - test_settlement.py — equal/exact/shares splits, rounding edge cases,
 len(transfers) <= n-1, reconciliation.
 - test_identity.py — hand-built/JSON-fixture telegram.Update objects
 covering reply-to, text_mention, known @mention, and unknown @mention
 error path.
 - test_parsing.py — grammar edge cases and malformed input.
 - test_repository.py — sqlite tmp_path/:memory: DB with schema.sql
 applied; one-open-trip-per-chat enforcement, add/soft-delete round trips.
 - test_handlers_*.py — call handler coroutines directly with a constructed
 Update (reply_text = AsyncMock()), asserting on the reply and on DB state
 via the repository layer.
 - Manual smoke test: run python -m fairsharebot with a real BotFather token in
 a private test group (documented in README, not automated).

 Phased build order (each phase ends with a working, testable checkpoint)

 0. Scaffolding — package layout, requirements.txt, config.py, DB schema
   - connection + init, __main__.py wiring /start//help only, .env.example.
 1. Trip lifecycle + identity capture — observe.py, /starttrip,
 /closetrip (status flip only), one-open-trip enforcement + tests.
 2. Payments, equal split — identity.py, /pay ... for @mentions,
 persistence, /balance shows raw balances.
 3. Custom splits — exact and shares grammars, validation, rounding.
 4. Settlement — settlement.py wired into /balance (preview) and
losetrip (final); invariant tests.
 5. History — /trips, /trip <id> on-demand recomputation.
 6. Polish — real /help examples, error handler, input validation, README
 usage walkthrough, .gitignore for .env/*.sqlite3.
 7. Future (TODOs only, not built now) — reminders via JobQueue +
ttlements table, payer override, receipt OCR,
 multi-currency, provably-optimal settlement for large groups.

itical files

fairsharebot/db/schema.sql — the data model
fairsharebot/identity.py — mention resolution, the trickiest correctness piece
 - fairsharebot/settlement.py — debt-simplification algorithm
 - fairsharebot/handlers/payment.py — the core /pay command (all three split grammars)
fairsharebot/__main__.py — wiring/entrypoint

 Verification

pytest -q after each phase — all new tests plus prior phases' tests green.
 - Manual smoke test at the end of Phase 2 onward: create a BotFather test bot,
 run python -m fairsharebot locally, add it to a private test group, and walk
 through /starttrip → a few /pay variants → /balance → /closetrip to
 confirm the settlement output matches hand-calculated expectations.
 - After Phase 4, specifically verify the settlement invariant by hand on a
 3-4 person trip with mixed equal/exact/shares payments: total paid == total
 owed == sum of computed transfers.