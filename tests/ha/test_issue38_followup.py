"""Issue 38: matching metadata, independent settings and honest chart sample age."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import logging
import struct
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity_component import EntityComponent

from custom_components.hoymiles_home.api import HoymilesHomeClient, microinverters
from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.diagnostics import async_get_config_entry_diagnostics
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from custom_components.hoymiles_home.inverter import standalone_hms_target
from custom_components.hoymiles_home.micro_data import decode_micro_details
from custom_components.hoymiles_home.module_polling import ModulePoller
from custom_components.hoymiles_home.output_power import parse_output_settings
from custom_components.hoymiles_home.protobuf import latest_module_samples, ProtobufDecodeError
from custom_components.hoymiles_home.sensor import HoymilesInverterDetailSensor
from custom_components.hoymiles_home.const import DOMAIN

RAW = [{"id": 7, "type": 2, "children": [{"id": 99, "type": 3, "sn": "ABCDEF000001"}]}]
ENRICHED = [{**RAW[0]["children"][0], "model_no": "HMS-2000-4WB",
             "_model_discovery": {"result": "identified", "source": "web_tree"}}]
SETTINGS = parse_output_settings({"power": 600, "max_power": 2000}, [])


@pytest.mark.parametrize("source", ["web_tree", "micro_detail"])
def test_matching_supplemental_model_is_used_without_mutating_raw_tree(source):
    enriched = deepcopy(ENRICHED)
    enriched[0]["_model_discovery"]["source"] = source
    before = deepcopy(RAW)
    assert standalone_hms_target(RAW) is None
    target = standalone_hms_target(RAW, enriched)
    assert target["inverter"] == {"id": 99, "model": "HMS-2000-4WB"}
    assert RAW == before
    assert "sn" not in target["inverter"]


@pytest.mark.parametrize("change", ["id", "bool_id", "type", "bool_type", "serial", "source",
                                    "unverified", "duplicate", "missing_model"])
def test_supplemental_metadata_cannot_substitute_or_ambiguate_identity(change):
    enriched = deepcopy(ENRICHED)
    item = enriched[0]
    if change == "id": item["id"] = 100
    elif change == "bool_id": item["id"] = True
    elif change == "type": item["type"] = 12
    elif change == "bool_type": item["type"] = True
    elif change == "serial": item["sn"] = "ABCDEF000002"
    elif change == "source": item["_model_discovery"]["source"] = "guessed"
    elif change == "unverified": item["_model_discovery"]["result"] = "unresolved"
    elif change == "duplicate": enriched.append(deepcopy(item))
    else: item.pop("model_no")
    assert standalone_hms_target(RAW, enriched) is None


@pytest.mark.parametrize("extra", [{"id": 100, "type": 3, "model": "HMS-800-2WB"},
                                    {"id": 100, "type": 12}, {"id": 100, "type": 99}])
def test_metadata_never_removes_mixed_tree_or_multiple_inverter_guards(extra):
    assert standalone_hms_target([*RAW, extra], ENRICHED) is None


async def test_conflicting_web_models_are_not_arbitrarily_used_for_controls():
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    candidate = {"id": 99, "type": 3, "sn": "ABCDEF000001", "model_no": "HMS-2000-4WB"}
    api._json = AsyncMock(side_effect=[
        {"status": 0, "data": [candidate, {**candidate, "model_no": "HMS-800-2WB"}]},
        {"status": 0, "data": {}}])
    enriched = await api.async_enrich_inverters(123, RAW[0]["children"])
    assert enriched[0]["_model_discovery"]["result"] == "unresolved"
    assert standalone_hms_target(RAW, enriched) is None


async def test_boolean_detail_identity_cannot_verify_integer_device_one():
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api._json = AsyncMock(side_effect=[{"status": 0, "data": []},
        {"status": 0, "data": {"id": True, "model_no": "HMS-2000-4WB"}}])
    enriched = await api.async_enrich_inverters(123, [{"id": 1, "type": 3}])
    assert enriched[0]["_model_discovery"]["result"] == "unresolved"


@pytest.mark.parametrize("node", [{"id": True, "type": 3}, {"id": -1, "type": 3},
                                  {"id": 0, "type": 3}, {"id": 99, "type": True}])
def test_inverter_discovery_rejects_nonphysical_identities(node):
    assert microinverters([node]) == []


async def test_reporter_case_reads_output_and_skips_battery_readers_with_real_enrichment(hass):
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_live = AsyncMock(side_effect=CloudDiagnosticError("missing_uri", "No live address"))
    api.async_list_stations = AsyncMock(return_value=[{"sid": 123}])
    api.async_device_tree = AsyncMock(return_value=deepcopy(RAW))
    api._json = AsyncMock(return_value={"status": 0, "data": deepcopy(ENRICHED)})
    api.async_station_realtime = AsyncMock(return_value={"today_eq": 123})
    api.async_battery_settings = AsyncMock()
    api.async_battery_temperatures = AsyncMock()
    api.async_cutoff_settings = AsyncMock()
    api.async_output_power_settings = AsyncMock(return_value=SETTINGS)
    api.async_module_values = AsyncMock(return_value={})
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True, battery_temperatures=True)
    try:
        await coordinator.async_refresh()
        await coordinator.output_settings.task
        await coordinator.cutoff_settings.task
        assert coordinator.last_update_success
        assert coordinator.data["live_available"] is False
        assert "model_no" not in coordinator.device_tree[0]["children"][0]
        assert coordinator.inverters[0]["_model_discovery"]["source"] == "web_tree"
        api.async_output_power_settings.assert_awaited_once_with(123)
        api.async_battery_settings.assert_not_awaited()
        api.async_battery_temperatures.assert_not_awaited()
        api.async_cutoff_settings.assert_not_awaited()
        assert coordinator.output_settings.available("output_power")
        entry = SimpleNamespace(entry_id="entry", data={"station_id": 123})
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)
        assert diagnostics["polling"]["standalone_hms_recognized"]
        assert diagnostics["battery_telemetry"]["enabled"]
        assert not diagnostics["battery_telemetry"]["applicable"]
        assert diagnostics["output_power_settings"]["status"] == "readable"
        assert "ABCDEF000001" not in json.dumps(diagnostics)
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("change", ["serial", "model", "permission"])
async def test_enriched_output_target_is_rechecked_after_fresh_read(hass, change):
    api = AsyncMock()
    api.async_output_power_settings.return_value = SETTINGS
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.device_tree, coordinator.inverters = deepcopy(RAW), deepcopy(ENRICHED)
    manager = coordinator.output_settings
    await manager._async_refresh()
    assert manager.available("output_power")

    async def fresh(*args):
        if change == "serial": coordinator.inverters[0]["sn"] = "ABCDEF000002"
        elif change == "model": coordinator.inverters[0]["model_no"] = "HMS-800-2WB"
        else: coordinator.battery_controls = False
        return SETTINGS

    api.async_output_power_settings.side_effect = fresh
    try:
        with pytest.raises(HoymilesConnectionError):
            await manager.async_set_power(700)
        api.async_write_output_power_settings.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("confirmed", [False, True])
async def test_enriched_output_uses_fresh_limits_and_complete_readback_without_resending(hass, confirmed):
    api = AsyncMock()
    api.async_output_power_settings.return_value = SETTINGS
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.device_tree, coordinator.inverters = deepcopy(RAW), deepcopy(ENRICHED)
    manager = coordinator.output_settings
    await manager._async_refresh()
    fresh = parse_output_settings({"power": 600, "max_power": 800}, [])
    actual = parse_output_settings({"power": 700, "max_power": 800 if confirmed else 750}, [])
    api.async_output_power_settings.side_effect = [fresh, actual]
    try:
        with patch("custom_components.hoymiles_home.device_settings.READBACK_ATTEMPTS", 1):
            if confirmed:
                await manager.async_set_power(700)
            else:
                with pytest.raises(HoymilesConnectionError, match="did not confirm"):
                    await manager.async_set_power(700)
        api.async_write_output_power_settings.assert_awaited_once_with(123, fresh, 700)
    finally:
        await coordinator.async_shutdown()


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def field(key, value):
    return varint(key * 8 + 2) + varint(len(value)) + value


def chart(series, labels=("10:00", "10:05", "23:55")):
    raw = b"".join(field(1, label.encode()) for label in labels)
    for key, values, identity, port in series:
        data = field(1, key.encode()) + field(2, struct.pack(f"<{len(values)}f", *values))
        data += varint(24) + varint(identity) + varint(32) + varint(port)
        raw += field(2, data)
    return raw


def test_module_series_keeps_sparse_field_times_and_ignores_future_tail_and_foreign_device():
    raw = chart([("MODULE_POWER", [10, 0, 999], 99, 1), ("MODULE_V", [30], 99, 1),
                 ("MODULE_I", [1, 0], 99, 1), ("MODULE_POWER", [999], 100, 1)])
    values = latest_module_samples(raw, device_id=99, port=1, latest_time="10:06")
    assert values == {"MODULE_POWER": 0, "MODULE_V": 30, "MODULE_I": 0,
                      "_sample_times": {"MODULE_POWER": "10:05", "MODULE_V": "10:00", "MODULE_I": "10:05"}}


def test_chart_time_refactor_preserves_existing_metric_precision_and_nonfinite_handling():
    value = struct.unpack("<f", struct.pack("<f", 1.234567))[0]
    micro = chart([("MI_TEMPERATURE", [value], 99, 0)])
    assert decode_micro_details(micro, [99])["inverters"][99]["temperature"] == value
    module = chart([("MODULE_POWER", [value], 99, 1), ("MODULE_V", [float("nan")], 99, 1)])
    samples = latest_module_samples(module, device_id=99, port=1)
    assert samples["MODULE_POWER"] == round(value, 3)
    assert "MODULE_V" not in samples and "MODULE_V" not in samples["_sample_times"]


async def test_module_time_cutoff_is_local_only_and_transport_remains_unchanged():
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._async_binary_data = AsyncMock(return_value=chart([("MODULE_POWER", [42], 99, 1)]))
    await api.async_module_values(123, 99, 1, "2026-11-11", latest_time="10:06")
    api._async_binary_data.assert_awaited_once_with(
        "https://neapi.hoymiles.com/pvmc/api/0/module_data/count_by_day_c",
        {"sid": 123, "date": "2026-11-11", "mi_list": [{"id": 99, "port": 1}],
         "quota": ["MODULE_POWER", "MODULE_V", "MODULE_I"]})


@pytest.mark.parametrize("raw", [chart([], labels=()), chart([], labels=("bad",)),
    chart([], labels=("10:00", "10:00")), chart([], labels=("10:05", "10:00")),
    chart([("MODULE_POWER", [1, 2], 99, 1)], labels=("10:00",)),
    chart([("MODULE_POWER", [1], 99, 1), ("MODULE_POWER", [2], 99, 1)])])
def test_bad_or_ambiguous_module_samples_are_rejected(raw):
    with pytest.raises(ProtobufDecodeError):
        latest_module_samples(raw, device_id=99, port=1)


async def test_repeated_chart_zero_does_not_refresh_age_and_sparse_metrics_expire_separately(hass, freezer):
    freezer.move_to("2026-11-11 10:06:00+00:00")
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._async_binary_data = AsyncMock(return_value=chart([
        ("MODULE_POWER", [10, 0], 99, 1), ("MODULE_V", [30], 99, 1)]))
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), False, MagicMock())
    try:
        await poller._async_poll([{"id": 99, "model_no": "HMS-800-2WB"}])
        assert poller.modules[99][1]["MODULE_POWER"] == 0
        assert poller.is_fresh(99, 1, "MODULE_V")
        freezer.move_to("2026-11-11 10:11:00+00:00")
        await poller._async_poll([{"id": 99, "model_no": "HMS-800-2WB"}])
        assert not poller.is_fresh(99, 1, "MODULE_V")
        assert poller.is_fresh(99, 1, "MODULE_POWER")
        assert poller.module_field_updated[(99, 1, "MODULE_POWER")] == datetime(2026, 11, 11, 10, 5, tzinfo=UTC)
        freezer.move_to("2026-11-11 10:16:00+00:00")
        await poller._async_poll([{"id": 99, "model_no": "HMS-800-2WB"}])
        assert not poller.is_fresh(99, 1, "MODULE_POWER")
        assert not poller.is_fresh(99, 2, "MODULE_POWER")
    finally:
        await poller.async_shutdown()


async def test_chart_dates_and_age_use_station_timezone_across_utc_midnight(hass, freezer):
    freezer.move_to("2026-11-11 23:05:00+00:00")
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._async_binary_data = AsyncMock(return_value=chart([("MODULE_POWER", [42, 0], 99, 1)],
                                                         labels=("00:00", "00:05")))
    poller = ModulePoller(hass, api, 123, ZoneInfo("Europe/Paris"), False, MagicMock())
    try:
        await poller._async_poll([{"id": 99, "model_no": "HMS-800-2WB"}])
        assert api._async_binary_data.await_args.args[1]["date"] == "2026-11-12"
        assert poller.is_fresh(99, 1, "MODULE_POWER")
        assert poller.module_field_updated[(99, 1, "MODULE_POWER")] == datetime(2026, 11, 11, 23, 5, tzinfo=UTC)
        poller._merge_module(poller.modules, 99, 1, {"MODULE_POWER": 999,
            "_sample_times": {"MODULE_POWER": "23:59"}}, "2026-11-11")
        assert poller.modules[99][1]["MODULE_POWER"] == 0
    finally:
        await poller.async_shutdown()


@pytest.mark.parametrize("date,time", [("2026-10-25", "02:30"), ("2026-03-29", "02:30")])
def test_ambiguous_or_nonexistent_dst_labels_cannot_be_claimed_fresh(hass, date, time):
    poller = ModulePoller(hass, AsyncMock(), 123, ZoneInfo("Europe/Paris"), False, MagicMock())
    assert poller._sample_stamp(date, time) is None


def test_micro_chart_genuine_zero_celsius_is_preserved_and_future_padding_is_not_a_measurement():
    raw = chart([("MI_TEMPERATURE", [5, 0, 99], 99, 0)])
    assert decode_micro_details(raw, [99], latest_time="10:06")["inverters"][99] == {
        "temperature": 0, "temperature_time": "10:05"}


async def test_stale_temperature_is_unavailable_but_keeps_last_value_and_original_timestamp(hass, freezer):
    freezer.move_to("2026-11-11 10:01:00+00:00")
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123, inverter_details=True, station_timezone=ZoneInfo("UTC"))
    poller = coordinator.module_polling
    poller._merge_details({"inverters": {99: {"time": "10:00", "temperature": 21}}}, {99}, "2026-11-11")
    coordinator.async_set_updated_data({"live": {}, "live_available": False, "inverter_details": poller.details})
    entry = SimpleNamespace(entry_id="entry", data={"station_id": 123})
    sensor = HoymilesInverterDetailSensor(coordinator, entry, {"id": 99}, "temperature",
                                        UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE)
    try:
        assert sensor.available
        freezer.move_to("2026-11-11 10:11:00+00:00")
        poller._merge_details({"inverters": {}}, {99}, "2026-11-11")
        assert not sensor.available
        assert sensor.extra_state_attributes == {"sample_time": "2026-11-11T10:00:00+00:00",
                                                 "last_valid_value": 21, "sample_status": "stale"}
    finally:
        await coordinator.async_shutdown()


async def test_real_ha_state_is_unavailable_when_current_temperature_expires(hass, freezer):
    freezer.move_to("2026-11-11 10:20:00+00:00")
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123, station_timezone=ZoneInfo("UTC"))
    coordinator.update_interval = None
    poller = coordinator.module_polling
    poller._merge_details({"inverters": {99: {"time": "10:00", "temperature": 21}}}, {99}, "2026-11-11")
    coordinator.async_set_updated_data({"live": {}, "live_available": False, "inverter_details": poller.details})
    entry = SimpleNamespace(entry_id="entry", data={"station_id": 123})
    primary = HoymilesInverterDetailSensor(coordinator, entry, {"id": 99}, "temperature",
                                         UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE)
    for entity, name in ((primary, "current"),):
        entity.entity_id = f"sensor.synthetic_{name}_temperature"
        entity._attr_device_info = None
        entity._attr_name = name
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    try:
        await component.async_add_entities([primary])
        current_state = hass.states.get(primary.entity_id)
        assert current_state.state == "unavailable"
        assert "sample_time" not in current_state.attributes
    finally:
        for entity in (primary,):
            if entity.hass is not None:
                await entity.async_remove()
        await coordinator.async_shutdown()


async def test_missing_uri_is_info_deduplicated_and_recovery_rearms_episode(caplog):
    caplog.set_level(logging.INFO)
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    missing = {"status": 0, "data": {"uri": ""}, "message": "PRIVATE"}
    api._json = AsyncMock(side_effect=[missing, missing, missing, missing,
                                     {"status": 0, "data": {"uri": "https://neapi.hoymiles.com/live"}},
                                     missing, missing])
    for _ in range(2):
        with pytest.raises(CloudDiagnosticError):
            await api._get_live_uri(123)
    assert caplog.text.count("stage=live_uri_mobile reason=missing_uri") == 1
    await api._get_live_uri(123)
    with pytest.raises(CloudDiagnosticError):
        await api._get_live_uri(123)
    assert caplog.text.count("stage=live_uri_mobile reason=missing_uri") == 2
    assert "Cloud live address recovered" in caplog.text
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)
    assert "PRIVATE" not in caplog.text
