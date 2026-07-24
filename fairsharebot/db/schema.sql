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
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id     INTEGER NOT NULL,
  name        TEXT NOT NULL,
  status      TEXT NOT NULL CHECK (status IN ('open', 'closed')) DEFAULT 'open',
  currency    TEXT NOT NULL DEFAULT 'USD',   -- display only, no conversion
  created_by  INTEGER NOT NULL REFERENCES users(telegram_user_id),
  created_at  TEXT NOT NULL,
  closed_at   TEXT
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
  deleted_at    TEXT   -- unused in MVP; reserved so a future /cancelpayment
                        -- needs no schema migration (queries filter WHERE deleted_at IS NULL)
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
