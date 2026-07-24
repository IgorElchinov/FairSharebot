from __future__ import annotations

import pytest
from telegram import MessageEntity

from fairsharebot.errors import InvalidSplitError, ParseError
from fairsharebot.utils.parsing import parse_pay_command


class _FakeMessage:
    def __init__(self, text: str, entities: list | None = None) -> None:
        self.text = text
        self.entities = entities or []


def test_parses_amount_description_and_mentions():
    parsed = parse_pay_command(_FakeMessage("/pay 90 taxi ride for @alice @bob"))

    assert parsed.amount_cents == 9000
    assert parsed.description == "taxi ride"
    assert parsed.mentioned_usernames == ["alice", "bob"]


def test_parses_decimal_amount():
    parsed = parse_pay_command(_FakeMessage("/pay 12.34 coffee"))

    assert parsed.amount_cents == 1234
    assert parsed.description == "coffee"
    assert parsed.mentioned_usernames == []


def test_description_only_no_for_keyword():
    parsed = parse_pay_command(_FakeMessage("/pay 50 dinner with friends"))

    assert parsed.description == "dinner with friends"
    assert parsed.mentioned_usernames == []


def test_at_mentions_normalized_lowercase():
    parsed = parse_pay_command(_FakeMessage("/pay 30 snacks for @Alice"))

    assert parsed.mentioned_usernames == ["alice"]


def test_text_mention_entities_are_collected():
    from telegram import User

    carol = User(id=5, is_bot=False, first_name="Carol")
    entity = MessageEntity(type=MessageEntity.TEXT_MENTION, offset=0, length=5, user=carol)

    parsed = parse_pay_command(_FakeMessage("/pay 30 snacks for Carol", entities=[entity]))

    assert parsed.text_mentioned_users == [carol]


def test_missing_amount_raises():
    with pytest.raises(ParseError):
        parse_pay_command(_FakeMessage("/pay"))


def test_non_numeric_amount_raises():
    with pytest.raises(ParseError):
        parse_pay_command(_FakeMessage("/pay abc taxi"))


def test_zero_amount_raises():
    with pytest.raises(ParseError):
        parse_pay_command(_FakeMessage("/pay 0 taxi"))


def test_negative_amount_raises():
    with pytest.raises(ParseError):
        parse_pay_command(_FakeMessage("/pay -5 taxi"))


def test_too_many_decimal_places_raises():
    with pytest.raises(ParseError):
        parse_pay_command(_FakeMessage("/pay 12.345 taxi"))


def test_exact_split_parses_refs_and_amounts():
    parsed = parse_pay_command(_FakeMessage("/pay 90 dinner split me=30 @alice=30 @bob=30"))

    assert parsed.split_type == "exact"
    assert parsed.description == "dinner"
    assert {(s.ref, s.computed_amount_cents) for s in parsed.shares} == {
        ("me", 3000),
        ("alice", 3000),
        ("bob", 3000),
    }
    assert all(s.weight is None for s in parsed.shares)


def test_exact_split_mismatched_sum_raises():
    with pytest.raises(InvalidSplitError):
        parse_pay_command(_FakeMessage("/pay 90 dinner split me=30 @alice=30 @bob=20"))


def test_exact_split_duplicate_ref_raises():
    with pytest.raises(InvalidSplitError):
        parse_pay_command(_FakeMessage("/pay 90 dinner split me=30 me=60"))


def test_exact_split_missing_tokens_raises():
    with pytest.raises(InvalidSplitError):
        parse_pay_command(_FakeMessage("/pay 90 dinner split"))


def test_exact_split_bad_ref_format_raises():
    with pytest.raises(InvalidSplitError):
        parse_pay_command(_FakeMessage("/pay 90 dinner split alice=30 me=60"))


def test_exact_split_non_positive_value_raises():
    with pytest.raises(InvalidSplitError):
        parse_pay_command(_FakeMessage("/pay 90 dinner split me=0 @alice=90"))


def test_shares_split_parses_weights_and_computes_cents():
    parsed = parse_pay_command(_FakeMessage("/pay 90 rent shares me=1 @alice=1 @bob=2"))

    assert parsed.split_type == "shares"
    by_ref = {s.ref: s for s in parsed.shares}
    assert by_ref["me"].computed_amount_cents == 2250
    assert by_ref["alice"].computed_amount_cents == 2250
    assert by_ref["bob"].computed_amount_cents == 4500
    assert by_ref["bob"].weight == 2.0
    assert sum(s.computed_amount_cents for s in parsed.shares) == 9000


def test_shares_split_uneven_weights_reconcile_exactly():
    parsed = parse_pay_command(_FakeMessage("/pay 10 snacks shares me=1 @alice=1 @bob=1"))

    assert sum(s.computed_amount_cents for s in parsed.shares) == 1000
    amounts = sorted(s.computed_amount_cents for s in parsed.shares)
    assert amounts == [333, 333, 334]


def test_shares_split_bad_weight_raises():
    with pytest.raises(InvalidSplitError):
        parse_pay_command(_FakeMessage("/pay 90 rent shares me=1 @alice=-1"))
