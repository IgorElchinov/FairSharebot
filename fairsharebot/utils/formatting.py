from __future__ import annotations

from datetime import datetime

from ..models import Transfer


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def format_date(iso_timestamp: str) -> str:
    return datetime.fromisoformat(iso_timestamp).strftime("%Y-%m-%d")


def format_transfers(transfers: list[Transfer], names: dict[int, str]) -> str:
    if not transfers:
        return "No transfers needed - everyone's settled up."

    lines = [
        f"{names.get(t.from_user_id, f'user {t.from_user_id}')} pays "
        f"{names.get(t.to_user_id, f'user {t.to_user_id}')} {format_cents(t.amount_cents)}"
        for t in transfers
    ]
    return "\n".join(lines)
