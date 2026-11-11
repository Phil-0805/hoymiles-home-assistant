"""Issue 38: narrowly scoped standalone controls and timestamped Home charts."""

from copy import deepcopy
from datetime import UTC, datetime
import json
import struct
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.diagnostics import _output_power_diagnostics
from custom_components.hoymiles_home.errors import HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError
from custom_components.hoymiles_home.inverter import standalone_hms_target
from custom_components.hoymiles_home.micro_data import decode_micro_details
from custom_components.hoymiles_home.module_polling import ModulePoller
from custom_components.hoymiles_home.output_power import parse_output_settings
from custom_components.hoymiles_home.protobuf import ProtobufDecodeError

HMS = {"id": 99, "type": 3, "model_no": "HMS-2000-4WB"}
TREE = [{"id": 7, "type": 2, "children": [HMS]}]
SETTINGS = parse_output_settings({"power": 600, "max_power": 2000}, [])


@pytest.mark.parametrize("tree", [[], None, {}, [HMS, HMS], [{**HMS, "id": True}],
    [{**HMS, "id": 0}], [{**HMS, "model_no": "unknown"}],
    [HMS, {"id": 1, "type": 12}], [HMS, {"id": 1, "type": 99}],
    [{**HMS, "type": True}], [{**HMS, "children": {}}],
    [HMS, {**HMS, "id": 100}], [{**HMS, "extra": {"type": 12}}]])
def test_incomplete_mixed_or_multiple_trees_never_enable_standalone(tree):
    assert standalone_hms_target(tree) is None


async def test_standalone_skips_battery_settings_and_temperatures_but_reads_output(hass):
    api = AsyncMock()
    api.async_live.return_value = {"con": 1, "power": {"pv": 123}}
    api.async_station_realtime.return_value = {}
    api.async_module_values.return_value = {}
    api.async_output_power_settings.return_value = SETTINGS
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True, battery_temperatures=True)
    coordinator.device_tree = deepcopy(TREE)
    coordinator.inverters = [HMS]
    try:
        assert await coordinator.async_refresh_battery_settings() is False
        await coordinator._async_update_data()
        await coordinator.output_settings.task
        await coordinator.cutoff_settings.task
        await coordinator.module_polling.task
        api.async_battery_settings.assert_not_awaited()
        api.async_battery_temperatures.assert_not_awaited()
        api.async_cutoff_settings.assert_not_awaited()
        api.async_output_power_settings.assert_awaited_once_with(123)
        assert coordinator.output_settings.available("output_power")
        assert coordinator.battery_settings["error"] == "not_applicable"
        assert "inverter" not in json.dumps(_output_power_diagnostics(coordinator.output_settings))
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("tree", [[], [{"id": 99, "type": 3}], [*TREE, {"type": 12, "id": 1}]])
async def test_unknown_or_battery_tree_retains_existing_settings_reader(hass, tree):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.device_tree = tree
    try:
        assert await coordinator.async_refresh_battery_settings()
        api.async_battery_settings.assert_awaited_once_with(123)
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("change", [None, "target", "permission", "unload", "limit", "readback"])
async def test_standalone_output_keeps_preflight_and_full_readback(hass, change):
    api = AsyncMock()
    api.async_output_power_settings.return_value = SETTINGS
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.device_tree = deepcopy(TREE)
    manager = coordinator.output_settings
    await manager._async_refresh()
    api.reset_mock()

    async def fresh(station):
        if change == "target":
            coordinator.device_tree[0]["children"][0]["id"] = 100
        elif change == "permission":
            coordinator.battery_controls = False
        elif change == "unload":
            await coordinator.async_shutdown()
        return parse_output_settings({"power": 600, "max_power": 650 if change == "limit" else 2000}, [])

    actual = parse_output_settings({"power": 700, "max_power": 1800 if change == "readback" else 2000}, [])
    count = 0

    async def reads(station):
        nonlocal count
        count += 1
        return await fresh(station) if count == 1 else actual

    api.async_output_power_settings.side_effect = reads
    try:
        with patch("custom_components.hoymiles_home.device_settings.READBACK_ATTEMPTS", 1):
            if change:
                with pytest.raises(HoymilesConnectionError):
                    await manager.async_set_power(700)
            else:
                await manager.async_set_power(700)
                assert manager.output == actual
        assert api.async_write_output_power_settings.await_count == (1 if change in (None, "readback") else 0)
        if change is None:
            api.async_write_output_power_settings.assert_awaited_once_with(123, SETTINGS, 700)
        api.async_write_cutoff_settings.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    return bytes(result + bytes([value]))


def field(number, value):
    return varint(number * 8 + 2) + varint(len(value)) + value


def chart(series=None, labels=("10:00", "10:05")):
    series = [(99, "MI_TEMPERATURE", [20, 21], 0)] if series is None else series
    raw = b"".join(field(1, label.encode()) for label in labels)
    for identity, key, values, port in series:
        data = field(1, key.encode()) + field(2, struct.pack(f"<{len(values)}f", *values))
        data += varint(24) + varint(identity) + varint(32) + varint(port)
        raw += field(2, data)
    return raw


def test_micro_chart_keeps_each_metric_sample_age_and_rejects_other_identities():
    raw = chart([(99, "MI_TEMPERATURE", [20, 21], 0), (99, "MI_NET_RATE", [50], 0),
                 (100, "MI_NET_V", [230, 231], 0), (0, "MI_NET_V", [230, 231], 0),
                 (99, "MI_NET_V", [230, 231], 1)])
    assert decode_micro_details(raw, [99]) == {"inverters": {99: {
        "temperature": 21, "temperature_time": "10:05", "frequency": 50, "frequency_time": "10:00"}}}


@pytest.mark.parametrize("raw", [chart(labels=("10:05", "10:00")), chart(labels=("tomorrow",)),
    chart(labels=("10:00", "10:00")), chart(labels=()), chart(labels=("10:00",)),
    chart([(99, "MI_TEMPERATURE", [20], 0), (99, "MI_TEMPERATURE", [21], 0)]), b"\x00"])
def test_micro_chart_rejects_ambiguous_misaligned_or_malformed_data(raw):
    with pytest.raises(ProtobufDecodeError):
        decode_micro_details(raw, [99])


async def test_micro_transport_matches_home_app_exactly():
    api = HoymilesHomeClient(MagicMock(), "test@example.com", "secret")
    api.async_ensure_login = AsyncMock()
    api._async_binary_data = AsyncMock(return_value=chart())
    assert (await api.async_micro_details(123, [99], "2026-11-11"))["inverters"][99]["temperature"] == 21
    api._async_binary_data.assert_awaited_once_with(
        "https://neapi.hoymiles.com/pvmc/api/0/micro_data/count_by_day_c",
        {"sid": 123, "date": "2026-11-11", "mi_list": [99],
         "quota": ["MI_TEMPERATURE", "MI_NET_RATE", "MI_NET_V"]})


async def test_fallback_uses_chart_timestamps_and_does_not_renew_old_or_future_values(hass, freezer):
    freezer.move_to("2026-11-11 10:06:00+00:00")
    api = AsyncMock()
    api.async_module_snapshot.return_value = {"inverters": {}}
    api.async_micro_details.return_value = decode_micro_details(chart([
        (99, "MI_TEMPERATURE", [20, 21], 0), (99, "MI_NET_RATE", [50], 0),
        (99, "MI_NET_V", [230, 231], 0)]), [99])
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), True, MagicMock())
    try:
        await poller._async_details([HMS], "2026-11-11")
        assert poller.details_status == "readable"
        assert poller.detail_is_fresh(99, "frequency")
        freezer.move_to("2026-11-11 10:11:00+00:00")
        await poller._async_details([HMS], "2026-11-11")
        assert not poller.detail_is_fresh(99, "frequency")
        assert poller.detail_is_fresh(99, "temperature")
        api.async_micro_details.return_value = decode_micro_details(chart(labels=("12:00", "12:05")), [99])
        await poller._async_details([HMS], "2026-11-11")
        assert poller.details[99]["temperature"] == 21
        assert poller.detail_field_updated[(99, "temperature")] == datetime(2026, 11, 11, 10, 5, tzinfo=UTC)
    finally:
        await poller.async_shutdown()


@pytest.mark.parametrize("error", [HoymilesAuthError("auth"), HoymilesRateLimitError("rate", 60)])
async def test_auth_or_rate_failure_never_triggers_chart_fallback(hass, error):
    api = AsyncMock()
    api.async_module_snapshot.side_effect = error
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), True, MagicMock())
    with pytest.raises(type(error)):
        await poller._async_details([HMS], "2026-11-11")
    api.async_micro_details.assert_not_awaited()
    await poller.async_shutdown()


async def test_complete_snapshot_never_requests_fallback(hass, freezer):
    freezer.move_to("2026-11-11 10:06:00+00:00")
    api = AsyncMock()
    api.async_module_snapshot.return_value = {"inverters": {99: {
        "time": "10:05", "frequency": 50, "temperature": 21, "voltage": 230}}}
    poller = ModulePoller(hass, api, 123, ZoneInfo("UTC"), True, MagicMock())
    await poller._async_details([HMS], "2026-11-11")
    api.async_micro_details.assert_not_awaited()
    await poller.async_shutdown()
