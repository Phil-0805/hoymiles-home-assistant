"""Number platform for Hoymiles S-Miles Home."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import HoymilesError
from .const import CONF_STATION_ID, DOMAIN
from .coordinator import HoymilesHomeCoordinator
from .device_settings_entity import DeviceSettingsEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up battery setting numbers."""
    coordinator: HoymilesHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        HoymilesBatteryReserveSocNumber(coordinator, entry),
    ])
    if coordinator.battery_controls:
        async_add_entities([
            HoymilesBatteryCutoffNumber(coordinator, entry, "sl"),
            HoymilesBatteryCutoffNumber(coordinator, entry, "sh"),
            HoymilesOutputPowerNumber(coordinator, entry),
        ])
    if coordinator.device_controls:
        async_add_entities([
            HoymilesDeviceSettingNumber(coordinator, entry, "display_brightness", "ldb", 100, PERCENTAGE),
            HoymilesDeviceSettingNumber(coordinator, entry, "display_off_delay", "sot", 3600, UnitOfTime.SECONDS),
            HoymilesDeviceSettingNumber(coordinator, entry, "strip_off_delay", "slot", 3600, UnitOfTime.SECONDS),
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


class HoymilesDeviceSettingNumber(DeviceSettingsEntity, NumberEntity):
    _attr_native_min_value = 0
    _attr_native_step = 1

    def __init__(self, coordinator, entry, key, field, maximum, unit):
        super().__init__(coordinator, entry, key)
        self.field = field
        self._attr_native_max_value = maximum
        self._attr_native_unit_of_measurement = unit

    @property
    def available(self):
        return super().available and self.field in self.values

    @property
    def native_value(self):
        value = self.values.get(self.field)
        if value is None:
            return None
        return round(value * 100 / 255) if self.field == "ldb" else value

    async def async_set_native_value(self, value):
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not 0 <= value <= self.native_max_value or int(value) != value):
            raise HomeAssistantError("Device setting must be a whole value within its displayed range")
        raw = round(value * 255 / 100) if self.field == "ldb" else int(value)
        await self._async_change(self.manager.async_set_lighting({self.field: raw}))


class HoymilesBatteryCutoffNumber(DeviceSettingsEntity, NumberEntity):
    """Separate app cutoffs from Android DisChargeActivity, action 1537."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_step = 1

    def __init__(self, coordinator, entry, field):
        self.field = field
        key = "battery_discharge_cutoff" if field == "sl" else "battery_charge_cutoff"
        super().__init__(coordinator, entry, key, "cutoffs")

    @property
    def manager(self):
        return self.coordinator.cutoff_settings

    @property
    def native_value(self):
        return (self.manager.cutoffs or {}).get(self.field)

    @property
    def native_min_value(self):
        lower = (self.manager.cutoffs or {}).get("sl", 10)
        return 10 if self.field == "sl" else max(50, lower + 10)

    @property
    def native_max_value(self):
        upper = (self.manager.cutoffs or {}).get("sh", 100)
        return min(70, upper - 10) if self.field == "sl" else 100

    async def async_set_native_value(self, value):
        if (type(value) not in (int, float) or not 10 <= value <= 100 or int(value) != value):
            raise HomeAssistantError("Battery cutoff must be a whole percentage within its supported range")
        await self._async_change(self.manager.async_set_cutoff(self.field, int(value)))


class HoymilesOutputPowerNumber(DeviceSettingsEntity, NumberEntity):
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_step = 1
    _attr_native_min_value = 100
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "output_power_limit", "output_power")

    @property
    def manager(self):
        return self.coordinator.output_settings

    @property
    def native_value(self):
        return (self.manager.output or {}).get("values", {}).get("total")

    @property
    def native_max_value(self):
        # HA requires a numeric bound even before the initial read. This
        # placeholder never enables a control or supplies a cloud capability.
        return (self.manager.output or {}).get("limits", {}).get("total", 100)

    async def async_set_native_value(self, value):
        if (type(value) not in (int, float) or not 100 <= value <= 2**31 - 1
                or int(value) != value):
            raise HomeAssistantError("Output power must be a whole watt value of at least 100 W")
        await self._async_change(self.manager.async_set_power(int(value)))
