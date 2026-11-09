"""Existing custom basic TOU plans use ID zero in the inspected Android app."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from custom_components.hoymiles_home.battery import parse_work_mode_settings, work_mode_command_data, writable_modes
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from test_work_mode_tou import snapshot


def plan(plan_id=0):
    return {"mode": 2, "k_2": {"id": plan_id, "week": [{
        "id": 0, "name": "synthetic plan", "week": [1, 2, 3, 4, 5, 6, 7], "dcs": [
            {"type": 4, "start_time": "00:00", "end_time": "04:00"},
            {"type": 1, "start_time": "04:00", "end_time": "06:00"},
            {"type": 2, "start_time": "06:00", "end_time": "23:59"},
        ],
    }]}}


@pytest.mark.parametrize("plan_id", [0, 1, 123])
def test_saved_basic_plan_is_read_and_reused_without_mutation(plan_id):
    tou = plan(plan_id)
    before = deepcopy(tou)
    parsed = parse_work_mode_settings(snapshot(2, tou))
    assert writable_modes(parsed) == [1, 8]
    command = work_mode_command_data(8, parsed["mode_settings"][8])
    assert command == {"mode": 3, "data": {"mode": 2, "data": tou["k_2"]}}
    assert tou == before
    command["data"]["data"]["week"][0]["dcs"][0]["type"] = 1
    assert tou == before


@pytest.mark.parametrize("plan_id", [-1, -2, True, False, "0", 0.0, None, 2**31])
def test_default_missing_or_ambiguous_ids_never_become_custom_commands(plan_id):
    parsed = parse_work_mode_settings(snapshot(3, plan(plan_id)))
    assert parsed["mode"] == 8 and 8 not in writable_modes(parsed)


@pytest.mark.parametrize("change", [
    "no_days", "bool_day", "duplicate_day", "unknown_day", "duplicate_group", "no_periods",
    "missing_time", "unknown_action", "bool_action", "fraction_action", "bad_clock", "encoded_clock",
    "equal_times", "reverse_times", "overlap", "bad_soc", "bool_power", "nonfinite_extra",
])
def test_invalid_nested_plan_is_readable_but_cannot_be_activated(change):
    tou = plan()
    group = tou["k_2"]["week"][0]
    period = group["dcs"][0]
    if change == "no_days": group["week"] = []
    elif change == "bool_day": group["week"] = [True]
    elif change == "duplicate_day": group["week"] = [1, 1]
    elif change == "unknown_day": group["week"] = [0]
    elif change == "duplicate_group": tou["k_2"]["week"].append(deepcopy(group))
    elif change == "no_periods": group["dcs"] = []
    elif change == "missing_time": period.pop("start_time")
    elif change == "unknown_action": period["type"] = 999
    elif change == "bool_action": period["type"] = True
    elif change == "fraction_action": period["type"] = 1.0
    elif change == "bad_clock": period["start_time"] = "24:00"
    elif change == "encoded_clock": period["start_time"] = "０0:00"
    elif change == "equal_times": period["end_time"] = "00:00"
    elif change == "reverse_times": period["start_time"] = "05:00"
    elif change == "overlap": period["end_time"] = "04:01"
    elif change == "bad_soc": period["soc_l"] = 101
    elif change == "bool_power": period["power_l"] = False
    elif change == "nonfinite_extra": period["unknown"] = float("nan")
    before = deepcopy(tou)
    parsed = parse_work_mode_settings(snapshot(3, tou))
    assert parsed["mode"] == 8 and parsed["readable"] is True
    assert writable_modes(parsed) == [1]
    assert 8 not in parsed["mode_settings"]
    # Compare JSON-independent shape for the intentionally nonfinite test.
    assert tou.keys() == before.keys()


async def test_switch_uses_fresh_zero_id_plan_preserves_all_fields_and_confirms_once(hass):
    api = AsyncMock()
    cached = plan()
    fresh = plan()
    fresh["k_2"]["week"][0]["name"] = "fresh synthetic plan"
    fresh["k_2"]["week"][0]["dcs"][0]["end_time"] = "03:00"
    fresh["k_2"]["week"][0]["dcs"][1]["start_time"] = "03:00"
    fresh["k_2"]["week"][0]["dcs"][0]["preserve_field"] = {"flag": 1}
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.battery_settings = parse_work_mode_settings(snapshot(2, cached))
    api.async_battery_settings.side_effect = [
        parse_work_mode_settings(snapshot(2, fresh)), parse_work_mode_settings(snapshot(3, fresh)),
    ]
    await coordinator.async_set_battery_mode(8)
    sent = api.async_write_battery_settings.await_args
    assert sent.args == (123, 8, {"tou_settings": {"mode": 2, "data": fresh["k_2"]}})
    assert sent.kwargs == {"request_method": "station_action_83"}
    api.async_write_battery_settings.assert_awaited_once()
    assert coordinator.battery_settings["mode"] == 8
    await coordinator.async_shutdown()


async def test_fresh_zero_id_plan_becoming_incomplete_prevents_write(hass):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.battery_settings = parse_work_mode_settings(snapshot(2, plan()))
    incomplete = plan()
    incomplete["k_2"].pop("week")
    api.async_battery_settings.return_value = parse_work_mode_settings(snapshot(2, incomplete))
    with pytest.raises(HoymilesConnectionError, match="not supported"):
        await coordinator.async_set_battery_mode(8)
    api.async_write_battery_settings.assert_not_awaited()
    await coordinator.async_shutdown()


async def test_zero_id_command_uses_existing_station_transport_and_exact_fresh_plan():
    from unittest.mock import MagicMock
    from custom_components.hoymiles_home.api import HoymilesHomeClient
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(return_value={"status": 0, "data": "synthetic-job"})
    api._async_poll_station_setting_job = AsyncMock(return_value={"code": 0})
    tou = plan()
    settings = parse_work_mode_settings(snapshot(2, tou))
    await api.async_write_battery_settings(123, 8, settings["mode_settings"][8], request_method="station_action_83")
    api._json.assert_awaited_once_with(
        "https://neapi.hoymiles.com/pvmc/api/0/station_ctl/write_c",
        {"action": 83, "data": {"sid": 123, "mode": 3, "data": {"mode": 2, "data": tou["k_2"]}}})
    api._async_poll_station_setting_job.assert_awaited_once_with("synthetic-job")
