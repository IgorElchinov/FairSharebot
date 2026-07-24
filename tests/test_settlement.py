from __future__ import annotations

from fairsharebot.models import Payment, PaymentSplit
from fairsharebot.settlement import compute_balances


def _payment(id_, payer_id, amount_cents) -> Payment:
    return Payment(
        id=id_,
        trip_id=1,
        payer_id=payer_id,
        amount_cents=amount_cents,
        description="",
        split_type="equal",
        created_by=payer_id,
        created_at="2026-01-01T00:00:00+00:00",
    )


def _split(id_, payment_id, user_id, computed_amount_cents) -> PaymentSplit:
    return PaymentSplit(
        id=id_,
        payment_id=payment_id,
        user_id=user_id,
        weight=None,
        computed_amount_cents=computed_amount_cents,
    )


def test_single_payment_equal_split_between_two():
    payments = [_payment(1, payer_id=1, amount_cents=1000)]
    splits = [_split(1, 1, user_id=1, computed_amount_cents=500), _split(2, 1, user_id=2, computed_amount_cents=500)]

    balances = compute_balances(payments, splits)

    assert balances == {1: 500, 2: -500}
    assert sum(balances.values()) == 0


def test_multiple_payments_reconcile_to_zero():
    payments = [
        _payment(1, payer_id=1, amount_cents=900),  # split 3 ways: 300/300/300
        _payment(2, payer_id=2, amount_cents=500),  # split 2 ways: 250/250
    ]
    splits = [
        _split(1, 1, user_id=1, computed_amount_cents=300),
        _split(2, 1, user_id=2, computed_amount_cents=300),
        _split(3, 1, user_id=3, computed_amount_cents=300),
        _split(4, 2, user_id=1, computed_amount_cents=250),
        _split(5, 2, user_id=2, computed_amount_cents=250),
    ]

    balances = compute_balances(payments, splits)

    # user 1: paid 900, owes 300 + 250 = 550 -> net +350
    # user 2: paid 500, owes 300 + 250 = 550 -> net -50
    # user 3: paid 0, owes 300 -> net -300
    assert balances == {1: 350, 2: -50, 3: -300}
    assert sum(balances.values()) == 0


def test_payer_splitting_only_with_self_nets_zero():
    payments = [_payment(1, payer_id=1, amount_cents=1000)]
    splits = [_split(1, 1, user_id=1, computed_amount_cents=1000)]

    balances = compute_balances(payments, splits)

    assert balances == {1: 0}


def test_no_payments_gives_empty_balances():
    assert compute_balances([], []) == {}
