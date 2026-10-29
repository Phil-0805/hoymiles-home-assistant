"""Hoymiles S-Miles Home integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HoymilesHomeClient
from .cloud_runtime import AccountPool
from .const import CONF_INVERTER_DETAILS, CONF_STATION_ID, CONF_STATION_TIMEZONE, DOMAIN, PLATFORMS
from .coordinator import HoymilesHomeCoordinator
from .telemetry import PV_POWER_SOURCE


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    pool = domain_data.setdefault("_accounts", AccountPool())
    account_key, runtime = pool.acquire(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = None
    try:
        client = HoymilesHomeClient(
            async_get_clientsession(hass),
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD], runtime=runtime,
        )
        coordinator = HoymilesHomeCoordinator(
            hass, client, entry.data[CONF_STATION_ID],
            pv_power_source=entry.options.get(PV_POWER_SOURCE, "auto"),
            inverter_details=entry.options.get(CONF_INVERTER_DETAILS, False),
            station_timezone=entry.options.get(CONF_STATION_TIMEZONE, hass.config.time_zone),
        )
        await coordinator.async_initialize()
        await coordinator.async_config_entry_first_refresh()
        domain_data[entry.entry_id] = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        domain_data.pop(entry.entry_id, None)
        pool.release(account_key)
        if coordinator is not None:
            await coordinator.async_shutdown()
        raise
    entry.async_on_unload(lambda: pool.release(account_key))
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply options through the normal unload/save/reload path."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await hass.data[DOMAIN][entry.entry_id].async_shutdown()
        await hass.data[DOMAIN][entry.entry_id].async_save_energy()
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False
