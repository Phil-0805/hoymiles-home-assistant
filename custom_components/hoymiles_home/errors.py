"""Shared API errors without transport or Home Assistant dependencies."""

from math import ceil


class HoymilesError(Exception):
    """Base API error."""


class HoymilesAuthError(HoymilesError):
    """Authentication error."""


class HoymilesConnectionError(HoymilesError):
    """Connection or response error."""


class HoymilesLivePending(HoymilesConnectionError):
    """A live server requested a later read, without returning telemetry."""

    def __init__(self, retry_after):
        super().__init__("Live data is not ready; a later read is scheduled")
        self.wait_seconds = retry_after
        # Only cap scheduler wake-ups. The client retains the full deadline.
        self.retry_after = min(86400, max(1, ceil(retry_after)))


SETTINGS_ERROR_REASONS = frozenset({
    "invalid_cutoffs", "invalid_heating", "invalid_lighting", "incomplete_display",
    "invalid_json", "invalid_station", "invalid_command_id", "command_failed",
    "invalid_settings", "authentication", "rate_limited", "timeout", "connection",
    "no_unique_target",
    "invalid_output_phases", "invalid_output_settings",
})

SETTINGS_DIAGNOSTIC_FIELDS = frozenset({
    "sl", "sh", "enable", "r", "g", "b", "slb", "slot", "ldb", "sot", "sid", "code",
    "power", "max_power", "out_power_total", "out_power_a", "out_power_b", "out_power_c",
    "power_a", "power_b", "power_c",
})


def setting_response_shape(data):
    """Describe only known field types; never retain values or arbitrary keys."""
    def kind(value):
        return {dict: "object", list: "array", str: "string", int: "integer",
                float: "number", bool: "boolean", type(None): "null"}.get(type(value), "other")
    fields = SETTINGS_DIAGNOSTIC_FIELDS
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
