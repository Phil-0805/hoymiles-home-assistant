"""Retain confirmed output settings, never stale measurements or other entities."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.device_migration import async_remove_last_inverter_temperature_sensors
from custom_components.hoymiles_home.diagnostics import _output_power_diagnostics
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from custom_components.hoymiles_home.number import HoymilesOutputPowerNumber
from custom_components.hoymiles_home.output_power import parse_output_settings


TREE = [{"type": 12, "sn": "ABCDEF000001", "dtu_sn": "ABCDEF000002"}]
ENTRY = SimpleNamespace(entry_id="synthetic", data={"station_id": 123})


@pytest.mark.parametrize("failed_read", [False, True])
async def test_confirmed_output_survives_night_without_refreshing_its_age(hass, freezer, failed_read):
    freezer.move_to("2026-11-12 15:00:00+00:00")
    api = AsyncMock()
    settings = parse_output_settings({"power": 2000, "max_power": 2000}, [])
    api.async_output_power_settings.return_value = settings
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.device_tree = deepcopy(TREE)
    coordinator.async_set_updated_data({"live_available": False, "live": {}})
    manager = coordinator.output_settings
    number = HoymilesOutputPowerNumber(coordinator, ENTRY)
    try:
        await manager._async_refresh()
        assert number.available
        assert number.extra_state_attributes["value_status"] == "current"
        stamp = number.extra_state_attributes["last_confirmed_at"]
        freezer.move_to("2026-11-13 05:00:00+00:00")
        if failed_read:
            api.async_output_power_settings.side_effect = HoymilesConnectionError("synthetic")
            await manager._async_refresh()
        calls = api.async_output_power_settings.await_count
        assert number.available
        assert number.native_value == 2000
        assert number.extra_state_attributes == {"value_status": "last_confirmed", "last_confirmed_at": stamp}
        assert not manager.available("output_power")  # The retained display is not a fresh read.
        diagnostic = _output_power_diagnostics(manager)
        assert diagnostic["value_status"] == "last_confirmed"
        assert diagnostic["last_confirmed_age_seconds"] == 14 * 3600
        assert api.async_output_power_settings.await_count == calls
        # A displayed cached range never bypasses a failed fresh preflight.
        api.async_output_power_settings.side_effect = HoymilesConnectionError("synthetic")
        with pytest.raises(HoymilesConnectionError):
            await manager.async_set_power(800)
        api.async_write_output_power_settings.assert_not_awaited()
        assert number.native_value == 2000
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("change", ["permission", "target", "unload", "disabled"])
async def test_retained_output_is_bound_to_controls_and_original_target(hass, freezer, change):
    api = AsyncMock()
    api.async_output_power_settings.return_value = parse_output_settings({"power": 600, "max_power": 2000}, [])
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.device_tree = deepcopy(TREE)
    manager = coordinator.output_settings
    entity = HoymilesOutputPowerNumber(coordinator, ENTRY)
    try:
        await manager._async_refresh()
        if change == "permission": coordinator.battery_controls = False
        elif change == "disabled": manager.enabled = False
        elif change == "unload": await coordinator.async_shutdown()
        else:
            coordinator.device_tree[0]["sn"] = "ABCDEF000003"
            api.async_output_power_settings.side_effect = HoymilesConnectionError("synthetic")
            await manager._async_refresh()
            # The attempted new target must not inherit the former target's snapshot.
            assert manager.target != manager.confirmed_target
        assert not entity.available
        assert manager.display_status() == "unavailable"
        api.async_write_output_power_settings.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


async def test_retained_output_uses_fresh_maximum_and_full_readback_once(hass, freezer):
    freezer.move_to("2026-11-12 15:00:00+00:00")
    api = AsyncMock()
    initial = parse_output_settings({"power": 2000, "max_power": 2000}, [])
    fresh = parse_output_settings({"power": 2000, "max_power": 800}, [])
    confirmed = parse_output_settings({"power": 800, "max_power": 800}, [])
    api.async_output_power_settings.side_effect = [initial, fresh, confirmed]
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.device_tree = deepcopy(TREE)
    manager = coordinator.output_settings
    try:
        await manager._async_refresh()
        freezer.move_to("2026-11-13 05:00:00+00:00")
        assert manager.display_status() == "last_confirmed"
        await manager.async_set_power(800)
        api.async_write_output_power_settings.assert_awaited_once_with(123, fresh, 800)
        assert manager.output == confirmed
        assert manager.display_status() == "current"
    finally:
        await coordinator.async_shutdown()


async def test_model_rating_and_restart_do_not_create_a_confirmed_output_setting(hass):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.device_tree = [{"type": 3, "id": 99, "model_no": "HMS-2000-4WB"}]
    try:
        entity = HoymilesOutputPowerNumber(coordinator, ENTRY)
        assert not entity.available
        assert entity.native_value is None
        assert coordinator.output_settings.confirmed_age_seconds() is None
        api.async_output_power_settings.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("disabled", [None, er.RegistryEntryDisabler.USER, er.RegistryEntryDisabler.INTEGRATION])
async def test_last_temperature_removal_is_exact_owned_and_idempotent(hass, disabled):
    registry, devices = er.async_get(hass), dr.async_get(hass)
    entry, other = MockConfigEntry(domain=DOMAIN), MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    other.add_to_hass(hass)
    device = devices.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "inverter_99")})
    old = registry.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_99_inverter_last_temperature",
                                      config_entry=entry, device_id=device.id)
    old = registry.async_update_entity(old.entity_id, name="Renamed", disabled_by=disabled)
    keep = []
    for domain, platform, uid, owner in [
        ("sensor", DOMAIN, f"{entry.entry_id}_99_inverter_temperature", entry),
        ("sensor", DOMAIN, f"{entry.entry_id}_battery_ABCDEF000001_temperature", entry),
        ("sensor", DOMAIN, f"{other.entry_id}_99_inverter_last_temperature", other),
        ("sensor", DOMAIN, f"{entry.entry_id}_100_inverter_last_temperature", other),
        ("sensor", "foreign", f"{entry.entry_id}_99_inverter_last_temperature", entry),
        ("number", DOMAIN, f"{entry.entry_id}_99_inverter_last_temperature", entry),
        *[("sensor", DOMAIN, f"{entry.entry_id}_{middle}_inverter_last_temperature", entry)
          for middle in ("0", "-1", "099", "True", "99_extra")],
        ("sensor", DOMAIN, f"{entry.entry_id}_99_inverter_last_temperature_extra", entry),
    ]:
        keep.append(registry.async_get_or_create(domain, platform, uid, config_entry=owner))
    async_remove_last_inverter_temperature_sensors(hass, entry)
    async_remove_last_inverter_temperature_sensors(hass, entry)
    assert registry.async_get(old.entity_id) is None
    assert devices.async_get(device.id) == device
    assert all(registry.async_get(item.entity_id) == item for item in keep)
