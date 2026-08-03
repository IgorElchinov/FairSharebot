from __future__ import annotations

import pytest

from fairsharebot.chain.units import cents_to_token_units, parse_token_amount


def test_cents_to_token_units_scales_to_18_decimals():
    assert cents_to_token_units(100) == 100 * 10**16
    assert cents_to_token_units(1) == 10**16
    assert cents_to_token_units(0) == 0


def test_parse_token_amount_whole_number():
    assert parse_token_amount("100") == 100 * 10**18


def test_parse_token_amount_fractional():
    assert parse_token_amount("1.5") == 15 * 10**17


def test_parse_token_amount_rejects_zero_and_negative():
    with pytest.raises(ValueError):
        parse_token_amount("0")
    with pytest.raises(ValueError):
        parse_token_amount("-5")


def test_parse_token_amount_rejects_garbage():
    with pytest.raises(ValueError):
        parse_token_amount("not-a-number")
