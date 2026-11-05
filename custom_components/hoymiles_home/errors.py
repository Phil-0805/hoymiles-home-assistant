"""Shared API errors without transport or Home Assistant dependencies."""


class HoymilesError(Exception):
    """Base API error."""


class HoymilesAuthError(HoymilesError):
    """Authentication error."""


class HoymilesConnectionError(HoymilesError):
    """Connection or response error."""


SETTINGS_ERROR_REASONS = frozenset({
    "invalid_cutoffs", "invalid_heating", "invalid_lighting", "incomplete_display",
    "invalid_json", "invalid_station", "invalid_command_id", "command_failed",
    "invalid_settings", "authentication", "rate_limited", "timeout", "connection",
    "no_unique_target",
})


def setting_response_shape(data):
    """Describe only known field types; never retain values or arbitrary keys."""
    def kind(value):
        return {dict: "object", list: "array", str: "string", int: "integer",
                float: "number", bool: "boolean", type(None): "null"}.get(type(value), "other")
    fields = {"sl", "sh", "enable", "r", "g", "b", "slb", "slot", "ldb", "sot", "sid"}
    return {"type": kind(data), "field_types": {
        key: kind(data[key]) for key in sorted(fields) if isinstance(data, dict) and key in data
    }}


class HoymilesSettingsError(HoymilesConnectionError):
    """Fixed diagnostic reason and structural metadata without cloud contents."""

    def __init__(self, reason, message, data=None):
        super().__init__(message)
        self.reason = reason if reason in SETTINGS_ERROR_REASONS else "invalid_settings"
        self.response_shape = setting_response_shape(data)


class HoymilesRateLimitError(HoymilesConnectionError):
    """Temporary server limit, with a bounded retry delay."""

    def __init__(self, message: str, retry_after: float = 60) -> None:
        super().__init__(message)
        # Limit scheduler wake-up delays, never the account's HTTP pause.
        # The runtime keeps the full server deadline, including multi-day waits.
        self.retry_after = min(86400, max(1, retry_after))
