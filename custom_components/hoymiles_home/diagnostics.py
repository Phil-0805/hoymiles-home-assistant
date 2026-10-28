"""Allowlisted model-discovery diagnostics, without account or device identifiers."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .inverter import inverter_model, inverter_ports


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Expose model results only; never export raw API payloads or config data."""
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
    return {"inverters": inverters}
