"""Android action 1537 is independent of action-83 work-mode SOC."""

import asyncio
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.device_settings import light_target, parse_cutoffs
from custom_components.hoymiles_home.diagnostics import _cutoff_diagnostics
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from custom_components.hoymiles_home.number import HoymilesBatteryCutoffNumber, async_setup_entry

TARGET = {"dev_sn": "ABCDEF000001", "dtu_sn": "ABCDEF000002"}
TREE = [{"type": 12, "sn": TARGET["dev_sn"], "dtu_sn": TARGET["dtu_sn"]}]
ENTRY = SimpleNamespace(entry_id="entry", data={"station_id": 123})


@pytest.fixture
async def cutoffs(hass):
    api = AsyncMock()
    api.async_cutoff_settings.return_value = {"sl": 12, "sh": 100}
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.device_tree = deepcopy(TREE)
    manager = coordinator.cutoff_settings
    await manager._async_refresh()
    api.reset_mock()
    with patch("custom_components.hoymiles_home.device_settings.READBACK_ATTEMPTS", 1):
        yield coordinator, api, manager
    await coordinator.async_shutdown()


@pytest.mark.parametrize("data", [{}, {"sl": 10}, {"sh": 100}, {"sl": True, "sh": 100},
    {"sl": 9, "sh": 100}, {"sl": 71, "sh": 100}, {"sl": 10, "sh": 49},
    {"sl": 10, "sh": 101}, {"sl": 50, "sh": 50}, {"sl": 50, "sh": 59},
    {"sl": "10", "sh": 100}, {"sl": 10, "sh": 90.0}])
def test_missing_defaults_and_out_of_app_range_never_enable_control(data):
    with pytest.raises(HoymilesConnectionError):
        parse_cutoffs(data)


def test_mobile_missing_dtu_is_empty_and_never_inherits_web_fallback():
    tree = [{"type": 12, "sn": TARGET["dev_sn"]}]
    assert light_target(tree, mobile_addressing=True) == {"dev_sn": TARGET["dev_sn"], "dtu_sn": ""}
    assert light_target(tree)["dtu_sn"] == TARGET["dev_sn"]


async def test_mobile_empty_dtu_is_transmitted_as_empty():
    api = HoymilesHomeClient(AsyncMock(), "test@example.com", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(return_value={"status": 0, "data": "job"})
    api._async_poll_station_setting_job = AsyncMock(return_value={"code": 0, "data": {"sl": 20, "sh": 90}})
    await api.async_cutoff_settings({"dev_sn": TARGET["dev_sn"], "dtu_sn": ""})
    assert api._json.await_args.args[1]["dtu_sn"] == ""


@pytest.mark.parametrize("field,value,fresh,expected", [
    ("sh", 80, {"sl": 25, "sh": 95}, {"sl": 25, "sh": 80}),
    ("sl", 30, {"sl": 12, "sh": 90}, {"sl": 30, "sh": 90}),
])
async def test_either_cutoff_preserves_other_fresh_app_threshold(cutoffs, field, value, fresh, expected):
    _, api, manager = cutoffs
    api.async_cutoff_settings.side_effect = [fresh, expected]
    await manager.async_set_cutoff(field, value)
    api.async_write_cutoff_settings.assert_awaited_once_with(TARGET, expected)
    api.async_write_battery_settings.assert_not_awaited()
    api.async_battery_settings.assert_not_awaited()
    assert manager.cutoffs == expected


async def test_changed_fresh_lower_limit_prevents_conflicting_upper(cutoffs):
    _, api, manager = cutoffs
    api.async_cutoff_settings.return_value = {"sl": 70, "sh": 100}
    with pytest.raises(HoymilesConnectionError):
        await manager.async_set_cutoff("sh", 75)
    api.async_write_cutoff_settings.assert_not_awaited()


@pytest.mark.parametrize("actual", [{"sl": 12, "sh": 100}, {"sl": 20, "sh": 80}])
async def test_readback_must_confirm_both_and_never_repeats_write(cutoffs, actual):
    _, api, manager = cutoffs
    api.async_cutoff_settings.side_effect = [{"sl": 12, "sh": 100}, actual]
    with pytest.raises(HoymilesConnectionError, match="did not confirm"):
        await manager.async_set_cutoff("sh", 80)
    api.async_write_cutoff_settings.assert_awaited_once()
    assert not manager.available("cutoffs")


@pytest.mark.parametrize("change", ["permission", "unload", "target"])
async def test_permission_unload_and_changed_controller_block_preflight(cutoffs, change):
    coordinator, api, manager = cutoffs

    async def fresh(target):
        if change == "permission":
            coordinator.battery_controls = False
        elif change == "unload":
            await coordinator.async_shutdown()
        else:
            coordinator.device_tree = []
        return {"sl": 12, "sh": 100}

    api.async_cutoff_settings.side_effect = fresh
    with pytest.raises(HoymilesConnectionError):
        await manager.async_set_cutoff("sl", 20)
    api.async_write_cutoff_settings.assert_not_awaited()


async def test_ambiguous_batteries_make_no_cutoff_request(cutoffs):
    coordinator, api, manager = cutoffs
    coordinator.device_tree.append({"type": 12, "sn": "ABCDEF000003"})
    await manager._async_refresh()
    assert manager.status["cutoffs"] == "no_unique_target"
    api.async_cutoff_settings.assert_not_awaited()


async def test_simultaneous_changes_serialize_fresh_pairs(cutoffs):
    _, api, manager = cutoffs
    state = {"sl": 12, "sh": 100}

    async def read(*args):
        await asyncio.sleep(0)
        return dict(state)

    async def write(target, values):
        state.update(values)

    api.async_cutoff_settings.side_effect = read
    api.async_write_cutoff_settings.side_effect = write
    await asyncio.gather(manager.async_set_cutoff("sl", 20), manager.async_set_cutoff("sh", 90))
    assert state == {"sl": 20, "sh": 90}


async def test_cutoff_permission_cannot_enable_heating_or_lighting(cutoffs):
    _, api, manager = cutoffs
    with pytest.raises(HoymilesConnectionError, match="disabled"):
        await manager.async_set_heating(True)
    api.async_heating_settings.assert_not_awaited()
    api.async_write_heating_settings.assert_not_awaited()


@pytest.mark.parametrize("value", [True, -1, 101, "80", 80.5, float("inf"), float("nan")])
async def test_invalid_entity_values_never_reach_cloud(cutoffs, value):
    coordinator, api, _ = cutoffs
    entity = HoymilesBatteryCutoffNumber(coordinator, ENTRY, "sh")
    with pytest.raises(HomeAssistantError):
        await entity.async_set_native_value(value)
    api.async_cutoff_settings.assert_not_awaited()


async def test_entities_have_separate_ids_limits_permission_and_safe_diagnostics(cutoffs, hass):
    coordinator, _, manager = cutoffs
    hass.data.setdefault("hoymiles_home", {})[ENTRY.entry_id] = coordinator
    entities = []
    await async_setup_entry(hass, ENTRY, entities.extend)
    lower, upper = [e for e in entities if isinstance(e, HoymilesBatteryCutoffNumber)]
    assert lower.unique_id == "entry_device_setting_battery_discharge_cutoff"
    assert upper.unique_id == "entry_device_setting_battery_charge_cutoff"
    assert lower.native_value == 12 and upper.native_value == 100
    assert lower.native_min_value == 10 and lower.native_max_value == 70
    assert upper.native_min_value == 50 and upper.native_max_value == 100
    assert lower.available and upper.available  # No heating/display permission needed.
    assert upper.extra_state_attributes is None
    diag = _cutoff_diagnostics(manager)
    assert diag["charge_cutoff_soc"] == 100
    assert diag["discharge_cutoff_soc"] == 12
    assert TARGET["dev_sn"] not in json.dumps(diag)
    coordinator.battery_controls = False
    assert not upper.available


@pytest.mark.parametrize("write", [False, True])
async def test_exact_mobile_station_transport_with_device_addressing(write):
    api = HoymilesHomeClient(AsyncMock(), "test@example.com", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(return_value={"status": 0, "data": "job"})
    api._async_poll_station_setting_job = AsyncMock(return_value={"code": 0, "data": json.dumps({"sl": 20, "sh": 90})})
    if write:
        await api.async_write_cutoff_settings(TARGET, {"sl": 20, "sh": 90})
    else:
        assert await api.async_cutoff_settings(TARGET) == {"sl": 20, "sh": 90}
    url, payload = api._json.await_args.args
    assert url.endswith("/station_ctl/" + ("write_c" if write else "read_c"))
    assert payload == {"action": 1537, **TARGET, "data": {"sl": 20, "sh": 90} if write else {}}
    assert "sid" not in payload["data"]
    api._async_poll_station_setting_job.assert_awaited_once_with("job")


@pytest.mark.parametrize("code", [True, 1, 2, None])
async def test_failed_or_invalid_command_status_is_not_a_confirmed_cutoff(code):
    api = HoymilesHomeClient(AsyncMock(), "test@example.com", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(return_value={"status": 0, "data": "job"})
    api._async_poll_station_setting_job = AsyncMock(return_value={"code": code})
    with pytest.raises(HoymilesConnectionError):
        await api.async_cutoff_settings(TARGET)
