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
