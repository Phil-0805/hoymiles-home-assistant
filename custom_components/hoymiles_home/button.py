"""Read-only actions for Hoymiles S-Miles Home."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STATION_ID, DOMAIN


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([
        HoymilesRefreshBatterySettingsButton(hass.data[DOMAIN][entry.entry_id], entry)
    ])


class HoymilesRefreshBatterySettingsButton(CoordinatorEntity, ButtonEntity):
    """Read battery settings again without waiting for the scheduled interval."""

    _attr_has_entity_name = True
    _attr_translation_key = "refresh_battery_settings"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        station_id = entry.data[CONF_STATION_ID]
        self._attr_unique_id = f"{entry.entry_id}_refresh_battery_settings"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"station_{station_id}")},
            manufacturer="Hoymiles", name=f"S-Miles Home {station_id}",
        )

    async def async_press(self) -> None:
        await self.coordinator.async_refresh_battery_settings()
