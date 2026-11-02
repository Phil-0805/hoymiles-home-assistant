"""Resolve timezone data off the event loop, including on a cold cache."""

from datetime import timedelta, timezone
import threading
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_home import async_setup_entry as real_setup_entry
from custom_components.hoymiles_home.config_flow import _time_zone_options
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator


@pytest.mark.parametrize("selected,resolved", [
    ("Europe/Berlin", timezone(timedelta(hours=1))),
    (None, timezone.utc),
    ("invalid/synthetic", None),
])
async def test_setup_awaits_zone_resolution_and_passes_tzinfo(hass, selected, resolved):
    options = {"station_timezone": selected} if selected else {}
    entry = MockConfigEntry(domain=DOMAIN, data={
        "username": "test@example.com", "password": "synthetic", "station_id": 123,
    }, options=options)
    entry.add_to_hass(hass)
    expected = resolved or dt_util.get_default_time_zone()
    with (
        patch("custom_components.hoymiles_home.dt_util.async_get_time_zone", new=AsyncMock(return_value=resolved)) as resolve,
        patch("custom_components.hoymiles_home.HoymilesHomeCoordinator", wraps=HoymilesHomeCoordinator) as constructor,
        patch.object(HoymilesHomeCoordinator, "async_initialize", new=AsyncMock()),
        patch.object(HoymilesHomeCoordinator, "async_config_entry_first_refresh", new=AsyncMock()),
        patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()),
        patch("custom_components.hoymiles_home.async_migrate_battery_temperatures"),
        patch("zoneinfo.ZoneInfo", side_effect=AssertionError("Synchronous zone lookup")),
    ):
        assert await real_setup_entry(hass, entry)
    resolve.assert_awaited_once_with(selected or hass.config.time_zone)
    assert constructor.call_args.kwargs["station_timezone"] is expected
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.station_timezone is expected
    assert coordinator.module_polling.timezone is expected
    await coordinator.async_shutdown()


async def test_coordinator_default_uses_cached_ha_timezone_without_disk_lookup(hass):
    with patch("zoneinfo.ZoneInfo", side_effect=AssertionError("Synchronous zone lookup")):
        coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    assert coordinator.station_timezone is dt_util.get_default_time_zone()
    await coordinator.async_shutdown()


async def test_options_enumerate_timezones_once_in_executor(hass):
    event_loop_thread = threading.get_ident()

    def enumerate_zones():
        assert threading.get_ident() != event_loop_thread
        return {"UTC", "Europe/Berlin"}

    _time_zone_options.cache_clear()
    try:
        with patch("custom_components.hoymiles_home.config_flow.available_timezones", side_effect=enumerate_zones) as enumerate_mock:
            for station_id in (123, 456):
                entry = MockConfigEntry(domain=DOMAIN, unique_id=str(station_id), data={"station_id": station_id})
                entry.add_to_hass(hass)
                form = await hass.config_entries.options.async_init(entry.entry_id)
                schema = form["data_schema"].schema
                selector = next(value for key, value in schema.items() if key.schema == "station_timezone")
                assert selector.config["options"] == ["Europe/Berlin", "UTC"]
        enumerate_mock.assert_called_once()
    finally:
        _time_zone_options.cache_clear()
