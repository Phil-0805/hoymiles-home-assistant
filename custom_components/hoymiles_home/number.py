"""Number platform for Hoymiles S-Miles Home."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HoymilesError
from .const import CONF_STATION_ID, DOMAIN
from .coordinator import HoymilesHomeCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up battery setting numbers."""
    coordinator: HoymilesHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([HoymilesBatteryReserveSocNumber(coordinator, entry)])


class HoymilesBatteryReserveSocNumber(
    CoordinatorEntity[HoymilesHomeCoordinator], NumberEntity
):
    """Writable reserve SOC for the active battery mode."""

    _attr_has_entity_name = True
    _attr_translation_key = "battery_reserve_soc"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 10
    _attr_native_max_value = 100
    _attr_native_step = 1

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        station_id = entry.data[CONF_STATION_ID]
        self._attr_unique_id = f"{entry.entry_id}_battery_reserve_soc_control"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"station_{station_id}")},
            manufacturer="Hoymiles",
            name=f"S-Miles Home {station_id}",
            model="S-Miles Home station",
        )

    @property
    def available(self) -> bool:
        settings = self.coordinator.battery_settings
        active = settings.get("active_settings")
        return (
            super().available
            and settings.get("readable") is True
            and isinstance(active, dict)
            and isinstance(active.get("reserve_soc"), (int, float))
        )

    @property
    def native_value(self) -> float | None:
        value = (
            self.coordinator.battery_settings.get("active_settings", {}).get(
                "reserve_soc"
            )
        )
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return None

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.async_set_battery_reserve_soc(round(value))
        except HoymilesError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="battery_setting_write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
