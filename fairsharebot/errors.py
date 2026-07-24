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
