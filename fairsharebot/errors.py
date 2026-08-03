from __future__ import annotations


class FairShareError(Exception):
    """Base class for user-facing bot errors."""


class NoOpenTripError(FairShareError):
    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id
        super().__init__(f"No open trip in chat {chat_id}")


class TripAlreadyOpenError(FairShareError):
    def __init__(self, chat_id: int) -> None:
        self.chat_id = chat_id
        super().__init__(f"A trip is already open in chat {chat_id}")


class UnknownUserError(FairShareError):
    def __init__(self, username: str) -> None:
        self.username = username
        super().__init__(f"Unknown user: @{username}")


class ParseError(FairShareError):
    """Raised when a command's text doesn't match its expected grammar."""


class InvalidSplitError(ParseError):
    """Raised when an exact/shares split doesn't validate (bad ref, non-positive
    value, duplicate participant, or amounts that don't sum to the payment total)."""


class PaymentNotFoundError(FairShareError):
    def __init__(self, payment_id: int) -> None:
        self.payment_id = payment_id
        super().__init__(f"No such payment: {payment_id}")


class NoWalletError(FairShareError):
    """Raised when a token-mode operation needs a wallet a user doesn't have yet."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__(f"No wallet on file for user {user_id}")


class NoCustodialWalletError(FairShareError):
    """Raised by /exportkey when a user has never had a custodial wallet derived."""

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        super().__init__(f"No custodial wallet was ever derived for user {user_id}")
