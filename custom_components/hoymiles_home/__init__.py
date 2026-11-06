"""Hoymiles S-Miles Home integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .api import HoymilesHomeClient
from .cloud_runtime import AccountPool
from .const import CONF_BATTERY_CONTROLS, CONF_DEVICE_CONTROLS, CONF_INVERTER_DETAILS, CONF_STATION_ID, CONF_STATION_TIMEZONE, DOMAIN, PLATFORMS
from .coordinator import HoymilesHomeCoordinator
from .device_migration import (
    async_migrate_battery_temperatures, async_remove_obsolete_charge_limit_entities,
    async_remove_obsolete_max_power_sensor,
)
from .telemetry import PV_POWER_SOURCE


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    pool = domain_data.setdefault("_accounts", AccountPool())
    account_key, runtime = pool.acquire(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = None
    try:
        client = HoymilesHomeClient(
            async_get_clientsession(hass, verify_ssl=True),
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD], runtime=runtime,
        )
        station_timezone = await dt_util.async_get_time_zone(
            entry.options.get(CONF_STATION_TIMEZONE) or hass.config.time_zone
        ) or dt_util.get_default_time_zone()
        coordinator = HoymilesHomeCoordinator(
            hass, client, entry.data[CONF_STATION_ID],
            battery_controls=entry.options.get(CONF_BATTERY_CONTROLS, False) is True,
            device_controls=entry.options.get(CONF_DEVICE_CONTROLS, False) is True,
            pv_power_source=entry.options.get(PV_POWER_SOURCE, "auto"),
            battery_temperatures=True,
            inverter_details=entry.options.get(CONF_INVERTER_DETAILS, False),
            station_timezone=station_timezone,
        )
        await coordinator.async_initialize()
        await coordinator.async_config_entry_first_refresh()
        domain_data[entry.entry_id] = coordinator
        # Register the station before child platforms resolve its registry ID.
        dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"station_{entry.data[CONF_STATION_ID]}")},
            manufacturer="Hoymiles", name=f"S-Miles Home {entry.data[CONF_STATION_ID]}",
            model="S-Miles Home station",
        )
        async_remove_obsolete_charge_limit_entities(hass, entry)
        async_remove_obsolete_max_power_sensor(hass, entry)
        async_migrate_battery_temperatures(hass, entry)
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
