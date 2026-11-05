"""Shared entity presentation for opt-in device settings."""

from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STATION_ID, DOMAIN
from .errors import HoymilesError


class DeviceSettingsEntity(CoordinatorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry, key, feature="lighting"):
        super().__init__(coordinator)
        self.feature = feature
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_device_setting_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"station_{entry.data[CONF_STATION_ID]}")},
            manufacturer="Hoymiles", name=f"S-Miles Home {entry.data[CONF_STATION_ID]}",
            model="S-Miles Home station",
        )

    @property
    def manager(self):
        return self.coordinator.device_settings

    @property
    def available(self):
        allowed = self.coordinator.battery_controls if self.feature in {"cutoffs", "output_power"} else self.coordinator.device_controls
        return (super().available and allowed
                and self.manager.available(self.feature))

    @property
    def values(self):
        return (self.manager.lighting or {}).get("values", {})

    async def _async_change(self, operation):
        try:
            await operation
        except HoymilesError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="device_setting_write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
