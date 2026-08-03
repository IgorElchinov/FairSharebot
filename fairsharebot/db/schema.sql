-- All monetary values are stored as integer cents.

CREATE TABLE IF NOT EXISTS users (
  telegram_user_id INTEGER PRIMARY KEY,
  username          TEXT,        -- normalized: lowercase, no leading '@'; nullable
  display_name      TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Scopes username resolution to "people seen in THIS chat" rather than every
-- user the bot has ever observed anywhere.
CREATE TABLE IF NOT EXISTS chat_users (
  chat_id       INTEGER NOT NULL,
  user_id       INTEGER NOT NULL REFERENCES users(telegram_user_id),
  last_seen_at  TEXT NOT NULL,
  PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS trips (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id          INTEGER NOT NULL,
  name             TEXT NOT NULL,
  status           TEXT NOT NULL CHECK (status IN ('open', 'closed')) DEFAULT 'open',
  currency         TEXT NOT NULL DEFAULT 'USD',   -- display only, no conversion
  settlement_mode  TEXT NOT NULL CHECK (settlement_mode IN ('cash', 'token')) DEFAULT 'cash',
  token_address    TEXT,   -- ERC-20 this trip settles in; NULL for cash trips
  created_by       INTEGER NOT NULL REFERENCES users(telegram_user_id),
  created_at       TEXT NOT NULL,
  closed_at        TEXT
);

-- Enforces "one open trip per chat" at the DB level.
CREATE UNIQUE INDEX IF NOT EXISTS idx_trips_one_open_per_chat
  ON trips(chat_id) WHERE status = 'open';

CREATE TABLE IF NOT EXISTS payments (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  trip_id       INTEGER NOT NULL REFERENCES trips(id),
  payer_id      INTEGER NOT NULL REFERENCES users(telegram_user_id),
  amount_cents  INTEGER NOT NULL,
  description   TEXT NOT NULL DEFAULT '',
  split_type    TEXT NOT NULL CHECK (split_type IN ('equal', 'exact', 'shares')),
  created_by    INTEGER NOT NULL REFERENCES users(telegram_user_id),
  created_at    TEXT NOT NULL,
  deleted_at    TEXT   -- set by /cancelpayment; queries filter WHERE deleted_at IS NULL
);
CREATE INDEX IF NOT EXISTS idx_payments_trip ON payments(trip_id);

CREATE TABLE IF NOT EXISTS payment_splits (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  payment_id            INTEGER NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
  user_id               INTEGER NOT NULL REFERENCES users(telegram_user_id),
  weight                REAL,     -- only meaningful for split_type='shares'
  computed_amount_cents INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_splits_payment ON payment_splits(payment_id);

-- The wallet a user's token-mode payments currently settle through. One row
-- per user; custody_type flips from 'custodial' to 'external' via /linkwallet.
CREATE TABLE IF NOT EXISTS wallets (
  telegram_user_id      INTEGER PRIMARY KEY REFERENCES users(telegram_user_id),
  address               TEXT NOT NULL,
  custody_type          TEXT NOT NULL CHECK (custody_type IN ('custodial', 'external')),
  allowance_granted_at  TEXT,   -- NULL until the standing-max-allowance permit tx confirms
  linked_at             TEXT NOT NULL,
  updated_at            TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_wallets_address ON wallets(address);

-- Append-only ledger of every custodial wallet ever derived for a user, kept
-- separate from `wallets` so /exportkey can still re-derive a user's original
-- custodial key even after they've switched to an external wallet via
-- /linkwallet. derivation_index is a sequential counter (not derived from
-- telegram_user_id), allocated transactionally as MAX(derivation_index) + 1.
CREATE TABLE IF NOT EXISTS custodial_wallets (
  telegram_user_id  INTEGER NOT NULL REFERENCES users(telegram_user_id),
  derivation_index  INTEGER NOT NULL UNIQUE,
  address           TEXT NOT NULL UNIQUE,
  created_at        TEXT NOT NULL,
  PRIMARY KEY (telegram_user_id, derivation_index)
);

-- Proof-of-ownership state for /linkwallet: the bot DMs a signing-page link
-- embedding `token`; the page has the wallet sign `nonce` and relays the
-- signature back for verification.
CREATE TABLE IF NOT EXISTS wallet_link_challenges (
  token             TEXT PRIMARY KEY,
  telegram_user_id  INTEGER NOT NULL REFERENCES users(telegram_user_id),
  nonce             TEXT NOT NULL,
  status            TEXT NOT NULL CHECK (status IN ('pending', 'verified', 'expired')) DEFAULT 'pending',
  created_at        TEXT NOT NULL,
  expires_at        TEXT NOT NULL,
  verified_address  TEXT
);

-- Ledger of every on-chain settlement attempt for a token-mode trip. Drives
-- /closetrip's residual-netting safety net: confirmed rows are subtracted
-- from the off-chain balance to find what still needs to move on-chain.
-- token_amount is base units (18 decimals) stored as a decimal string, not
-- INTEGER/REAL - sqlite's 64-bit int can overflow at 18 decimals for large
-- trips, and REAL would reintroduce the float rounding bugs amount_cents was
-- designed to avoid. Convert to a Python int in the repo layer.
CREATE TABLE IF NOT EXISTS crypto_transfers (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  trip_id        INTEGER NOT NULL REFERENCES trips(id),
  payment_id     INTEGER REFERENCES payments(id),   -- NULL for a /closetrip netting transfer
  from_user_id   INTEGER NOT NULL REFERENCES users(telegram_user_id),
  to_user_id     INTEGER NOT NULL REFERENCES users(telegram_user_id),
  from_address   TEXT NOT NULL,   -- snapshot at execution time, not a live join to `wallets`
  to_address     TEXT NOT NULL,   -- (so a later wallet switch can't corrupt historical rows)
  token_amount   TEXT NOT NULL,
  tx_hash        TEXT,
  status         TEXT NOT NULL CHECK (status IN ('pending', 'confirmed', 'failed')) DEFAULT 'pending',
  error_message  TEXT,
  created_at     TEXT NOT NULL,
  confirmed_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_crypto_transfers_trip ON crypto_transfers(trip_id);
CREATE INDEX IF NOT EXISTS idx_crypto_transfers_status ON crypto_transfers(status);
