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
