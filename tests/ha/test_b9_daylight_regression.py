"""Daylight follow-up: real API decoding, Home topology and diagnostic privacy."""

from copy import deepcopy
from datetime import UTC, datetime
import json
import logging
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfElectricCurrent, UnitOfElectricPotential, UnitOfPower, UnitOfTemperature
from homeassistant.helpers.entity_component import EntityComponent

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.diagnostics import async_get_config_entry_diagnostics
from custom_components.hoymiles_home.errors import (
    HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError, HoymilesTelemetryError,
)
from custom_components.hoymiles_home.inverter import standalone_hms_assessment, standalone_hms_target
from custom_components.hoymiles_home.module_polling import ModulePoller
from custom_components.hoymiles_home.output_power import parse_output_settings
from custom_components.hoymiles_home.protobuf import (
    ProtobufDecodeError, chart_labels, decode_line_chart, latest_module_samples,
)
from custom_components.hoymiles_home.sensor import (
    HoymilesModuleSensor, HoymilesInverterDetailSensor, HoymilesStationSensor, STATION_SENSORS,
)


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def field(key, value):
    return varint(key * 8 + 2) + varint(len(value)) + value


def chart(labels, quota="MODULE_POWER", values=(0,), port=1):
    series = field(1, quota.encode()) + field(2, struct.pack(f"<{len(values)}f", *values))
    series += varint(24) + varint(99) + varint(32) + varint(port)
    return b"".join(field(1, label.encode()) for label in labels) + field(2, series)


HMS = {"id": 99, "type": 3, "sn": "ABCDEF000001"}
TREE = [{"id": 7, "type": 1, "devices": [HMS]}]
SETTINGS = parse_output_settings({"power": 600, "max_power": 2000}, [])


@pytest.mark.parametrize("tree", [TREE, [{"id": 7, "type": 1, "children": [HMS]}],
    [{"id": 7, "type": 1, "devices": [{"id": 8, "type": 2, "devices": [HMS]}]}]])
async def test_manufacturer_home_dtu_topology_uses_station_output_without_battery_probes(hass, tree):
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_live = AsyncMock(return_value={"con": 1, "power": {"pv": 0}})
    api.async_station_realtime = AsyncMock(return_value={})
    api.async_device_tree = AsyncMock(return_value=deepcopy(tree))
    api._json = AsyncMock(return_value={"status": 0, "data": [
        {**HMS, "model_no": "HMS-2000-4WB"}]})
    api.async_battery_settings = AsyncMock()
    api.async_battery_temperatures = AsyncMock()
    api.async_cutoff_settings = AsyncMock()
    api.async_output_power_settings = AsyncMock(return_value=SETTINGS)
    api.async_module_values = AsyncMock(return_value={})
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True, battery_temperatures=True)
    try:
        await coordinator.async_refresh()
        for task in (coordinator.output_settings.task, coordinator.cutoff_settings.task,
                     coordinator.module_polling.task):
            if task:
                await task
        assert coordinator.last_update_success
        assert coordinator.output_settings.available("output_power")
        api.async_output_power_settings.assert_awaited_once_with(123)
        api.async_battery_settings.assert_not_awaited()
        api.async_battery_temperatures.assert_not_awaited()
        api.async_cutoff_settings.assert_not_awaited()
        entry = SimpleNamespace(entry_id="synthetic", data={"station_id": 123})
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        diagnostic = await async_get_config_entry_diagnostics(hass, entry)
        assert diagnostic["polling"]["standalone_hms_reason"] == "recognized"
        assert diagnostic["battery_telemetry"]["applicable"] is False
        assert diagnostic["pv_power"]["value"] == 0
        assert "ABCDEF000001" not in json.dumps(diagnostic)
        assert coordinator.device_tree == tree
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(("tree", "reason"), [
    (None, "unsupported_tree_shape"), ([], "empty_tree"),
    ([{**HMS, "model_no": "HMS-2000-4WB", "devices": {}}], "invalid_children"),
    ([{**HMS, "model_no": "HMS-2000-4WB", "devices": [{"id": 12, "type": 12}]}], "storage_present"),
    ([{**HMS, "model_no": "HMS-2000-4WB", "devices": [{"id": 10, "type": 10}]}], "unsupported_device_type"),
    ([{**HMS, "model_no": "HMS-2000-4WB", "devices": [{"id": 9, "type": 99}]}], "unsupported_device_type"),
    ([{**TREE[0], "id": True}], "invalid_device_id"),
    ([{**TREE[0], "devices": [HMS, HMS]}], "duplicate_device"),
    ([{**TREE[0], "children": [HMS]}], "duplicate_device"),
    ([{**TREE[0], "devices": [HMS, {**HMS, "id": 100}]}], "multiple_inverters"),
    ([{"id": 7, "type": 1, "metadata": HMS}], "no_inverter"),
])
def test_home_topology_guards_and_reasons(tree, reason):
    enriched = [{**HMS, "model_no": "HMS-2000-4WB",
                 "_model_discovery": {"result": "identified", "source": "web_tree"}},
                {**HMS, "id": 100, "model_no": "HMS-2000-4WB",
                 "_model_discovery": {"result": "identified", "source": "web_tree"}}]
    before = deepcopy(tree)
    assert standalone_hms_assessment(tree, enriched) == (None, reason)
    assert standalone_hms_target(tree, enriched) is None
    assert tree == before


@pytest.mark.parametrize("labels", [("9:50", "10:05", "24:00"), ("09:50", "10:05", "24:00")])
async def test_real_chart_api_keeps_valid_zero_and_temperature_before_day_end(hass, freezer, labels):
    freezer.move_to("2026-11-12 10:04:30+00:00")
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._async_binary_data = AsyncMock(side_effect=[
        chart(labels, "MI_TEMPERATURE", (12.2, 0, 999), 0),
        chart(labels, values=(20, 0, 999)),
    ])
    api.async_module_snapshot = AsyncMock(return_value={"inverters": {}})
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), True, MagicMock())
    try:
        # One physical input limits this synthetic batch to one module request.
        await poller._async_poll([{"id": 99, "model_no": "HMS-400-1WB"}])
        assert api._async_binary_data.await_count == 2
        assert poller.details[99]["temperature"] == 0
        assert poller.modules[99][1]["MODULE_POWER"] == 0
        assert poller.detail_is_fresh(99, "temperature")
        assert poller.is_fresh(99, 1, "MODULE_POWER")
        assert poller.details_status == "readable"
        assert poller.module_field_updated[(99, 1, "MODULE_POWER")] == datetime(2026, 11, 12, 10, 5, tzinfo=UTC)
        summary = poller.diagnostics(99, [1])
        assert summary["pv_inputs"][0]["fields"]["power"] == {"status": "fresh", "age_seconds": -30}
        assert summary["detail_fields"]["voltage"]["status"] == "missing"
        freezer.move_to("2026-11-12 10:15:01+00:00")
        assert not poller.is_fresh(99, 1, "MODULE_POWER")
        assert not poller.detail_is_fresh(99, "temperature")
    finally:
        await poller.async_shutdown()


@pytest.mark.parametrize(("labels", "values", "reason"), [
    ([], [1], "empty_axis"), (["private-device-token"], [1], "unsupported_axis_format"),
    (["24:01"], [1], "unsupported_axis_format"), (["25:00"], [1], "unsupported_axis_format"),
    (["9:05", "09:05"], [1, 2], "unordered_axis"),
    (["10:05", "09:05"], [1, 2], "unordered_axis"),
    (["10:05"], [1, 2], "misaligned_series"),
])
async def test_decoder_failure_reason_survives_api_and_poller_without_cloud_contents(hass, freezer, labels, values, reason):
    freezer.move_to("2026-11-12 10:06:00+00:00")
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._async_binary_data = AsyncMock(return_value=chart(labels, values=values))
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), False, MagicMock())
    try:
        await poller._async_poll([{"id": 99, "model_no": "HMS-400-1WB"}])
        summary = poller.diagnostics(99, [1])
        assert summary["pv_inputs"][0]["read_status"] == reason
        assert not poller.is_fresh(99, 1, "MODULE_POWER")
        assert "private-device-token" not in json.dumps(summary)
        api._async_binary_data.assert_awaited_once()
    finally:
        await poller.async_shutdown()


def test_boundary_does_not_become_midnight_and_future_samples_are_not_substituted():
    raw = chart(["10:05", "10:10", "24:00"], values=[1, 2, 999])
    assert latest_module_samples(raw, device_id=99, port=1, latest_time="10:06")["MODULE_POWER"] == 1
    assert latest_module_samples(raw, device_id=99, port=1)["_sample_times"] == {"MODULE_POWER": "10:10"}
    raw = chart(["24:00"], values=[0])
    assert latest_module_samples(raw, device_id=99, port=1) == {"_sample_times": {}}
    with pytest.raises(ProtobufDecodeError):
        chart_labels(decode_line_chart(chart(["24:00", "00:00"], values=[1, 2])))


async def test_cutoff_tolerance_does_not_wrap_at_station_midnight(hass, freezer):
    freezer.move_to("2026-11-12 22:59:30+00:00")
    poller = ModulePoller(hass, AsyncMock(), 123, ZoneInfo("Europe/Paris"), False, MagicMock())
    assert poller._chart_cutoff("2026-11-12") == "23:59"
    assert poller._sample_stamp("2026-11-12", "24:00") is None
    await poller.async_shutdown()


@pytest.mark.parametrize(("error", "reason"), [
    (HoymilesConnectionError("private-payload"), "connection"),
    (HoymilesAuthError("private-token"), "authentication"),
    (HoymilesRateLimitError("private-url", 900), "rate_limited"),
    (HoymilesTelemetryError("unsupported_axis_format"), "unsupported_axis_format"),
])
async def test_snapshot_failure_has_no_micro_fallback_and_preserves_fixed_reason(hass, error, reason):
    api = AsyncMock()
    api.async_module_snapshot.side_effect = error
    api.async_module_values.return_value = {}
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), True, MagicMock())
    try:
        await poller._async_poll([{"id": 99, "model_no": "HMS-400-1WB"}])
        assert poller.detail_read_status == {"snapshot": reason, "micro_chart": "not_requested"}
        api.async_micro_details.assert_not_awaited()
        assert "private" not in json.dumps(poller.diagnostics(99, [1]))
    finally:
        await poller.async_shutdown()


async def test_readable_summary_does_not_claim_all_fields_are_fresh(hass, freezer):
    freezer.move_to("2026-11-12 10:06:00+00:00")
    api = AsyncMock()
    api.async_module_snapshot.return_value = {"inverters": {99: {
        "time": "10:05", "frequency": 50, "temperature_time": "09:00", "temperature": 12.2}}}
    api.async_micro_details.return_value = {"inverters": {}}
    api.async_module_values.return_value = {}
    coordinator = HoymilesHomeCoordinator(hass, api, 123, inverter_details=True, station_timezone=ZoneInfo("UTC"))
    coordinator.last_update_success = True
    coordinator.inverters = [{"id": 99, "model_no": "HMS-400-1WB"}]
    coordinator.data = {"live": {"con": 1}, "modules": {}}
    poller = coordinator.module_polling
    try:
        await poller._async_poll(coordinator.inverters)
        assert poller.details_status == "readable"
        summary = poller.diagnostics(99, [1])
        assert summary["detail_fields"]["temperature"] == {"status": "stale", "age_seconds": 3960}
        assert summary["detail_fields"]["frequency"]["status"] == "fresh"
        assert summary["pv_inputs"][0]["fields"]["power"]["status"] == "missing"
        assert summary["detail_reads"] == {"snapshot": "success", "micro_chart": "success"}
        # The export must add explanation without changing sample age or values.
        assert poller.details[99]["temperature"] == 12.2
        assert not poller.detail_is_fresh(99, "temperature")
    finally:
        await coordinator.async_shutdown()


async def test_all_four_pv_inputs_publish_genuine_zero_in_ha_and_stale_temperature_expires(hass, freezer):
    freezer.move_to("2026-11-12 09:06:00+00:00")
    labels = ["9:00", "9:05", "24:00"]
    module = chart(labels, values=[5, 0, 999], port=0)
    module += chart([], "MODULE_V", [30, 0, 999], port=0)
    module += chart([], "MODULE_I", [1, 0, 999], port=0)
    micro = chart(labels, "MI_TEMPERATURE", [12.2, 0, 999], port=0)
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_ensure_login = AsyncMock()
    api.async_module_snapshot = AsyncMock(return_value={"inverters": {}})
    api._async_binary_data = AsyncMock(side_effect=[micro, module, module, module, module])
    coordinator = HoymilesHomeCoordinator(hass, api, 123, inverter_details=True, station_timezone=ZoneInfo("UTC"))
    coordinator.update_interval = None
    inverter = {**HMS, "model_no": "HMS-2000-4WB"}
    coordinator.inverters = [inverter]
    poller = coordinator.module_polling
    entry = SimpleNamespace(entry_id="synthetic", data={"station_id": 123})
    entities = []
    try:
        await poller._async_poll([inverter])
        assert api._async_binary_data.await_count == 5
        coordinator.async_set_updated_data({"live": {"con": 1, "power": {"pv": 0}},
                                           "modules": poller.modules, "inverter_details": poller.details})
        for port in range(1, 5):
            for key, quota, unit, kind in (
                ("power", "MODULE_POWER", UnitOfPower.WATT, SensorDeviceClass.POWER),
                ("voltage", "MODULE_V", UnitOfElectricPotential.VOLT, SensorDeviceClass.VOLTAGE),
                ("current", "MODULE_I", UnitOfElectricCurrent.AMPERE, SensorDeviceClass.CURRENT),
            ):
                entity = HoymilesModuleSensor(coordinator, entry, inverter, port, key, quota, unit, kind)
                entity.entity_id = f"sensor.synthetic_pv{port}_{key}"
                entities.append(entity)
        temperature = HoymilesInverterDetailSensor(coordinator, entry, inverter, "temperature",
                                                  UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE)
        temperature.entity_id = "sensor.synthetic_temperature"
        entities.append(temperature)
        for entity in entities:
            entity._attr_name = entity.entity_id
            entity._attr_device_info = None
        component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
        await component.async_add_entities(entities)
        for entity in entities:
            assert float(hass.states.get(entity.entity_id).state) == 0
        freezer.move_to("2026-11-12 09:16:00+00:00")
        for entity in entities:
            entity.async_write_ha_state()
            assert hass.states.get(entity.entity_id).state == "unavailable"
        # Neither exporting nor aging causes a request or turns missing data into zero.
        poller.diagnostics(99, [1, 2, 3, 4])
        assert api._async_binary_data.await_count == 5
    finally:
        for entity in entities:
            if entity.hass is not None:
                await entity.async_remove()
        await coordinator.async_shutdown()


@pytest.mark.parametrize(("connected", "live_available", "value", "available"), [
    (0, True, 0, True), (0, True, None, False), (0, True, 42, False),
    (0, False, 0, False), (1, True, 0, True),
])
async def test_explicit_offline_pv_zero_is_visible_but_missing_live_does_not_become_zero(
    hass, connected, live_available, value, available
):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    coordinator.async_set_updated_data({"live_available": live_available,
        "live": {"con": connected, "power": {"pv": value}}})
    sensor = HoymilesStationSensor(coordinator, SimpleNamespace(entry_id="synthetic", data={"station_id": 123}),
                                  next(item for item in STATION_SENSORS if item.key == "pv_power"))
    try:
        assert sensor.available is available
        assert sensor.native_value == value
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("value", [0, None, 42])
async def test_offline_module_power_requires_an_explicit_fresh_zero(hass, freezer, value):
    freezer.move_to("2026-11-12 09:06:00+00:00")
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123, station_timezone=ZoneInfo("UTC"))
    poller = coordinator.module_polling
    poller._merge_module(poller.modules, 99, 1, {"MODULE_POWER": value,
        "_sample_times": {"MODULE_POWER": "09:05"}}, "2026-11-12")
    coordinator.async_set_updated_data({"live": {"con": 0}, "modules": poller.modules})
    sensor = HoymilesModuleSensor(coordinator, SimpleNamespace(entry_id="synthetic", data={"station_id": 123}),
                                 HMS, 1, "power", "MODULE_POWER", UnitOfPower.WATT, SensorDeviceClass.POWER)
    try:
        assert sensor.available is (value == 0)
        freezer.move_to("2026-11-12 09:16:00+00:00")
        assert not sensor.available
    finally:
        await coordinator.async_shutdown()
