"""Read-only actions for Hoymiles S-Miles Home."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STATION_ID, DOMAIN
from .device_settings_entity import DeviceSettingsEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([
        HoymilesRefreshBatterySettingsButton(hass.data[DOMAIN][entry.entry_id], entry)
    ])
    if hass.data[DOMAIN][entry.entry_id].device_controls:
        async_add_entities([HoymilesRefreshDeviceSettingsButton(hass.data[DOMAIN][entry.entry_id], entry)])
    if hass.data[DOMAIN][entry.entry_id].battery_controls:
        async_add_entities([HoymilesRefreshCutoffSettingsButton(hass.data[DOMAIN][entry.entry_id], entry)])


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
        if not await self.coordinator.async_refresh_battery_settings():
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="settings_refresh_wait",
            )


class HoymilesRefreshDeviceSettingsButton(DeviceSettingsEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "refresh_device_settings")

    @property
    def available(self):
        return (self.coordinator.last_update_success and self.coordinator.device_controls
                and self.manager.enabled and not self.manager.stopped)

    async def async_press(self):
        if not await self.manager.async_refresh():
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="settings_refresh_wait")


class HoymilesRefreshCutoffSettingsButton(HoymilesRefreshDeviceSettingsButton):
    def __init__(self, coordinator, entry):
        DeviceSettingsEntity.__init__(self, coordinator, entry, "refresh_battery_cutoffs", "cutoffs")

    @property
    def manager(self):
        return self.coordinator.cutoff_settings

    @property
    def available(self):
        return (self.coordinator.last_update_success and self.coordinator.battery_controls
                and self.manager.enabled and not self.manager.stopped)
