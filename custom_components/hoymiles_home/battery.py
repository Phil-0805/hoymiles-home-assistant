"""Battery settings helpers for Hoymiles S-Miles Home."""

from __future__ import annotations

from typing import Any

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


class BatterySettingsError(ValueError):
    """Raised when a battery settings payload is incomplete."""


def battery_setting_targets(tree: Any) -> list[dict[str, Any]]:
    """Return device-addressed read targets from a nested Home device tree."""
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
            device_type == 3
            and isinstance(serial, str)
            and serial
            and isinstance(dtu_serial, str)
            and dtu_serial
            and serial != dtu_serial
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
    if not isinstance(mode, int):
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
