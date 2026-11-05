"""Remove b2 app-cutoff identities while preserving independent mode SOC data."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_home.battery import parse_work_mode_settings, work_mode_upper_soc
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.device_migration import async_remove_obsolete_charge_limit_entities
from custom_components.hoymiles_home.diagnostics import _battery_diagnostics


def settings(lower=12, upper=95):
    return parse_work_mode_settings({"code": 0, "data": {
        "mode": 2, "soc_l": lower, "soc_h": upper, "k_3": {"mode": 1},
    }})


@pytest.mark.parametrize("data", [{"mode": 2, "soc_l": 12}, {"mode": 2, "k_2": {"soc_l": 12}}])
def test_default_upper_bound_is_not_explicit_mode_evidence(data):
    parsed = parse_work_mode_settings({"code": 0, "data": data})
    assert parsed["active_settings"]["soc_h"] == 100
    assert not parsed["work_mode_upper_soc_explicit"]
    assert work_mode_upper_soc(parsed) is None


@pytest.mark.parametrize("nested", [False, True])
def test_explicit_raw_upper_bound_is_recognized_in_both_layouts(nested):
    bounds = {"soc_l": 12, "soc_h": 90}
    parsed = parse_work_mode_settings({"code": 0, "data": {"mode": 2, **({"k_2": bounds} if nested else bounds)}})
    assert work_mode_upper_soc(parsed) == 90


def test_diagnostics_do_not_present_mode_value_as_app_cutoff():
    result = _battery_diagnostics(settings(12, 80))
    assert result["work_mode_upper_soc"] == 80
    assert "charge_limit_soc" not in result


async def test_reserve_change_preserves_fresh_mode_upper_soc(hass):
    api = AsyncMock()
    api.async_battery_settings.side_effect = [settings(25, 95), settings(30, 95)]
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.battery_settings = settings(12, 100)
    await coordinator.async_set_battery_reserve_soc(30)
    api.async_write_battery_settings.assert_awaited_once_with(
        123, 1, {"reserve_soc": 30, "soc_l": 30, "soc_h": 95}, request_method="station_action_83",
    )
    api.async_write_cutoff_settings.assert_not_awaited()
    await coordinator.async_shutdown()


@pytest.mark.parametrize("disabled", [False, True])
async def test_migration_removes_only_current_entries_obsolete_entities(hass, disabled):
    registry = er.async_get(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={"station_id": 123})
    other = MockConfigEntry(domain=DOMAIN, data={"station_id": 456})
    entry.add_to_hass(hass)
    other.add_to_hass(hass)
    retired_number = registry.async_get_or_create("number", DOMAIN,
        f"{entry.entry_id}_battery_charge_limit_soc_control", config_entry=entry)
    retired_sensor = registry.async_get_or_create("sensor", DOMAIN,
        f"{entry.entry_id}_battery_charge_limit_soc", config_entry=entry)
    if disabled:
        registry.async_update_entity(retired_number.entity_id, disabled_by=er.RegistryEntryDisabler.USER)
    retained = [
        registry.async_get_or_create("number", DOMAIN, f"{entry.entry_id}_battery_reserve_soc_control", config_entry=entry),
        registry.async_get_or_create("number", DOMAIN, f"{entry.entry_id}_device_setting_battery_charge_cutoff", config_entry=entry),
        registry.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_battery_ABCDEF000001_temperature", config_entry=entry),
        registry.async_get_or_create("number", DOMAIN, f"{other.entry_id}_battery_charge_limit_soc_control", config_entry=other),
        registry.async_get_or_create("number", "foreign_integration", f"{entry.entry_id}_battery_charge_limit_soc_control", config_entry=entry),
    ]
    async_remove_obsolete_charge_limit_entities(hass, entry)
    async_remove_obsolete_charge_limit_entities(hass, entry)  # Idempotent on reload.
    assert registry.async_get(retired_number.entity_id) is None
    assert registry.async_get(retired_sensor.entity_id) is None
    for entity in retained:
        assert registry.async_get(entity.entity_id) == entity
