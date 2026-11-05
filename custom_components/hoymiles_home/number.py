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
from .battery import battery_charge_limit_soc
from .const import CONF_STATION_ID, DOMAIN
from .coordinator import HoymilesHomeCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up battery setting numbers."""
    coordinator: HoymilesHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        HoymilesBatteryReserveSocNumber(coordinator, entry),
        HoymilesBatteryChargeLimitSocNumber(coordinator, entry),
    ])


class HoymilesBatteryReserveSocNumber(
    CoordinatorEntity[HoymilesHomeCoordinator], NumberEntity
):
    """Writable reserve SOC for the active battery mode."""

    _attr_has_entity_name = True
    _setting_key = "reserve_soc"
    _attr_translation_key = "battery_reserve_soc"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_min_value = 10
    _attr_native_max_value = 100
    _attr_native_step = 1

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator)
        station_id = entry.data[CONF_STATION_ID]
        self._attr_unique_id = f"{entry.entry_id}_battery_{self._setting_key}_control"
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
            and self.coordinator.battery_controls
            and settings.get("readable") is True
            and settings.get("writable") is True
            and settings.get("reserve_soc_verified") is True
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


class HoymilesBatteryChargeLimitSocNumber(HoymilesBatteryReserveSocNumber):
    """Upper charge SOC in the verified self-consumption settings path only."""

    _setting_key = "charge_limit_soc"
    _attr_translation_key = "battery_charge_limit_soc"

    @property
    def available(self) -> bool:
        return (
            super().available
            and battery_charge_limit_soc(self.coordinator.battery_settings) is not None
        )

    @property
    def native_value(self) -> float | None:
        return battery_charge_limit_soc(self.coordinator.battery_settings)

    @property
    def native_min_value(self) -> float:
        active = self.coordinator.battery_settings.get("active_settings")
        lower = active.get("reserve_soc") if isinstance(active, dict) else None
        return max(10, lower) if type(lower) is int and 0 <= lower <= 100 else 10

    async def async_set_native_value(self, value: float) -> None:
        try:
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not 10 <= value <= 100 or int(value) != value):
                raise HoymilesError("Charge limit SOC must be an integer from 10 to 100")
            await self.coordinator.async_set_battery_charge_limit_soc(int(value))
        except HoymilesError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="battery_setting_write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
