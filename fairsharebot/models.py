from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class User:
    id: int
    username: str | None
    display_name: str


@dataclass(frozen=True)
class Trip:
    id: int
    chat_id: int
    name: str
    status: str
    currency: str
    created_by: int
    created_at: str
    closed_at: str | None
    settlement_mode: str = "cash"  # 'cash' or 'token'
    token_address: str | None = None


@dataclass(frozen=True)
class Payment:
    id: int
    trip_id: int
    payer_id: int
    amount_cents: int
    description: str
    split_type: str
    created_by: int
    created_at: str


@dataclass(frozen=True)
class PaymentSplit:
    id: int
    payment_id: int
    user_id: int
    weight: float | None
    computed_amount_cents: int


@dataclass(frozen=True)
class SplitInput:
    """A split row to be persisted, before it has a database id."""

    user_id: int
    computed_amount_cents: int
    weight: float | None = None


@dataclass(frozen=True)
class Transfer:
    """One suggested payment in a settlement plan: from_user_id owes to_user_id."""

    from_user_id: int
    to_user_id: int
    amount_cents: int


@dataclass(frozen=True)
class Wallet:
    """The wallet a user's token-mode payments currently settle through."""

    telegram_user_id: int
    address: str
    custody_type: str  # 'custodial' or 'external'
    allowance_granted_at: str | None
    linked_at: str
    updated_at: str


@dataclass(frozen=True)
class WalletLinkChallenge:
    """Proof-of-ownership state for /linkwallet."""

    token: str
    telegram_user_id: int
    nonce: str
    status: str  # 'pending', 'verified', or 'expired'
    created_at: str
    expires_at: str
    verified_address: str | None


@dataclass(frozen=True)
class ClosingSettlementResult:
    """What /closetrip's residual-netting safety net actually managed to
    submit vs. couldn't, so the reply can tell the group which is which."""

    submitted: list[Transfer]
    failed: list[Transfer]


@dataclass(frozen=True)
class CryptoTransfer:
    """One on-chain settlement attempt, tracked so /closetrip can net residuals."""

    id: int
    trip_id: int
    payment_id: int | None
    from_user_id: int
    to_user_id: int
    from_address: str
    to_address: str
    token_amount: int
    tx_hash: str | None
    status: str  # 'pending', 'confirmed', or 'failed'
    error_message: str | None
    created_at: str
    confirmed_at: str | None
