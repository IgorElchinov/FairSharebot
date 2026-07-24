from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from telegram import Message, MessageEntity
from telegram import User as TgUser

from ..errors import ParseError

USAGE = "Usage: /pay <amount> <description> [for @user1 @user2 ...]"


@dataclass(frozen=True)
class ParsedPayment:
    amount_cents: int
    description: str
    mentioned_usernames: list[str] = field(default_factory=list)
    text_mentioned_users: list[TgUser] = field(default_factory=list)


def parse_pay_command(message: Message) -> ParsedPayment:
    """Parses the equal-split /pay grammar: /pay <amount> <description...> [for @mentions...]."""
    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        raise ParseError(USAGE)

    tokens = parts[1].split()
    if not tokens:
        raise ParseError(USAGE)

    amount_cents = _parse_amount_cents(tokens[0])

    description_tokens: list[str] = []
    mentioned_usernames: list[str] = []
    in_mentions = False
    for token in tokens[1:]:
        if not in_mentions and token.lower() == "for":
            in_mentions = True
            continue
        if in_mentions:
            if token.startswith("@") and len(token) > 1:
                mentioned_usernames.append(token[1:].lower())
        else:
            description_tokens.append(token)

    text_mentioned_users = [
        entity.user
        for entity in (message.entities or [])
        if entity.type == MessageEntity.TEXT_MENTION and entity.user is not None
    ]

    return ParsedPayment(
        amount_cents=amount_cents,
        description=" ".join(description_tokens).strip(),
        mentioned_usernames=mentioned_usernames,
        text_mentioned_users=text_mentioned_users,
    )


def _parse_amount_cents(token: str) -> int:
    try:
        amount = Decimal(token)
    except InvalidOperation as exc:
        raise ParseError(f"'{token}' isn't a valid amount.") from exc

    if amount <= 0:
        raise ParseError("Amount must be greater than zero.")

    cents_decimal = amount * 100
    if cents_decimal != cents_decimal.to_integral_value():
        raise ParseError("Amounts can have at most 2 decimal places.")

    return int(cents_decimal)
