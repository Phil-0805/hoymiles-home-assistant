"""Retire only the exact owned raw sensor; preserve output controls and peers."""

from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
import pytest

from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.device_migration import async_remove_obsolete_max_power_sensor


@pytest.mark.parametrize("disabled", [None, er.RegistryEntryDisabler.USER, er.RegistryEntryDisabler.INTEGRATION])
async def test_only_owned_exact_raw_max_power_sensor_is_removed(hass, disabled):
    registry, devices = er.async_get(hass), dr.async_get(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={"station_id": 123})
    other = MockConfigEntry(domain=DOMAIN, data={"station_id": 456})
    entry.add_to_hass(hass)
    other.add_to_hass(hass)
    station = devices.async_get_or_create(config_entry_id=entry.entry_id,
                                         identifiers={(DOMAIN, "station_123")})
    old = registry.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_battery_max_power",
                                      config_entry=entry, device_id=station.id)
    old = registry.async_update_entity(old.entity_id, name="Custom old sensor name", disabled_by=disabled)
    retained = [
        registry.async_get_or_create("number", DOMAIN, f"{entry.entry_id}_device_setting_output_power_limit",
                                     config_entry=entry, device_id=station.id),
        registry.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_battery_power", config_entry=entry),
        registry.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_battery_max_power_extra", config_entry=entry),
        registry.async_get_or_create("number", DOMAIN, f"{entry.entry_id}_battery_max_power", config_entry=entry),
        registry.async_get_or_create("sensor", DOMAIN, f"{other.entry_id}_battery_max_power", config_entry=other),
        registry.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_battery_max_power_misowned", config_entry=other),
        registry.async_get_or_create("sensor", "foreign_integration", f"{entry.entry_id}_battery_max_power", config_entry=entry),
    ]
    async_remove_obsolete_max_power_sensor(hass, entry)
    async_remove_obsolete_max_power_sensor(hass, entry)
    assert registry.async_get(old.entity_id) is None
    assert devices.async_get(station.id) == station
    for entity in retained:
        assert registry.async_get(entity.entity_id) == entity


async def test_matching_unique_id_attached_to_other_config_is_preserved(hass):
    registry = er.async_get(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={"station_id": 123})
    other = MockConfigEntry(domain=DOMAIN, data={"station_id": 456})
    entry.add_to_hass(hass)
    other.add_to_hass(hass)
    entity = registry.async_get_or_create("sensor", DOMAIN, f"{entry.entry_id}_battery_max_power", config_entry=other)
    async_remove_obsolete_max_power_sensor(hass, entry)
    assert registry.async_get(entity.entity_id) == entity
