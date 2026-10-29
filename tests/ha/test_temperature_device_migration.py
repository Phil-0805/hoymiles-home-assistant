"""Preserve b4 temperature entity identities while regrouping station sensors."""

from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
import pytest

from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.device_migration import async_migrate_battery_temperatures

SN, PACK = "2800A0000001", "2805A0000002"


def setup_entry(hass, station=123):
    entry = MockConfigEntry(domain=DOMAIN, data={"station_id": station})
    entry.add_to_hass(hass)
    return entry


def add_old(hass, entry, serial, via=None):
    registry = dr.async_get(hass)
    kwargs = {"via_device_id": via} if via else {}
    device = registry.async_get_or_create(config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"battery_{entry.data['station_id']}_{serial}")}, **kwargs)
    entity = er.async_get(hass).async_get_or_create("sensor", DOMAIN,
        f"{entry.entry_id}_battery_{serial}_temperature", config_entry=entry,
        device_id=device.id, suggested_object_id="existing_temperature")
    return device, entity


@pytest.mark.parametrize("disabled", [False, True])
async def test_migrate_preserves_entity_id_unique_id_and_customization(hass, disabled):
    entry = setup_entry(hass)
    device, entity = add_old(hass, entry, SN)
    registry, devices = er.async_get(hass), dr.async_get(hass)
    original = registry.async_update_entity(entity.entity_id, name="My battery temperature",
        disabled_by=er.RegistryEntryDisabler.USER if disabled else None)
    async_migrate_battery_temperatures(hass, entry)
    await hass.async_block_till_done()
    target = devices.async_get_device_by_identifier((DOMAIN, "station_123"), entry.entry_id)
    moved = registry.async_get(original.entity_id)
    assert moved is not None and target is not None
    assert moved.entity_id == original.entity_id
    assert moved.unique_id == original.unique_id
    assert moved.name == original.name and moved.disabled_by == original.disabled_by
    assert moved.device_id == target.id
    assert devices.async_get(device.id) is None
    async_migrate_battery_temperatures(hass, entry)
    assert registry.async_get(original.entity_id) == moved


async def test_parent_and_pack_move_without_leaving_empty_devices(hass):
    entry = setup_entry(hass)
    main, temperature = add_old(hass, entry, SN)
    pack, pack_temperature = add_old(hass, entry, PACK, main.id)
    async_migrate_battery_temperatures(hass, entry)
    await hass.async_block_till_done()
    registry, devices = er.async_get(hass), dr.async_get(hass)
    target = devices.async_get_device_by_identifier((DOMAIN, "station_123"), entry.entry_id)
    assert registry.async_get(temperature.entity_id).device_id == target.id
    assert registry.async_get(pack_temperature.entity_id).device_id == target.id
    assert devices.async_get(main.id) is None
    assert devices.async_get(pack.id) is None


async def test_device_with_foreign_disabled_entity_is_preserved(hass):
    entry = setup_entry(hass)
    old, temperature = add_old(hass, entry, SN)
    entities = er.async_get(hass)
    other = entities.async_get_or_create("sensor", "other_integration", "other_sensor",
        device_id=old.id, disabled_by=er.RegistryEntryDisabler.USER)
    async_migrate_battery_temperatures(hass, entry)
    await hass.async_block_till_done()
    assert dr.async_get(hass).async_get(old.id) is not None
    assert entities.async_get(other.entity_id).device_id == old.id
    assert entities.async_get(temperature.entity_id).device_id != old.id


async def test_other_entry_and_non_temperature_entities_are_preserved(hass):
    entry, other = setup_entry(hass), setup_entry(hass, 456)
    other_device, other_temp = add_old(hass, other, PACK)
    old, _ = add_old(hass, entry, SN)
    entities = er.async_get(hass)
    other_sensor = entities.async_get_or_create("sensor", DOMAIN, "unrelated", config_entry=entry, device_id=old.id)
    async_migrate_battery_temperatures(hass, entry)
    assert dr.async_get(hass).async_get(other_device.id) is not None
    assert entities.async_get(other_temp.entity_id).device_id == other_device.id
    assert entities.async_get(other_sensor.entity_id).device_id == old.id
    assert dr.async_get(hass).async_get(old.id) is not None


async def test_device_used_as_parent_by_unrelated_device_is_preserved(hass):
    entry = setup_entry(hass)
    old, _ = add_old(hass, entry, SN)
    child = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "unrelated_device")}, via_device_id=old.id)
    async_migrate_battery_temperatures(hass, entry)
    assert dr.async_get(hass).async_get(old.id) is not None
    assert dr.async_get(hass).async_get(child.id).via_device_id == old.id
