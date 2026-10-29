"""Conservative interpretation of live power and battery status fields."""

from math import isfinite
from typing import Any

PV_POWER_SOURCE = "pv_power_source"
PV_POWER_SOURCES = ("auto", "pv", "pv2")
BATTERY_ACTIVITY = {0: "idle", 1: "charging", 2: "discharging"}
STATUS_FIELDS = ("ems", "brs", "chs", "bhs")


def live_connected(live: dict[str, Any]) -> bool:
    """Honor an explicit offline/invalid flag; tolerate legacy missing flags."""
    return "con" not in live or number(live["con"]) == 1


def number(value: Any) -> float | int | None:
    """Accept finite numeric cloud values, excluding booleans."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        parsed = float(value) if isinstance(value, str) else value
        return parsed if isfinite(parsed) else None
    except (ValueError, OverflowError):
        return None


def live_power(data: dict[str, Any]) -> dict[str, Any]:
    """A disconnected or malformed response may contain a null power block."""
    live = data.get("live")
    power = live.get("power") if isinstance(live, dict) else None
    return power if isinstance(power, dict) else {}


def pv_power_details(data: dict[str, Any]) -> dict[str, Any]:
    """Select one field, retaining the established default and valid zeros.

    pv and pv2 are not proven to be additive on every Home installation.
    Explicit selections never silently substitute a different field.
    """
    power = live_power(data)
    values = {key: number(power.get(key)) for key in ("pv", "pv2")}
    selection = data.get(PV_POWER_SOURCE, "auto")
    if selection not in PV_POWER_SOURCES:
        selection = "auto"
    source = selection
    if selection == "auto":
        source = "pv2" if values["pv2"] is not None else "pv"
    return {"selection": selection, "source": source,
            "value": values[source], **values}


def status_codes(live: dict[str, Any]) -> dict[str, int | float | None]:
    """Keep raw numeric codes without guessing undocumented meanings."""
    return {key: number(live.get(key)) for key in STATUS_FIELDS}


def battery_activity(live: dict[str, Any]) -> str | None:
    """Use the brs direction mapping tested on the HMS-2000-4WB setup.

    This is the same mapping used by the existing energy calculation, not a
    verified protocol specification for every battery model or firmware.
    """
    code = number(live.get("brs"))
    if code is None:
        return None
    return BATTERY_ACTIVITY.get(code, "unrecognized")
