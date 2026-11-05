"""Cloud diagnostics made exclusively from fixed labels and bounded numbers."""

import logging

from .errors import HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError

LOGGER = logging.getLogger(__name__)
STAGES = frozenset({"login_challenge", "login", "station_discovery", "station_validation",
                    "reauthentication", "live_uri_mobile", "live_uri_web", "live_data", "other_api"})
REASONS = frozenset({"http_error", "timeout", "transport_error", "redirect_rejected",
                     "invalid_json", "cloud_rejected", "invalid_challenge", "missing_token",
                     "missing_uri", "invalid_uri_type", "untrusted_uri", "invalid_live_data",
                     "unexpected_response", "authentication", "rate_limited", "connection", "unexpected_error"})


def safe_code(value):
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 6:
        value = int(value)
    return value if type(value) is int and 0 <= value <= 999999 else "unavailable"


def response_summary(response):
    """Do not include values, arbitrary keys, server messages, addresses or counts."""
    response = response if isinstance(response, dict) else {}
    data = response.get("data")
    kind = {dict: "object", list: "array", str: "string", int: "integer", float: "number",
            bool: "boolean", type(None): "null"}.get(type(data), "other")
    uri = "missing"
    if isinstance(data, dict) and "uri" in data:
        value = data["uri"]
        uri = "empty" if value is None or value == "" else "string" if isinstance(value, str) else "wrong_type"
    return f"cloud_status={safe_code(response.get('status'))} data_type={kind} uri={uri}"


class CloudDiagnosticError(HoymilesConnectionError):
    """A fixed reason attached to an already sanitized public exception message."""

    def __init__(self, reason, message):
        super().__init__(message)
        self.reason = reason if reason in REASONS else "unexpected_response"


def failure_reason(error):
    if isinstance(error, CloudDiagnosticError):
        return error.reason
    if isinstance(error, HoymilesAuthError):
        return "authentication"
    if isinstance(error, HoymilesRateLimitError):
        return "rate_limited"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, HoymilesConnectionError):
        return "connection"
    return "unexpected_error"


def log_failure(stage, error):
    """Used by setup paths too; never interpolate exception text or traceback."""
    LOGGER.warning("Cloud setup failed: stage=%s reason=%s", stage if stage in STAGES else "other_api",
                   failure_reason(error))
