"""Shared API errors without transport or Home Assistant dependencies."""


class HoymilesError(Exception):
    """Base API error."""


class HoymilesAuthError(HoymilesError):
    """Authentication error."""


class HoymilesConnectionError(HoymilesError):
    """Connection or response error."""


class HoymilesRateLimitError(HoymilesConnectionError):
    """Temporary server limit, with a bounded retry delay."""

    def __init__(self, message: str, retry_after: float = 60) -> None:
        super().__init__(message)
        # Limit scheduler wake-up delays, never the account's HTTP pause.
        # The runtime keeps the full server deadline, including multi-day waits.
        self.retry_after = min(86400, max(1, retry_after))
