"""Temperature telemetry is automatic, including former opt-out entries."""

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_home import async_setup_entry as real_setup_entry
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator


@pytest.mark.parametrize("options", [{}, {"battery_temperatures": False}, {"battery_temperatures": True}])
async def test_setup_enables_temperature_polling_for_new_and_existing_entries(hass, options):
    entry = MockConfigEntry(domain=DOMAIN, data={
        "username": "test@example.com", "password": "synthetic", "station_id": 123,
    }, options=options)
    entry.add_to_hass(hass)
    with (
        patch.object(HoymilesHomeCoordinator, "async_initialize", new=AsyncMock()),
        patch.object(HoymilesHomeCoordinator, "async_config_entry_first_refresh", new=AsyncMock()),
        patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()),
        patch("custom_components.hoymiles_home.async_migrate_battery_temperatures"),
    ):
        assert await real_setup_entry(hass, entry)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.battery_telemetry.enabled is True
    assert coordinator.battery_controls is False
    assert coordinator.device_controls is False
    await coordinator.async_shutdown()


async def test_options_remove_obsolete_toggle_but_keep_unrelated_settings(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="station", data={"station_id": 123},
        options={"battery_temperatures": False, "other_option": "keep"})
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert "battery_temperatures" not in {key.schema for key in form["data_schema"].schema}
    await hass.config_entries.options.async_configure(form["flow_id"], {"pv_power_source": "auto"})
    assert "battery_temperatures" not in entry.options
    assert entry.options["other_option"] == "keep"
