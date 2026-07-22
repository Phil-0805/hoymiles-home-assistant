"""Sensor platform for Hoymiles S-Miles Home."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfElectricPotential,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STATION_ID, DOMAIN
from .coordinator import HoymilesHomeCoordinator


def _number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _live(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda data: _number(data.get("live", {}).get("power", {}).get(key))


def _station(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda data: _number(data.get("station", {}).get(key))


def _battery_energy(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda data: _number(data.get("battery_energy", {}).get(key))


def _pv_power(data: dict[str, Any]) -> float | int | None:
    power = data.get("live", {}).get("power", {})
    value = _number(power.get("pv2"))
    return value if value is not None else _number(power.get("pv"))


def _battery_charge_power(data: dict[str, Any]) -> float | int | None:
    """Return charging power as a positive value."""
    value = _live("bat")(data)
    return max(value, 0) if value is not None else None


def _battery_discharge_power(data: dict[str, Any]) -> float | int | None:
    """Return discharging power as a positive value."""
    value = _live("bat")(data)
    return max(-value, 0) if value is not None else None


@dataclass(frozen=True, kw_only=True)
class HoymilesDescription(SensorEntityDescription):
    """Describe a station sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _battery_settings_attributes(data: dict[str, Any]) -> dict[str, Any]:
    settings = data.get("battery_settings", {})
    return {
        key: settings.get(key)
        for key in (
            "mode",
            "available_modes",
            "available_mode_names",
            "active_settings",
            "mode_settings",
            "request_method",
            "error",
        )
        if settings.get(key) is not None
    }


STATION_SENSORS = (
    HoymilesDescription(
        key="pv_power",
        translation_key="pv_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_pv_power,
    ),
    HoymilesDescription(
        key="load_power",
        translation_key="load_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_live("load"),
    ),
    HoymilesDescription(
        key="grid_power",
        translation_key="grid_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_live("grid"),
    ),
    HoymilesDescription(
        key="battery_power",
        translation_key="battery_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_live("bat"),
    ),
    HoymilesDescription(
        key="battery_charge_power",
        translation_key="battery_charge_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_battery_charge_power,
    ),
    HoymilesDescription(
        key="battery_discharge_power",
        translation_key="battery_discharge_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_battery_discharge_power,
    ),
    HoymilesDescription(
        key="battery_soc",
        translation_key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _number(data.get("live", {}).get("soc")),
    ),
    HoymilesDescription(
        key="battery_charge_energy_today",
        translation_key="battery_charge_energy_today",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_battery_energy("charge_wh"),
    ),
    HoymilesDescription(
        key="battery_discharge_energy_today",
        translation_key="battery_discharge_energy_today",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_battery_energy("discharge_wh"),
    ),
    HoymilesDescription(
        key="battery_settings_access",
        translation_key="battery_settings_access",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            "readable"
            if data.get("battery_settings", {}).get("readable")
            else "unavailable"
        ),
        attributes_fn=_battery_settings_attributes,
    ),
    HoymilesDescription(
        key="battery_mode",
        translation_key="battery_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("battery_settings", {}).get("mode_name"),
        attributes_fn=_battery_settings_attributes,
    ),
    HoymilesDescription(
        key="battery_reserve_soc",
        translation_key="battery_reserve_soc",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _number(
            data.get("battery_settings", {})
            .get("active_settings", {})
            .get("reserve_soc")
        ),
    ),
    HoymilesDescription(
        key="battery_max_power",
        translation_key="battery_max_power",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _number(
            data.get("battery_settings", {})
            .get("active_settings", {})
            .get("max_power")
        ),
    ),
    *(
        HoymilesDescription(
            key=key,
            translation_key=key,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data, field=key: data.get("live", {}).get(field),
        )
        for key in ("ems", "brs", "chs", "bhs")
    ),
    HoymilesDescription(
        key="today_energy",
        translation_key="today_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_station("today_eq"),
    ),
    HoymilesDescription(
        key="month_energy",
        translation_key="month_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_station("month_eq"),
    ),
    HoymilesDescription(
        key="year_energy",
        translation_key="year_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_station("year_eq"),
    ),
    HoymilesDescription(
        key="total_energy",
        translation_key="total_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_station("total_eq"),
    ),
)


MODULE_SENSORS = (
    ("power", "MODULE_POWER", UnitOfPower.WATT, SensorDeviceClass.POWER),
    ("voltage", "MODULE_V", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
    (
        "current",
        "MODULE_I",
        UnitOfElectricCurrent.AMPERE,
        SensorDeviceClass.CURRENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: HoymilesHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        HoymilesStationSensor(coordinator, entry, description)
        for description in STATION_SENSORS
    ]
    for inverter in coordinator.inverters:
        for port in range(1, 5):
            for key, quota, unit, device_class in MODULE_SENSORS:
                entities.append(
                    HoymilesModuleSensor(
                        coordinator,
                        entry,
                        inverter,
                        port,
                        key,
                        quota,
                        unit,
                        device_class,
                    )
                )
    async_add_entities(entities)


class HoymilesStationSensor(CoordinatorEntity[HoymilesHomeCoordinator], SensorEntity):
    """A station-level sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, description: HoymilesDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        station_id = entry.data[CONF_STATION_ID]
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"station_{station_id}")},
            manufacturer="Hoymiles",
            name=f"S-Miles Home {station_id}",
            model="S-Miles Home station",
        )

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data or {})


class HoymilesModuleSensor(CoordinatorEntity[HoymilesHomeCoordinator], SensorEntity):
    """A PV-input sensor."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator,
        entry,
        inverter: dict[str, Any],
        port: int,
        key: str,
        quota: str,
        unit,
        device_class,
    ) -> None:
        super().__init__(coordinator)
        self._inverter_id = inverter["id"]
        self._port = port
        self._quota = quota
        self._attr_translation_key = f"module_{key}"
        self._attr_translation_placeholders = {"port": str(port)}
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_unique_id = f"{entry.entry_id}_{self._inverter_id}_pv{port}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"inverter_{self._inverter_id}")},
            manufacturer="Hoymiles",
            name="Hoymiles microinverter",
            model="HMS-2000-4WB",
            serial_number=inverter.get("sn"),
            via_device=(DOMAIN, f"station_{entry.data[CONF_STATION_ID]}"),
        )

    @property
    def native_value(self):
        return (
            (self.coordinator.data or {})
            .get("modules", {})
            .get(self._inverter_id, {})
            .get(self._port, {})
            .get(self._quota)
        )
