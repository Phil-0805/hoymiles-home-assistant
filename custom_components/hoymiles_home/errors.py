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
        self.retry_after = retry_after
