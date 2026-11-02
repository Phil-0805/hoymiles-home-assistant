"""Select platform for Hoymiles S-Miles Home."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HoymilesError
from .battery import BATTERY_MODE_NAMES, writable_modes
from .const import CONF_STATION_ID, DOMAIN
from .coordinator import HoymilesHomeCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up battery setting selects."""
    coordinator: HoymilesHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HoymilesBatteryModeSelect(coordinator, entry)])


class HoymilesBatteryModeSelect(
    CoordinatorEntity[HoymilesHomeCoordinator], SelectEntity
):
    """Writable battery operating mode."""

    _attr_has_entity_name = True
    _attr_translation_key = "battery_mode"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        station_id = entry.data[CONF_STATION_ID]
        self._attr_unique_id = f"{entry.entry_id}_battery_mode_control"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"station_{station_id}")},
            manufacturer="Hoymiles",
            name=f"S-Miles Home {station_id}",
            model="S-Miles Home station",
        )

    def _mode_options(self) -> dict[str, int]:
        settings = self.coordinator.battery_settings
        return {
            BATTERY_MODE_NAMES.get(mode, f"Unknown ({mode})"): mode
            for mode in writable_modes(settings)
        }

    @property
    def available(self) -> bool:
        return (
            super().available
            and self.coordinator.battery_settings.get("readable") is True
            and self.coordinator.battery_settings.get("writable") is True
            and self.coordinator.battery_settings.get("mode") in self._mode_options().values()
            and bool(self._mode_options())
        )

    @property
    def options(self) -> list[str]:
        return list(self._mode_options())

    @property
    def current_option(self) -> str | None:
        mode = self.coordinator.battery_settings.get("mode")
        if isinstance(mode, int):
            return BATTERY_MODE_NAMES.get(mode, f"Unknown ({mode})")
        return None

    @property
    def extra_state_attributes(self) -> dict:
        return {"mode_change_available": self.available and len(self._mode_options()) > 1}

    async def async_select_option(self, option: str) -> None:
        mode = self._mode_options().get(option)
        if mode is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="battery_mode_unavailable",
                translation_placeholders={"mode": option},
            )
        if mode == self.coordinator.battery_settings.get("mode"):
            return  # Selecting the displayed mode never sends a redundant write.
        try:
            await self.coordinator.async_set_battery_mode(mode)
        except HoymilesError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="battery_setting_write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
