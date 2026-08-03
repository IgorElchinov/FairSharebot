from __future__ import annotations

from decimal import Decimal, InvalidOperation

TOKEN_DECIMALS = 18

# FairSharebot's token is pegged 1 token-cent = 1 real cent by fixed
# convention, not a live exchange rate or oracle - that lets every split
# already computed in cents (equal/exact/shares, all in utils/parsing.py)
# convert directly to on-chain base units with no second currency concept.
# A real backing/exchange-rate story is out of scope here, same as
# multi-currency conversion in the cash flow (see CLAUDE.md/PLAN.md).
_CENTS_TO_BASE_UNITS_SCALE = 10 ** (TOKEN_DECIMALS - 2)


def cents_to_token_units(cents: int) -> int:
    return cents * _CENTS_TO_BASE_UNITS_SCALE


def token_units_to_cents(units: int) -> int:
    """Inverse of cents_to_token_units - exact for any amount that actually
    came from that function, since the peg is an integer scale factor."""
    return units // _CENTS_TO_BASE_UNITS_SCALE


def parse_token_amount(text: str) -> int:
    """Parses a whole/fractional token amount (as typed in /minttoken) into
    base units. Decimal, not float, for the same reason utils/parsing.py
    parses money amounts via Decimal - this is real value, not a display
    approximation."""
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"Not a valid number: {text!r}") from None
    if amount <= 0:
        raise ValueError("Amount must be positive")
    return int(amount.scaleb(TOKEN_DECIMALS))
