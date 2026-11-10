"""Cloud diagnostics made exclusively from fixed labels and bounded numbers."""

import logging

from .const import (
    AUTH_BASE_URLS, DATA_BASE_URL, STATION_SETTING_READ_URL,
    STATION_SETTING_STATUS_URL, STATION_SETTING_WRITE_URL,
)
from .errors import HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError
from .telemetry import number

LOGGER = logging.getLogger(__name__)
_SETTING_ROUTES = {
    f"{DATA_BASE_URL}/pvm-ctl/api/0/dev/setting/read": ("device_settings", "read"),
    f"{DATA_BASE_URL}/pvm-ctl/api/0/dev/setting/write": ("device_settings", "write"),
    STATION_SETTING_READ_URL: ("station_settings", "read"),
    STATION_SETTING_WRITE_URL: ("station_settings", "write"),
}
_SETTING_FEATURES = {
    1518: "heating", 1529: "lighting", 1537: "cutoffs", 84: "output_power",
    1532: "output_power", 83: "work_mode", 1013: "battery_settings",
}
_KNOWN_STAGES = {
    f"{base}/iam/pub/3/auth/{operation}": stage
    for base in AUTH_BASE_URLS.values()
    for operation, stage in (("pre-insp", "login_challenge"), ("login", "login"))
}
_KNOWN_STAGES.update({
    f"{base}/iam/pub/0/c/region_c": "login_region" for base in AUTH_BASE_URLS.values()
})
_KNOWN_STAGES.update({
    f"{DATA_BASE_URL}/pvm/api/0/station/select_by_page": "station_discovery",
    f"{DATA_BASE_URL}/pvm/api/0/station/select_device_of_tree": "station_validation",
    f"{DATA_BASE_URL}/pvm-data/api/0/station/data/count_station_real_data": "station_realtime",
    f"{DATA_BASE_URL}/pvmc/api/0/station/select_by_page_c": "station_discovery",
    f"{DATA_BASE_URL}/pvmc/api/0/station/select_device_c": "station_validation",
    f"{DATA_BASE_URL}/pvmc/api/0/station/get_sd_uri_c": "live_uri_mobile",
    f"{DATA_BASE_URL}/pvm/api/0/station/get_sd_uri": "live_uri_web",
    f"{DATA_BASE_URL}/pvm-ctl/api/0/dev/setting/status": "device_settings_status",
    STATION_SETTING_STATUS_URL: "station_settings_status",
    f"{DATA_BASE_URL}/pvmc/api/0/station/phase/type_s_c": "output_phase_lookup",
})
_SETTING_STAGES = {
    f"{feature}_{operation}"
    for feature in {"device_settings", "station_settings"} | set(_SETTING_FEATURES.values())
    for operation in ("read", "write")
}
STAGES = frozenset(set(_KNOWN_STAGES.values()) | _SETTING_STAGES
                   | {"reauthentication", "live_data", "other_api"})
REASONS = frozenset({"http_error", "timeout", "transport_error", "redirect_rejected",
                     "invalid_json", "cloud_rejected", "invalid_challenge", "missing_token",
                     "missing_uri", "invalid_uri_type", "untrusted_uri", "invalid_live_data",
                     "unexpected_response", "authentication", "rate_limited", "connection", "unexpected_error",
                     "unsupported_auth_version", "unsupported_auth_region", "invalid_auth_routing",
                     "session_expired", "client_update_required", "home_app_required",
                     "invalid_work_mode_settings", "unsupported_profile_operation", "account_action_required"})


def cloud_failure_reason(response):
    """Recognize evidenced server errors without returning any server text."""
    status = response.get("status")
    if type(status) in (str, int) and str(status) == "0":
        return None
    if type(status) in (str, int) and str(status) == "100":
        return "session_expired"
    message = response.get("message")
    text = message.lower() if isinstance(message, str) and len(message) <= 4096 else ""
    if "logins exceeds the daily maximum limit" in text:
        return "rate_limited"
    if "your app version is low. please update to the latest version." in text:
        return "client_update_required"
    if any(signal in text for signal in (
        "can only login to the s-miles home", "can only log in to s-miles home app",
        "can only be used for logging in to the s-miles home app",
    )):
        return "home_app_required"
    return "cloud_rejected"


def request_stage(url, payload=None, live_uri=None):
    """Match exact known routes/actions; never turn private input into labels."""
    if url in _SETTING_ROUTES:
        family, operation = _SETTING_ROUTES[url]
        action = payload.get("action") if isinstance(payload, dict) else None
        if type(action) is int:
            family = _SETTING_FEATURES.get(action, family)
        return f"{family}_{operation}"
    return _KNOWN_STAGES.get(url, "live_data" if live_uri is not None and url == live_uri else "other_api")


def safe_code(value):
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 6:
        value = int(value)
    return value if type(value) is int and 0 <= value <= 999999 else "unavailable"


def value_kind(value):
    """Only fixed type labels; no repr, arbitrary class names or field values."""
    return {dict: "object", list: "array", str: "string", int: "integer", float: "number",
            bool: "boolean", type(None): "null"}.get(type(value), "other")


def work_mode_response_summary(result):
    """Summarize unwrapped action-83 results without plans or private values."""
    result = result if isinstance(result, dict) else {}
    data = result.get("data")
    fields = data if isinstance(data, dict) else {}
    tou = fields.get("k_3")
    tou_fields = tou if isinstance(tou, dict) else {}

    def known(value, allowed):
        return value if type(value) is int and value in allowed else "unavailable"

    return (f"command_code={safe_code(result.get('code'))} data_type={value_kind(data)} "
            f"app_mode={known(fields.get('mode'), (2, 3))} "
            f"tou_submode={known(tou_fields.get('mode'), (1, 2, 3, 4, 5))} "
            f"self_settings_type={value_kind(fields.get('k_2'))} "
            f"tou_settings_type={value_kind(tou)} "
            f"soc_l_type={value_kind(fields.get('soc_l'))} "
            f"soc_h_type={value_kind(fields.get('soc_h'))}")


def live_response_summary(payload):
    """Describe the actual live acceptance criteria, without exposing measurements."""
    def field_kind(key):
        return value_kind(payload[key]) if isinstance(payload, dict) and key in payload else "missing"

    con_state = "missing"
    if isinstance(payload, dict) and "con" in payload:
        con_state = "valid" if number(payload["con"]) in (0, 1) else "invalid"
    return (f"data_type={value_kind(payload)} flow_type={field_kind('flow')} "
            f"con_type={field_kind('con')} con_state={con_state} power_type={field_kind('power')}")


def response_summary(response):
    """Do not include values, arbitrary keys, server messages, addresses or counts."""
    response = response if isinstance(response, dict) else {}
    data = response.get("data")
    kind = value_kind(data)
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
