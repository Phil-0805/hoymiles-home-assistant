"""Sensor platform for Hoymiles S-Miles Home."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    EntityCategory,
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfElectricPotential,
    UnitOfTemperature,
    UnitOfFrequency,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import RestoreEntity, RestoredExtraData

from .battery import BATTERY_MODE_STATES, battery_settings_attributes
from .const import CONF_STATION_ID, DOMAIN, CONF_HISTORY_INTERVAL, HISTORY_INTERVALS, HISTORY_FLUSH_SIGNAL
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
ENDUSER_SENSOR_KEYS = {
    "pv_power", "grid_power", "load_power", "battery_power", "battery_soc",
    "battery_charge_power", "battery_discharge_power", "battery_activity",
    "load_energy_today", "battery_charge_energy_today", "battery_discharge_energy_today",
    "today_energy", "month_energy", "year_energy", "total_energy",
}
HISTORY_ENERGY_KEYS = {
    "load_energy_today", "battery_charge_energy_today", "battery_discharge_energy_today",
}
HISTORY_SENSOR_KEYS = HISTORY_ENERGY_KEYS | {
    "pv_power", "load_power", "grid_power", "battery_power",
    "battery_charge_power", "battery_discharge_power",
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
    if data.get("live", {}).get("_enduser_schema") == "es":
        return {"direction_mapping": "Enduser flow: battery inflow=charging, outflow=discharging"}
    return {"raw_codes": status_codes(data.get("live", {})),
            "direction_mapping": "brs: 0=idle, 1=charging, 2=discharging",
            "mapping_verified_on": "HMS-2000-4WB, HiBattery 4020-X",
            "other_status_meanings": "unverified"}


def _battery_charge_power(data: dict[str, Any]) -> float | int | None:
    """Return charging power as a positive value."""
    value = _live("bat")(data)
    if value is None:
        return None
    relay_status = _number(data.get("live", {}).get("brs"))
    charge, _discharge = split_battery_power(
        float(value),
        relay_status if relay_status in (0, 1, 2) else None,
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
        relay_status if relay_status in (0, 1, 2) else None,
    )
    return discharge


@dataclass(frozen=True, kw_only=True)
class HoymilesDescription(SensorEntityDescription):
    """Describe a station sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    attributes_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


def _battery_settings_attributes(data: dict[str, Any]) -> dict[str, Any]:
    return battery_settings_attributes(data.get("battery_settings", {}))


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
        device_class=SensorDeviceClass.ENUM,
        options=list(BATTERY_MODE_STATES.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: BATTERY_MODE_STATES.get(data.get("battery_settings", {}).get("mode")),
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


def _station_parent_id(coordinator, entry):
    registry = dr.async_get(coordinator.hass)
    identifier = (DOMAIN, f"station_{entry.data[CONF_STATION_ID]}")
    if hasattr(registry, "async_get_device_by_identifier"):
        parent = registry.async_get_device_by_identifier(identifier, entry.entry_id)
    else:
        parent = registry.async_get_device(identifiers={identifier})
    return parent.id if parent is not None else None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: HoymilesHomeCoordinator = hass.data[DOMAIN][entry.entry_id]
    enduser = getattr(getattr(coordinator, "client", None), "profile", "home") == "enduser"
    entities: list[SensorEntity] = [
        HoymilesStationSensor(coordinator, entry, description)
        for description in STATION_SENSORS
        if not enduser or description.key in ENDUSER_SENSOR_KEYS
    ]
    history_option = getattr(entry, "options", {}).get(CONF_HISTORY_INTERVAL, "off")
    if isinstance(history_option, str) and history_option in HISTORY_INTERVALS[1:]:
        entities.extend([
            HoymilesHistorySensor(source, entry, int(history_option))
            for source in entities if source.entity_description.key in HISTORY_SENSOR_KEYS
        ])
    for inverter in coordinator.inverters:
        if enduser:
            continue  # No evidenced Enduser module-chart implementation yet.
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
        data = self.coordinator.data or {}
        if getattr(getattr(self.coordinator, "client", None), "profile", "home") == "enduser":
            if self.native_value is None:
                return False
            calculated_source = {"load_energy_today": "load", "battery_charge_energy_today": "bat",
                                 "battery_discharge_energy_today": "bat"}.get(self.entity_description.key)
            if calculated_source and _number(live_power(data).get(calculated_source)) is None:
                return False
        if (self.entity_description.key in LIVE_SENSOR_KEYS | {
                "load_energy_today", "battery_charge_energy_today", "battery_discharge_energy_today"}
                and data.get("live_available", True) is not True):
            return False
        if self.entity_description.key in {"today_energy", "month_energy", "year_energy", "total_energy"}:
            if not self.coordinator.station_is_fresh(self.entity_description.key):
                return False
        return super().available and (
            self.entity_description.key not in LIVE_SENSOR_KEYS
            or live_connected((self.coordinator.data or {}).get("live", {}))
            or (self.entity_description.key == "pv_power" and self.native_value == 0)
        )

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.coordinator.data or {})


class HoymilesHistorySensor(CoordinatorEntity[HoymilesHomeCoordinator], RestoreEntity, SensorEntity):
    """Publish snapshots locally; the original entity and cloud stay responsive."""

    _attr_has_entity_name = True

    def __init__(self, source: HoymilesStationSensor, entry: ConfigEntry, interval: int) -> None:
        super().__init__(source.coordinator)
        self._source = source
        self._interval = interval
        self._energy = source.entity_description.key in HISTORY_ENERGY_KEYS
        key = source.entity_description.key + "_history"
        self.entity_description = replace(
            source.entity_description, key=key, translation_key=key,
            state_class=SensorStateClass.TOTAL if self._energy else source.state_class,
        )
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = source.device_info
        self._value = None
        self._cycle = None
        self._history_available = False
        self._pending = None
        self._next_sample = 0.0
        self._minimum = None
        self._minimum_cycle = None
        self._flush_signal = HISTORY_FLUSH_SIGNAL.format(entry.entry_id)
        self._cancel_boundary = None

    @property
    def available(self):
        return self._history_available

    @property
    def native_value(self):
        return self._value

    @property
    def last_reset(self) -> datetime | None:
        if self._energy and self._cycle is not None:
            return datetime.fromisoformat(self._cycle).replace(
                tzinfo=self.coordinator.station_timezone).astimezone(UTC)
        return None

    @property
    def extra_state_attributes(self):
        return {"sampling_interval_seconds": self._interval}

    async def async_added_to_hass(self) -> None:
        # Restore only a monotonicity guard, never display a restored measurement.
        if self._energy and (extra := await self.async_get_last_extra_data()) is not None:
            stored = extra.as_dict()
            today = datetime.now(UTC).astimezone(self.coordinator.station_timezone).date().isoformat()
            value = _number(stored.get("value")) if isinstance(stored, dict) else None
            if value is not None and value >= 0 and stored.get("cycle") == today:
                self._minimum, self._minimum_cycle = value, today
        await super().async_added_to_hass()
        if self._energy:
            self.async_on_remove(async_dispatcher_connect(self.hass, self._flush_signal, self._flush_energy))
            self.async_on_remove(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._flush_energy))
            self._schedule_boundary()
            self.async_on_remove(self._cancel_boundary_timer)
        self._handle_coordinator_update()

    @callback
    def _cancel_boundary_timer(self) -> None:
        if self._cancel_boundary is not None:
            self._cancel_boundary()
            self._cancel_boundary = None

    @callback
    def _schedule_boundary(self) -> None:
        # Flush an observed tail even if no live event arrives just before midnight.
        # This is a local publication timer, never a cloud refresh.
        now = datetime.now(UTC).astimezone(self.coordinator.station_timezone)
        midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), now.tzinfo)
        when = midnight.astimezone(UTC) - timedelta(seconds=self._interval)
        if when <= now.astimezone(UTC):
            midnight = datetime.combine(now.date() + timedelta(days=2), datetime.min.time(), now.tzinfo)
            when = midnight.astimezone(UTC) - timedelta(seconds=self._interval)
        self._cancel_boundary = async_track_point_in_utc_time(self.hass, self._boundary_reached, when)

    @callback
    def _boundary_reached(self, _) -> None:
        self._flush_energy()
        self._schedule_boundary()

    @property
    def extra_restore_state_data(self):
        return RestoredExtraData({"value": self._minimum, "cycle": self._minimum_cycle}) if self._energy else None

    def _publish(self, value, cycle) -> None:
        self._value, self._cycle = value, cycle
        self._history_available = True
        if self._energy:
            self._minimum, self._minimum_cycle = value, cycle
        self.async_write_ha_state()

    @callback
    def _flush_energy(self, *_) -> None:
        # Publish only an actually observed old counter, never extrapolate it.
        # Do not publish an old-day value with a new-day timestamp.
        today = datetime.now(UTC).astimezone(self.coordinator.station_timezone).date().isoformat()
        if (self._energy and self._pending is not None and self._pending[1] == today
                and self._pending != (self._value, self._cycle)):
            self._publish(*self._pending)

    @callback
    def _handle_coordinator_update(self) -> None:
        value = _number(self._source.native_value)
        available = self._source.available and value is not None
        cycle = None
        boundary = False
        if self._energy:
            now = datetime.now(UTC).astimezone(self.coordinator.station_timezone)
            cycle = (self.coordinator.data or {}).get("battery_energy", {}).get("date")
            # This also validates the source's cycle without parsing arbitrary text.
            available = available and value >= 0 and cycle == now.date().isoformat()
            if self._minimum_cycle == cycle and self._minimum is not None:
                available = available and value is not None and value >= self._minimum
            midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), now.tzinfo)
            boundary = (midnight.astimezone(UTC) - now.astimezone(UTC)).total_seconds() <= self._interval
        if not available:
            if self._history_available:
                self._flush_energy()
                self._history_available = False
                self.async_write_ha_state()
            self._pending = None
            return
        self._pending = (value, cycle)
        clock = monotonic()
        if (not self._history_available or clock >= self._next_sample
                or cycle != self._cycle or boundary):
            self._publish(value, cycle)
            self._next_sample = clock + self._interval

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
            via_device_id=_station_parent_id(coordinator, entry),
        )

    @property
    def available(self) -> bool:
        return (
            super().available
            and (live_connected((self.coordinator.data or {}).get("live", {}))
                 or (self._quota == "MODULE_POWER" and _number(self.native_value) == 0))
            and self.coordinator.module_is_fresh(self._inverter_id, self._port, self._quota)
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

    @property
    def extra_state_attributes(self):
        stamp = self.coordinator.module_polling.module_field_updated.get(
            (self._inverter_id, self._port, self._quota))
        return {"sample_time": stamp.isoformat() if stamp is not None else None,
                "last_valid_value": _number(self.native_value),
                "sample_status": "unavailable" if stamp is None else
                "fresh" if self.coordinator.module_is_fresh(self._inverter_id, self._port, self._quota) else "stale"}


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
            via_device_id=_station_parent_id(coordinator, entry),
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
        values = (self.coordinator.data or {}).get("inverter_details", {}).get(self._inverter_id, {})
        stamp = values.get(f"{self._key}_sample_time")
        return {"sample_time": stamp, "last_valid_value": _number(values.get(self._key)),
                "sample_status": "unavailable" if stamp is None else
                "fresh" if self.coordinator.module_polling.detail_is_fresh(self._inverter_id, self._key) else "stale"}


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
