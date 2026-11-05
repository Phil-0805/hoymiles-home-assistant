"""Output power uses explicit phase layout/limits and full fresh readback."""

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.diagnostics import _output_power_diagnostics
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from custom_components.hoymiles_home.number import HoymilesOutputPowerNumber
from custom_components.hoymiles_home.output_power import output_phases, output_write_data, parse_output_settings

TREE = [{"type": 12, "sn": "ABCDEF000001", "dtu_sn": "ABCDEF000002"}]
ENTRY = SimpleNamespace(entry_id="entry", data={"station_id": 123})
SINGLE = {"power": 600, "max_power": 2000}
MULTI = {"out_power_total": 1200, "max_power": 4000, "out_power_a": 600,
         "out_power_b": 700, "power_a": 2000, "power_b": 2000}


@pytest.fixture
async def output(hass):
    api = AsyncMock()
    api.async_output_power_settings.return_value = parse_output_settings(SINGLE, [])
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.device_tree = deepcopy(TREE)
    manager = coordinator.output_settings
    await manager._async_refresh()
    api.reset_mock()
    with patch("custom_components.hoymiles_home.device_settings.READBACK_ATTEMPTS", 1):
        yield coordinator, api, manager
    await coordinator.async_shutdown()


@pytest.mark.parametrize("phases", [None, {}, "A", ["D"], ["A", "A"], [True], ["A", "B", "C", "D"], " " * 129, '[[]]', 'null'])
def test_invalid_or_missing_phase_evidence_is_not_single_phase(phases):
    with pytest.raises(HoymilesConnectionError):
        output_phases(phases)


@pytest.mark.parametrize("data", [{}, {"power": 600}, {"max_power": 2000},
    {"power": True, "max_power": 2000}, {"power": 99, "max_power": 2000},
    {"power": 2100, "max_power": 2000}, {"power": 600, "max_power": "2000"},
    {"power": 600, "max_power": 2**31}, {"power": 600.0, "max_power": 2000}])
def test_explicit_valid_values_and_maximum_are_required(data):
    with pytest.raises(HoymilesConnectionError):
        parse_output_settings(data, [])


def test_phase_write_preserves_each_active_phase_and_sets_output_type():
    settings = parse_output_settings(MULTI, ["B", "A"])
    assert settings["phases"] == ["A", "B"]
    assert output_write_data(settings, 1500) == {"type": 0, "power_total": 1500, "power_a": 600, "power_b": 700}
    assert settings["values"]["total"] == 1200
    with pytest.raises(HoymilesConnectionError):
        parse_output_settings({k: v for k, v in MULTI.items() if k != "power_a"}, ["A", "B"])


async def test_single_write_uses_fresh_lower_maximum(output):
    _, api, manager = output
    fresh = parse_output_settings({"power": 600, "max_power": 800}, [])
    actual = parse_output_settings({"power": 700, "max_power": 800}, [])
    api.async_output_power_settings.side_effect = [fresh, actual]
    await manager.async_set_power(700)
    api.async_write_output_power_settings.assert_awaited_once_with(123, fresh, 700)
    assert manager.output == actual
    api.async_write_cutoff_settings.assert_not_awaited()


async def test_value_above_fresh_limit_never_writes(output):
    _, api, manager = output
    api.async_output_power_settings.return_value = parse_output_settings({"power": 600, "max_power": 800}, [])
    with pytest.raises(HoymilesConnectionError):
        await manager.async_set_power(900)
    api.async_write_output_power_settings.assert_not_awaited()


async def test_phase_write_uses_fresh_counterpart_values(output):
    _, api, manager = output
    manager._store("output_power", parse_output_settings(MULTI, ["A", "B"]))
    fresh = parse_output_settings({**MULTI, "out_power_b": 800}, ["A", "B"])
    actual = parse_output_settings({**MULTI, "out_power_total": 1500, "out_power_b": 800}, ["A", "B"])
    api.async_output_power_settings.side_effect = [fresh, actual]
    await manager.async_set_power(1500)
    api.async_write_output_power_settings.assert_awaited_once_with(123, fresh, 1500)


async def test_changed_phase_layout_blocks_a_write(output):
    _, api, manager = output
    api.async_output_power_settings.return_value = parse_output_settings(MULTI, ["A", "B"])
    with pytest.raises(HoymilesConnectionError, match="phase layout changed"):
        await manager.async_set_power(1500)
    api.async_write_output_power_settings.assert_not_awaited()


@pytest.mark.parametrize("change", ["permission", "unload", "target"])
async def test_preflight_guards_output_permission_and_controller(output, change):
    coordinator, api, manager = output

    async def fresh(station):
        if change == "permission":
            coordinator.battery_controls = False
        elif change == "unload":
            await coordinator.async_shutdown()
        else:
            coordinator.device_tree = []
        return parse_output_settings(SINGLE, [])

    api.async_output_power_settings.side_effect = fresh
    with pytest.raises(HoymilesConnectionError):
        await manager.async_set_power(700)
    api.async_write_output_power_settings.assert_not_awaited()


@pytest.mark.parametrize("actual", [SINGLE, {"power": 700, "max_power": 1800}])
async def test_failed_full_readback_never_resends_the_write(output, actual):
    _, api, manager = output
    api.async_output_power_settings.side_effect = [parse_output_settings(SINGLE, []), parse_output_settings(actual, [])]
    with pytest.raises(HoymilesConnectionError, match="did not confirm"):
        await manager.async_set_power(700)
    api.async_write_output_power_settings.assert_awaited_once()
    assert not manager.available("output_power")


@pytest.mark.parametrize("value", [True, 99, 700.5, float("inf"), float("nan"), "700", 10**400])
async def test_invalid_service_values_do_not_contact_cloud(output, value):
    coordinator, api, _ = output
    with pytest.raises(HomeAssistantError):
        await HoymilesOutputPowerNumber(coordinator, ENTRY).async_set_native_value(value)
    api.async_output_power_settings.assert_not_awaited()


async def test_noop_does_not_write_and_entity_has_explicit_range(output):
    coordinator, api, manager = output
    entity = HoymilesOutputPowerNumber(coordinator, ENTRY)
    assert entity.native_value == 600
    assert entity.native_max_value == 2000
    assert entity.native_min_value == 100
    assert entity.native_unit_of_measurement == "W"
    assert entity.available  # Battery permission, independent of display permission.
    assert entity.unique_id == "entry_device_setting_output_power_limit"
    assert entity.extra_state_attributes is None
    await manager.async_set_power(600)
    api.async_write_output_power_settings.assert_not_awaited()
    assert TREE[0]["sn"] not in json.dumps(_output_power_diagnostics(manager))


async def test_disabled_output_settings_do_not_poll_or_write(hass):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    assert coordinator.output_settings.start() is None
    assert await coordinator.output_settings.async_refresh() is False
    with pytest.raises(HoymilesConnectionError):
        await coordinator.output_settings.async_set_power(600)
    api.async_output_power_settings.assert_not_awaited()
    api.async_write_output_power_settings.assert_not_awaited()
    await coordinator.async_shutdown()


async def test_shutdown_cancels_output_read(output):
    coordinator, api, manager = output
    started = asyncio.Event()

    async def read(station):
        started.set()
        await asyncio.Event().wait()

    api.async_output_power_settings.side_effect = read
    task = manager.start()
    await started.wait()
    await coordinator.async_shutdown()
    assert task.cancelled()


@pytest.mark.parametrize("phases,data,action,read_data,write_data,value", [
    ([], SINGLE, 84, {}, {"power": 700}, 700),
    (["A", "B"], MULTI, 1532, {"type": 0}, {"type": 0, "power_total": 1500, "power_a": 600, "power_b": 700}, 1500),
])
async def test_exact_android_transport_for_read_and_write(phases, data, action, read_data, write_data, value):
    api = HoymilesHomeClient(AsyncMock(), "test@example.com", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(side_effect=[{"status": 0, "data": json.dumps(phases)}, {"status": 0, "data": "read-job"}])
    api._async_poll_station_setting_job = AsyncMock(return_value={"code": 0, "data": json.dumps(data)})
    settings = await api.async_output_power_settings(123)
    assert api._json.await_args_list[0].args[0].endswith("/pvmc/api/0/station/phase/type_s_c")
    assert api._json.await_args_list[0].args[1] == {"sid": 123}
    assert api._json.await_args.args[1] == {"action": action, "data": {**read_data, "sid": 123}}
    assert api._json.await_args.args[0].endswith("/station_ctl/read_c")
    api._json = AsyncMock(return_value={"status": 0, "data": "write-job"})
    api._async_poll_station_setting_job.return_value = {"code": 0}
    await api.async_write_output_power_settings(123, settings, value)
    assert api._json.await_args.args[0].endswith("/station_ctl/write_c")
    assert api._json.await_args.args[1] == {"action": action, "data": {**write_data, "sid": 123}}
    api._async_poll_station_setting_job.assert_awaited_with("write-job")


async def test_failed_phase_lookup_is_never_replaced_with_action_84():
    api = HoymilesHomeClient(AsyncMock(), "test@example.com", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(return_value={"status": 1, "message": "synthetic failure"})
    with pytest.raises(HoymilesConnectionError):
        await api.async_output_power_settings(123)
    assert api._json.await_count == 1


@pytest.mark.parametrize("code", [True, 1, None])
async def test_invalid_command_status_cannot_confirm_output(code):
    api = HoymilesHomeClient(AsyncMock(), "test@example.com", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(return_value={"status": 0, "data": "job"})
    api._async_poll_station_setting_job = AsyncMock(return_value={"code": code})
    with pytest.raises(HoymilesConnectionError):
        await api.async_write_output_power_settings(123, parse_output_settings(SINGLE, []), 700)
