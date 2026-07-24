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
