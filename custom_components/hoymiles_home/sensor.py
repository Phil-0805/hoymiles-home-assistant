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
    UnitOfTemperature,
    UnitOfFrequency,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_STATION_ID, DOMAIN
from .coordinator import HoymilesHomeCoordinator
from .energy import split_battery_power
from .inverter import inverter_model, inverter_ports
from .telemetry import (
    battery_activity, live_connected, live_power, number as _number, pv_power_details, status_codes,
)

LIVE_SENSOR_KEYS = {
    "pv_power", "load_power", "grid_power", "battery_power",
    "battery_charge_power", "battery_discharge_power", "battery_soc",
    "battery_activity", "ems", "brs", "chs", "bhs",
}


def _live(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda data: _number(live_power(data).get(key))


def _station(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda data: _number(data.get("station", {}).get(key))


def _calculated_energy(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda data: _number(data.get("battery_energy", {}).get(key))


def _pv_power(data: dict[str, Any]) -> float | int | None:
    return pv_power_details(data)["value"]


def _pv_attributes(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in pv_power_details(data).items() if key != "value"}


def _status_attributes(data: dict[str, Any]) -> dict[str, Any]:
    return {"raw_codes": status_codes(data.get("live", {})),
            "direction_mapping": "brs: 0=idle, 1=charging, 2=discharging",
            "mapping_verified_on": "HMS-2000-4WB",
            "other_status_meanings": "unverified"}


def _battery_charge_power(data: dict[str, Any]) -> float | int | None:
    """Return charging power as a positive value."""
    value = _live("bat")(data)
    if value is None:
        return None
    relay_status = _number(data.get("live", {}).get("brs"))
    charge, _discharge = split_battery_power(
        float(value),
        int(relay_status) if relay_status is not None else None,
    )
    return charge


def _battery_discharge_power(data: dict[str, Any]) -> float | int | None:
    """Return discharging power as a positive value."""
    value = _live("bat")(data)
    if value is None:
        return None
    relay_status = _number(data.get("live", {}).get("brs"))
    _charge, discharge = split_battery_power(
        float(value),
        int(relay_status) if relay_status is not None else None,
    )
    return discharge


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
            "writable",
            "reserve_soc_verified",
            "reserve_soc_source",
            "unverified_action_1013_reserve_soc",
            "app_user_agent",
            "user_setting_probes",
            "work_mode_request_error",
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
        attributes_fn=_pv_attributes,
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
        key="load_energy_today",
        translation_key="load_energy_today",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_calculated_energy("consumption_wh"),
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
        value_fn=_calculated_energy("charge_wh"),
    ),
    HoymilesDescription(
        key="battery_discharge_energy_today",
        translation_key="battery_discharge_energy_today",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_calculated_energy("discharge_wh"),
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
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: _number(
            data.get("battery_settings", {})
            .get("active_settings", {})
            .get("max_power")
        ),
        attributes_fn=lambda data: {"unit_verified": False},
    ),
    HoymilesDescription(
        key="battery_activity",
        translation_key="battery_activity",
        device_class=SensorDeviceClass.ENUM,
        options=["idle", "charging", "discharging", "unrecognized"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: battery_activity(data.get("live", {})),
        attributes_fn=_status_attributes,
    ),
    *(
        HoymilesDescription(
            key=key,
            translation_key=key,
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=lambda data, field=key: data.get("live", {}).get(field),
            attributes_fn=_status_attributes,
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
        for port in inverter_ports(inverter):
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
        if coordinator.inverter_details:
            for key, unit, device_class in (
                ("temperature", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE),
                ("frequency", UnitOfFrequency.HERTZ, SensorDeviceClass.FREQUENCY),
                ("voltage", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
            ):
                entities.append(HoymilesInverterDetailSensor(
                    coordinator, entry, inverter, key, unit, device_class
                ))
    async_add_entities(entities)
    if coordinator.battery_telemetry.enabled:
        known_batteries = set()

        def add_battery_sensors():
            new = []
            for serial, record in coordinator.battery_telemetry.values.items():
                if serial not in known_batteries:
                    known_batteries.add(serial)
                    new.append(HoymilesBatteryTemperatureSensor(coordinator, entry, serial, record["parent"]))
            if new:
                async_add_entities(new)

        entry.async_on_unload(coordinator.async_add_listener(add_battery_sensors))
        add_battery_sensors()


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
    def available(self) -> bool:
        if self.entity_description.key == "battery_max_power" and self.native_value is None:
            return False
        return super().available and (
            self.entity_description.key not in LIVE_SENSOR_KEYS
            or live_connected((self.coordinator.data or {}).get("live", {}))
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
            model=inverter_model(inverter),
            serial_number=inverter.get("sn"),
            via_device=(DOMAIN, f"station_{entry.data[CONF_STATION_ID]}"),
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and live_connected((self.coordinator.data or {}).get("live", {}))
            and self.coordinator.module_is_fresh(self._inverter_id, self._port)
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


class HoymilesInverterDetailSensor(CoordinatorEntity[HoymilesHomeCoordinator], SensorEntity):
    """Optional read-only inverter telemetry from an explicitly enabled endpoint."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, inverter, key, unit, device_class):
        super().__init__(coordinator)
        self._inverter_id, self._key = inverter["id"], key
        self._attr_unique_id = f"{entry.entry_id}_{inverter['id']}_inverter_{key}"
        self._attr_translation_key = f"inverter_{key}"
        self._attr_suggested_display_precision = {"temperature": 1, "frequency": 2, "voltage": 1}[key]
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"inverter_{inverter['id']}")},
            manufacturer="Hoymiles", name="Hoymiles microinverter",
            model=inverter_model(inverter),
            via_device=(DOMAIN, f"station_{entry.data[CONF_STATION_ID]}"),
        )

    @property
    def available(self):
        return (
            super().available
            and live_connected((self.coordinator.data or {}).get("live", {}))
            and self.coordinator.module_polling.detail_is_fresh(self._inverter_id, self._key)
        )

    @property
    def native_value(self):
        return _number((self.coordinator.data or {}).get("inverter_details", {}).get(
            self._inverter_id, {}
        ).get(self._key))

    @property
    def extra_state_attributes(self):
        return {"sample_time": (self.coordinator.data or {}).get("inverter_details", {}).get(
            self._inverter_id, {}
        ).get(f"{self._key}_sample_time")}


class HoymilesBatteryTemperatureSensor(CoordinatorEntity[HoymilesHomeCoordinator], SensorEntity):
    """Celsius temperature for one battery or expansion pack, never an inverter."""

    _attr_has_entity_name = True
    _attr_translation_key = "battery_temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry, serial, parent):
        super().__init__(coordinator)
        self._serial = serial
        self._attr_unique_id = f"{entry.entry_id}_battery_{serial}_temperature"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"station_{entry.data[CONF_STATION_ID]}")},
            manufacturer="Hoymiles",
            name=f"S-Miles Home {entry.data[CONF_STATION_ID]}",
            model="S-Miles Home station",
        )

    @property
    def available(self):
        return (super().available
                and live_connected((self.coordinator.data or {}).get("live", {}))
                and self.coordinator.battery_telemetry.is_fresh(self._serial))

    @property
    def native_value(self):
        return self.coordinator.battery_telemetry.values.get(self._serial, {}).get("temperature")

    @property
    def extra_state_attributes(self):
        stamp = self.coordinator.battery_telemetry.updated.get(self._serial)
        return {"fetched_at": stamp.isoformat() if stamp else None,
                "source": "battery_device_api", "freshness_basis": "cloud_response",
                "battery_serial": self._serial}
