from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from telegram import Message, MessageEntity
from telegram import User as TgUser

from ..errors import InvalidSplitError, ParseError
from .formatting import format_cents

USAGE = (
    "Usage:\n"
    "/pay <amount> <description> for @user1 @user2 - equal split\n"
    "/pay <amount> <description> split me=30 @alice=30 - exact amounts\n"
    "/pay <amount> <description> shares me=1 @alice=2 - weighted split"
)

_SPLIT_KEYWORDS = {"for": "equal", "split": "exact", "shares": "shares"}


@dataclass(frozen=True)
class ParsedShare:
    ref: str  # "me" or a normalized username (no leading '@')
    computed_amount_cents: int
    weight: float | None = None


@dataclass(frozen=True)
class ParsedPayment:
    amount_cents: int
    description: str
    split_type: str = "equal"  # "equal" | "exact" | "shares"
    mentioned_usernames: list[str] = field(default_factory=list)
    text_mentioned_users: list[TgUser] = field(default_factory=list)
    shares: list[ParsedShare] = field(default_factory=list)


def parse_pay_command(message: Message) -> ParsedPayment:
    """Parses /pay in one of three grammars: equal ("for @mentions"), exact
    ("split ref=amount ..."), or weighted ("shares ref=weight ...")."""
    text = message.text or ""
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        raise ParseError(USAGE)

    tokens = parts[1].split()
    if not tokens:
        raise ParseError(USAGE)

    amount_cents = _parse_amount_cents(tokens[0])

    description_tokens: list[str] = []
    mode_tokens: list[str] = []
    split_type = "equal"
    in_split_mode = False
    for token in tokens[1:]:
        if not in_split_mode and token.lower() in _SPLIT_KEYWORDS:
            split_type = _SPLIT_KEYWORDS[token.lower()]
            in_split_mode = True
            continue
        if in_split_mode:
            mode_tokens.append(token)
        else:
            description_tokens.append(token)

    description = " ".join(description_tokens).strip()

    if split_type == "equal":
        mentioned_usernames = [
            token[1:].lower() for token in mode_tokens if token.startswith("@") and len(token) > 1
        ]
        text_mentioned_users = [
            entity.user
            for entity in (message.entities or [])
            if entity.type == MessageEntity.TEXT_MENTION and entity.user is not None
        ]
        return ParsedPayment(
            amount_cents=amount_cents,
            description=description,
            split_type="equal",
            mentioned_usernames=mentioned_usernames,
            text_mentioned_users=text_mentioned_users,
        )

    if split_type == "exact":
        shares = _parse_exact_shares(mode_tokens, amount_cents)
    else:
        shares = _parse_weighted_shares(mode_tokens, amount_cents)

    return ParsedPayment(
        amount_cents=amount_cents, description=description, split_type=split_type, shares=shares
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


def _normalize_ref(ref_token: str) -> str:
    if ref_token.lower() == "me":
        return "me"
    if ref_token.startswith("@") and len(ref_token) > 1:
        return ref_token[1:].lower()
    # Users without a public username can't be referenced by exact/weighted
    # splits (there's no unambiguous text token for them, unlike the equal-split
    # "for" grammar which can fall back to text_mention entities) — this is a
    # known MVP limitation, not a bug.
    raise InvalidSplitError(f"'{ref_token}' isn't recognized — use 'me' or '@username'.")


def _parse_ref_value_pairs(tokens: list[str]) -> list[tuple[str, Decimal]]:
    if not tokens:
        raise InvalidSplitError("List who owes what, e.g. 'me=30 @alice=30 @bob=30'.")

    pairs: list[tuple[str, Decimal]] = []
    seen_refs: set[str] = set()
    for token in tokens:
        if "=" not in token:
            raise InvalidSplitError(f"'{token}' isn't in the form ref=amount, e.g. '@alice=30'.")

        ref_token, _, value_token = token.partition("=")
        ref = _normalize_ref(ref_token)
        if ref in seen_refs:
            raise InvalidSplitError(f"'{ref_token}' was listed more than once.")
        seen_refs.add(ref)

        try:
            value = Decimal(value_token)
        except InvalidOperation as exc:
            raise InvalidSplitError(f"'{value_token}' isn't a valid number.") from exc
        if value <= 0:
            raise InvalidSplitError(f"The amount for '{ref_token}' must be greater than zero.")

        pairs.append((ref, value))

    return pairs


def _parse_exact_shares(tokens: list[str], amount_cents: int) -> list[ParsedShare]:
    pairs = _parse_ref_value_pairs(tokens)

    shares: list[ParsedShare] = []
    total_cents = 0
    for ref, value in pairs:
        cents_decimal = value * 100
        if cents_decimal != cents_decimal.to_integral_value():
            raise InvalidSplitError(f"The amount for '{ref}' can have at most 2 decimal places.")
        cents = int(cents_decimal)
        total_cents += cents
        shares.append(ParsedShare(ref=ref, computed_amount_cents=cents))

    if total_cents != amount_cents:
        diff = format_cents(abs(total_cents - amount_cents))
        direction = "over" if total_cents > amount_cents else "under"
        raise InvalidSplitError(
            f"Split amounts add up to {format_cents(total_cents)}, which is {diff} {direction} "
            f"the payment total of {format_cents(amount_cents)}."
        )

    return shares


def _parse_weighted_shares(tokens: list[str], amount_cents: int) -> list[ParsedShare]:
    pairs = _parse_ref_value_pairs(tokens)
    total_weight = sum(weight for _, weight in pairs)

    # Largest-remainder method: floor each share to whole cents, then hand the
    # leftover cents one at a time to whoever's floor discarded the most, so
    # totals always reconcile exactly regardless of weight ratios.
    remainders: list[tuple[Decimal, str, Decimal, int]] = []
    allocated = 0
    for ref, weight in pairs:
        raw_cents = Decimal(amount_cents) * weight / total_weight
        base = int(raw_cents)
        allocated += base
        remainders.append((raw_cents - base, ref, weight, base))

    leftover = amount_cents - allocated
    remainders.sort(key=lambda item: item[0], reverse=True)
    bonus_refs = {ref for _, ref, _, _ in remainders[:leftover]}

    shares = [
        ParsedShare(ref=ref, computed_amount_cents=base + (1 if ref in bonus_refs else 0), weight=float(weight))
        for _, ref, weight, base in remainders
    ]

    order = {ref: index for index, (ref, _) in enumerate(pairs)}
    shares.sort(key=lambda share: order[share.ref])

    return shares
