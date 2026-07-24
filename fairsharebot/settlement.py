from __future__ import annotations

import heapq

from .models import Payment, PaymentSplit, Transfer


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


def compute_transfers(balances: dict[int, int]) -> list[Transfer]:
    """Suggests who should pay whom to settle all balances, minimizing (heuristically)
    the number of transactions: repeatedly match the largest creditor against the
    largest debtor until everyone nets to zero.

    Minimizing the transaction count *exactly* is NP-hard in general (it's a
    variant of the subset-sum/exact-cover family). This greedy largest-debtor/
    largest-creditor heuristic is the same approach virtually every Splitwise-style
    tool uses: it always produces at most n-1 transfers for n participants with a
    nonzero balance, and is usually optimal or very close to it for realistic group
    sizes - but it is not provably minimal in every pathological case. An exact
    solver is out of scope.
    """
    creditors = [(-amount, user_id) for user_id, amount in balances.items() if amount > 0]
    debtors = [(amount, user_id) for user_id, amount in balances.items() if amount < 0]
    heapq.heapify(creditors)
    heapq.heapify(debtors)

    transfers: list[Transfer] = []
    while creditors and debtors:
        neg_credit, creditor_id = heapq.heappop(creditors)
        debt, debtor_id = heapq.heappop(debtors)
        credit = -neg_credit
        owed = -debt

        settled = min(credit, owed)
        transfers.append(Transfer(from_user_id=debtor_id, to_user_id=creditor_id, amount_cents=settled))

        remaining_credit = credit - settled
        remaining_debt = owed - settled
        if remaining_credit > 0:
            heapq.heappush(creditors, (-remaining_credit, creditor_id))
        if remaining_debt > 0:
            heapq.heappush(debtors, (-remaining_debt, debtor_id))

    return transfers
