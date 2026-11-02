"""Move b4 temperature entities without changing their identities or history."""

import re

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import CONF_STATION_ID, DOMAIN


def _owned_device(device, entry_id):
    # Never remove composite/shared devices. Older HA has a set of owners;
    # current HA stores one owner on each ordinary device entry.
    if type(device) is not dr.DeviceEntry:
        return False
    owner = getattr(device, "config_entry_id", None)
    return owner == entry_id if owner is not None else device.config_entries == {entry_id}


def _all_devices(registry):
    # New HA exposes a collection; older versions expose a mapping of IDs.
    return [registry.async_get(item) if isinstance(item, str) else item
            for item in registry.devices]


@callback
def async_migrate_battery_temperatures(hass, entry):
    """Reassign existing temperature entities, then remove only unused b4 devices."""
    devices, entities = dr.async_get(hass), er.async_get(hass)
    station_id = entry.data[CONF_STATION_ID]
    pattern = re.compile(rf"battery_{re.escape(str(station_id))}_[0-9A-F]{{12,24}}")
    old = {
        device.id: device for device in dr.async_entries_for_config_entry(devices, entry.entry_id)
        if _owned_device(device, entry.entry_id)
        and not device.connections
        and len(device.identifiers) == 1
        and any(domain == DOMAIN and pattern.fullmatch(identifier) for domain, identifier in device.identifiers)
    }
    if not old:
        return
    identifier = (DOMAIN, f"station_{station_id}")
    if hasattr(devices, "async_get_device_by_identifier"):
        target = devices.async_get_device_by_identifier(identifier, entry.entry_id)
    else:
        target = devices.async_get_device(identifiers={identifier})
    for entity in er.async_entries_for_config_entry(entities, entry.entry_id):
        if entity.device_id not in old or entity.platform != DOMAIN or entity.domain != "sensor":
            continue
        device = old[entity.device_id]
        serial = next(iter(device.identifiers))[1].removeprefix(f"battery_{station_id}_")
        if entity.unique_id != f"{entry.entry_id}_battery_{serial}_temperature":
            continue
        if target is None:
            target = devices.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"station_{station_id}")},
                manufacturer="Hoymiles", name=f"S-Miles Home {station_id}",
                model="S-Miles Home station",
            )
        entities.async_update_entity(entity.entity_id, device_id=target.id)

    # Process leaves first. Preserve any device with entities (including disabled
    # or foreign entities), physical child devices, or another device via it.
    for _ in range(len(old)):
        removed = []
        for device_id in old:
            if er.async_entries_for_device(entities, device_id, include_disabled_entities=True):
                continue
            if any(device.via_device_id == device_id for device in _all_devices(devices)):
                continue
            if any(child.parent_device_id == device_id for child in getattr(devices, "child_devices", ())):
                continue
            devices.async_remove_device(device_id)
            removed.append(device_id)
        for device_id in removed:
            old.pop(device_id)
        if not removed:
            break
