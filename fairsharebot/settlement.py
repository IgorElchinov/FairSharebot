from __future__ import annotations

from .models import Payment, PaymentSplit


def compute_balances(payments: list[Payment], splits: list[PaymentSplit]) -> dict[int, int]:
    """Net balance per user, in cents. Positive = owed money, negative = owes money.

    A payer's balance goes up by the full amount they paid; each split
    participant's balance goes down by their share. Split amounts are
    constructed (at payment time) to sum exactly to the payment total, so
    sum(balances.values()) is always 0.
    """
    balances: dict[int, int] = {}
    for payment in payments:
        balances[payment.payer_id] = balances.get(payment.payer_id, 0) + payment.amount_cents
    for split in splits:
        balances[split.user_id] = balances.get(split.user_id, 0) - split.computed_amount_cents
    return balances
