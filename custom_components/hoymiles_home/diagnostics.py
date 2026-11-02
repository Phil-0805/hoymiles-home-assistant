"""Allowlisted telemetry diagnostics without account or device identifiers."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .inverter import inverter_model, inverter_ports
from .battery import writable_modes
from .telemetry import battery_activity, live_power, number, pv_power_details, status_codes


def _battery_diagnostics(settings: dict) -> dict:
    """Export availability and selected numbers, never error text or payloads."""
    method = settings.get("request_method")
    active = settings.get("active_settings", {})
    if not isinstance(active, dict):
        active = {}
    modes = settings.get("available_modes")
    modes = modes if isinstance(modes, list) else []
    modes = [mode for mode in modes if type(mode) is int and mode in {1, 2, 3, 4, 5, 6, 7, 8}]
    return {
        "readable": settings.get("readable") is True,
        "writable": settings.get("writable") is True,
        "request_method": method if method in {
            "station_action_83", "station", "device"
        } else None,
        "used_work_mode_fallback": bool(settings.get("work_mode_request_error")),
        "has_error": bool(settings.get("error")),
        "mode": number(settings.get("mode")),
        "reserve_soc": number(active.get("reserve_soc")),
        "max_power": number(active.get("max_power")),
        "available_modes": modes,
        "mode_control": "multiple_modes" if len(writable_modes(settings)) > 1 else "single_or_no_mode",
        "max_power_unit_verified": False,
        "active_numeric_fields": {
            key: number(active[key])
            for key in ("reserve_soc", "soc_l", "soc_h", "max_power", "pc", "pd")
            if key in active
        },
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Expose selected numeric values; never export raw payloads or config data."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    statuses = {"identified", "unresolved", "none", "home_tree", "web_tree",
                "micro_detail", "unavailable", "no_model"}
    inverters = []
    for inverter in coordinator.inverters:
        discovery = inverter.get("_model_discovery", {})
        safe_discovery = {
            key: value for key, value in discovery.items()
            if key in {"result", "source", "web_tree", "detail"}
            and isinstance(value, str) and value in statuses
        }
        if discovery.get("timeout") is True:
            safe_discovery["timeout"] = True
        inverters.append({
            "model": inverter_model(inverter),
            "queried_pv_ports": list(inverter_ports(inverter)),
            "discovery": safe_discovery,
        })
    data = getattr(coordinator, "data", None) or {}
    live = data.get("live", {})
    return {
        "inverters": inverters,
        "polling": {
            "station_timezone": str(getattr(coordinator, "station_timezone", "unknown")),
            "details_enabled": getattr(coordinator, "inverter_details", False) is True,
            "details_status": getattr(getattr(coordinator, "module_polling", None), "details_status", "disabled"),
            "minimum_http_start_interval_seconds": 1,
            "maximum_concurrent_http_requests": 2,
        },
        "battery_telemetry": {
            "enabled": getattr(getattr(coordinator, "battery_telemetry", None), "enabled", False),
            "status": getattr(getattr(coordinator, "battery_telemetry", None), "status", "disabled"),
            "device_count": len(getattr(getattr(coordinator, "battery_telemetry", None), "values", {})),
        },
        "pv_power": pv_power_details(data),
        "battery": {
            "power": number(live_power(data).get("bat")),
            "soc": number(live.get("soc")),
            "raw_status_codes": status_codes(live),
            "activity_from_brs": battery_activity(live),
            "direction_mapping_verified_on": "HMS-2000-4WB",
            "other_status_meanings": "unverified",
            "settings": _battery_diagnostics(
                getattr(coordinator, "battery_settings", {})
            ),
        },
    }
