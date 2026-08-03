from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ..models import Transfer


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def format_token_amount(base_units: int, *, decimals: int = 18) -> str:
    """base_units is an integer in the token's smallest unit (wei-equivalent).
    Uses Decimal, not float division, for the same reason format_cents avoids
    floats - this is real value moving, not a display-only approximation."""
    value = Decimal(base_units).scaleb(-decimals)
    text = format(value, "f")  # fixed-point, never scientific notation
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


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
