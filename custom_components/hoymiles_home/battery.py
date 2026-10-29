"""Battery settings helpers for Hoymiles S-Miles Home."""

from __future__ import annotations

from typing import Any
from math import isfinite
from copy import deepcopy
import json

BATTERY_MODE_NAMES = {
    1: "Self-Consumption",
    2: "Economy",
    3: "Backup",
    4: "Off-Grid",
    5: "Self-Consumption + Max Power",
    6: "Backup + Max Power",
    7: "Peak Shaving",
    8: "Time of Use",
}
WRITABLE_BATTERY_MODES = {1, 2, 3, 4, 7, 8}


def writable_modes(settings: dict[str, Any]) -> list[int]:
    """Only offer advertised modes whose control semantics are supported."""
    modes = settings.get("available_modes")
    if not isinstance(modes, list):
        return []
    return [mode for mode in modes if type(mode) is int and mode in WRITABLE_BATTERY_MODES]


class BatterySettingsError(ValueError):
    """Raised when a battery settings payload is incomplete."""


def reserve_soc_candidates(payload: Any) -> list[dict[str, Any]]:
    """Return non-sensitive reserve-SOC evidence from an app settings payload."""
    candidates: list[dict[str, Any]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
            return
        if not isinstance(value, dict):
            return

        for key, item in value.items():
            item_path = f"{path}.{key}" if path else str(key)
            if (
                key == "reserve_soc"
                and isinstance(item, (int, float))
                and not isinstance(item, bool)
                and 0 <= float(item) <= 100
            ):
                candidates.append({"path": item_path, "value": int(item)})
            else:
                visit(item, item_path)

    visit(payload, "")
    return candidates


def soc_setting_candidates(payload: Any) -> list[dict[str, Any]]:
    """Return non-sensitive scalar values whose setting name contains SOC."""
    candidates: list[dict[str, Any]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
            return
        if not isinstance(value, dict):
            return

        for key, item in value.items():
            item_path = f"{path}.{key}" if path else str(key)
            if ("soc" in str(key).lower() and isinstance(item, (int, float))
                    and not isinstance(item, bool) and 0 <= item <= 100 and isfinite(item)):
                candidates.append({"path": item_path, "value": item})
            else:
                visit(item, item_path)

    visit(payload, "")
    return candidates[:100]


def confirmed_reserve_soc(
    candidates: list[dict[str, Any]], mode: int | None
) -> int | None:
    """Choose an unambiguous app reserve SOC, preferring the active mode."""
    if mode is not None:
        mode_values = {
            item["value"]
            for item in candidates
            if f"k_{mode}" in str(item.get("path")).replace("[", ".").replace("]", "").split(".")
        }
        if len(mode_values) == 1:
            return int(mode_values.pop())

    # A bare bms_data.reserve_soc is a separate/stale consumer setting on the
    # HMS-2000-4WB and must not be treated as the active mode's discharge floor.
    return None


def battery_setting_targets(tree: Any) -> list[dict[str, Any]]:
    """Return HiBattery device-addressed targets from a Home device tree.

    S-Miles Home exposes the AC battery controller as device type 12. A type-3
    microinverter can also accept action 1013, but its response describes a
    different/default settings block and must not be presented as the battery's
    active configuration.
    """
    found: dict[tuple[str, str], dict[str, Any]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                visit(item)
            return
        if not isinstance(value, dict):
            return

        serial = value.get("sn")
        dtu_serial = value.get("dtu_sn")
        device_type = value.get("type")
        if (
            device_type == 12
            and isinstance(serial, str)
            and serial
            and isinstance(dtu_serial, str)
            and dtu_serial
        ):
            found[(serial, dtu_serial)] = {
                "dev_sn": serial,
                "dev_type": device_type,
                "dtu_sn": dtu_serial,
            }

        for child in value.values():
            visit(child)

    visit(tree)
    return list(found.values())


def parse_battery_settings(result: Any) -> dict[str, Any]:
    """Normalize a completed action-1013 settings response."""
    if not isinstance(result, dict):
        raise BatterySettingsError("Missing battery settings result")

    code = result.get("code")
    if code not in (None, 0):
        raise BatterySettingsError(
            str(result.get("message") or f"Battery settings returned code {code}")
        )

    payload = result.get("data")
    if not isinstance(payload, dict):
        raise BatterySettingsError("Missing battery settings payload")

    mode_data = payload.get("data")
    if not isinstance(mode_data, dict):
        raise BatterySettingsError("Missing battery mode data")

    mode = payload.get("mode")
    if isinstance(mode, bool) or not isinstance(mode, int):
        mode = None

    modes: dict[int, dict[str, Any]] = {}
    for key, settings in mode_data.items():
        if not key.startswith("k_") or not key[2:].isdigit():
            continue
        if isinstance(settings, dict):
            modes[int(key[2:])] = settings

    active_settings = modes.get(mode, {}) if mode is not None else {}
    return {
        "readable": True,
        "mode": mode,
        "mode_name": BATTERY_MODE_NAMES.get(mode, f"Unknown ({mode})"),
        "available_modes": sorted(modes),
        "available_mode_names": [
            BATTERY_MODE_NAMES.get(item, f"Unknown ({item})")
            for item in sorted(modes)
        ],
        "active_settings": active_settings,
        "mode_settings": modes,
    }


def _tou_settings(raw: Any, *, command: bool = False) -> dict[str, Any]:
    """Reuse an existing action-83 TOU selection; never create a schedule."""
    if not isinstance(raw, dict) or type(raw.get("mode")) is not int:
        raise BatterySettingsError("Missing TOU configuration")
    submode = raw["mode"]
    if submode == 1:
        return {"mode": 1}  # Existing recommended configuration.
    if submode == 2:
        plan = raw.get("data" if command else "k_2")
        if (not isinstance(plan, dict) or type(plan.get("id")) is not int
                or plan["id"] <= 0 or not isinstance(plan.get("week"), list)
                or not 1 <= len(plan["week"]) <= 7
                or not all(isinstance(day, dict) for day in plan["week"])):
            raise BatterySettingsError("TOU basic plan must already be configured in the app")
        result = {"mode": 2, "data": {"id": plan["id"], "week": deepcopy(plan["week"])}}
        try:
            if len(json.dumps(result, allow_nan=False)) > 65536:
                raise ValueError("oversized schedule")
        except (ValueError, TypeError, RecursionError) as err:
            raise BatterySettingsError("Invalid TOU schedule") from err
        return result
    if submode == 3:
        plan = raw if command else raw.get("k_3")
        if not isinstance(plan, dict) or type(plan.get("id")) is not int or plan["id"] <= 0:
            raise BatterySettingsError("TOU advanced plan must already be configured in the app")
        return {"mode": 3, "id": plan["id"]}
    raise BatterySettingsError("Unsupported TOU submode")


def work_mode_command_data(mode: int, settings: dict[str, Any]) -> dict[str, Any]:
    """Build only the command-83 payloads observed in Hoymiles' web client."""
    if type(mode) is not int:
        raise BatterySettingsError("Invalid work mode")
    if mode == 8:
        return {"mode": 3, "data": _tou_settings(settings.get("tou_settings"), command=True)}
    if mode != 1:
        raise BatterySettingsError("Unsupported work mode write")
    lower, upper = settings.get("reserve_soc"), settings.get("soc_h", 100)
    if (isinstance(lower, bool) or isinstance(upper, bool)
            or not isinstance(lower, (int, float)) or not isinstance(upper, (int, float))
            or not 0 <= lower <= upper <= 100 or not isfinite(lower) or not isfinite(upper)
            or int(lower) != lower or int(upper) != upper):
        raise BatterySettingsError("Invalid work mode SOC limits")
    return {"mode": 2, "soc_l": int(lower), "soc_h": int(upper)}


def parse_work_mode_settings(result: Any) -> dict[str, Any]:
    """Read action 83: app mode 2 is self-consumption, 3 is TOU (not BMS ids)."""
    if not isinstance(result, dict) or result.get("code") != 0:
        raise BatterySettingsError("Work mode settings are not ready")
    data = result.get("data")
    if not isinstance(data, dict) or type(data.get("mode")) is not int or data["mode"] not in (2, 3):
        raise BatterySettingsError("Unsupported work mode settings")
    modes = {}
    # Both layouts have been observed: the existing k_2 bucket and the current
    # web client's top-level SOC fields. Conflicting evidence is rejected.
    self_data = data.get("k_2")
    source = "station_action_83_k_2_soc_l"
    if "soc_l" in data:
        if isinstance(self_data, dict) and any(key in self_data and self_data[key] != data[key]
                                              for key in ("soc_l", "soc_h") if key in data):
            raise BatterySettingsError("Conflicting work mode SOC settings")
        self_data = data
        source = "station_action_83_soc_l"
    if isinstance(self_data, dict):
        candidate = {"reserve_soc": self_data.get("soc_l"), "soc_h": self_data.get("soc_h", 100)}
        try:
            payload = work_mode_command_data(1, candidate)
            modes[1] = {"reserve_soc": payload["soc_l"], "soc_l": payload["soc_l"], "soc_h": payload["soc_h"]}
        except BatterySettingsError:
            if data["mode"] == 2:
                raise
    try:
        modes[8] = {"tou_settings": _tou_settings(data.get("k_3"))}
    except BatterySettingsError:
        if data["mode"] == 3:
            raise
    mode = 1 if data["mode"] == 2 else 8
    if mode not in modes:
        raise BatterySettingsError("Missing active work mode settings")
    return {
        "readable": True, "writable": True,
        "mode": mode, "mode_name": BATTERY_MODE_NAMES[mode],
        "app_work_mode": data["mode"],
        "available_modes": list(modes),
        "available_mode_names": [BATTERY_MODE_NAMES[item] for item in modes],
        "active_settings": deepcopy(modes[mode]), "mode_settings": modes,
        "request_method": "station_action_83",
        "reserve_soc_verified": mode == 1,
        "reserve_soc_source": source if mode == 1 else None,
    }


def _setting_equal(actual: Any, expected: Any) -> bool:
    """Compare complete values without treating boolean flags as numeric settings."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(
            _setting_equal(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            _setting_equal(a, b) for a, b in zip(actual, expected, strict=True)
        )
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    return actual == expected


def battery_settings_confirmed(
    settings: dict[str, Any], mode: int, requested: dict[str, Any]
) -> bool:
    """Return whether a delayed app-setting write is visible in a fresh read."""
    if type(settings.get("mode")) is not int or settings.get("mode") != mode:
        return False
    active = settings.get("active_settings")
    if not isinstance(active, dict):
        return False
    return all(
        key in active and _setting_equal(active[key], value)
        for key, value in requested.items()
    )
def battery_setting_command_data(
    station_id: int, mode: int, mode_data: dict[str, Any]
) -> dict[str, Any]:
    """Build the action-1013 write data without dropping mode settings."""
    setting_data: dict[str, Any] = {"mode": mode}
    if mode_data:
        setting_data["data"] = mode_data
    return {
        "sid": station_id,
        "data": setting_data,
    }
