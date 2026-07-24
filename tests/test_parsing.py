from __future__ import annotations

import pytest
from telegram import MessageEntity

from fairsharebot.errors import ParseError
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
