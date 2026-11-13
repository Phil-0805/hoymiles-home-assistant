"""Issue #34: read a known app mode independently of command capabilities."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.battery import (
    BatterySettingsError, parse_work_mode_settings, work_mode_command_data, writable_modes,
)
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from custom_components.hoymiles_home.number import HoymilesBatteryReserveSocNumber
from custom_components.hoymiles_home.select import HoymilesBatteryModeSelect
from test_work_mode_tou import snapshot, WEEK


@pytest.mark.parametrize("tou", [None, {}, {"mode": 2},
    {"mode": 2, "k_2": {"id": -1, "week": WEEK}},
    {"mode": 2, "k_2": {"id": "1", "week": WEEK}},
    {"mode": 2, "k_2": {"id": 1, "week": []}},
    {"mode": 3}, {"mode": 4}, {"mode": 5},
])
def test_known_tou_mode_survives_missing_unusable_or_unsupported_plan(tou):
    raw = snapshot(3)
    raw["data"]["k_3"] = tou
    before = deepcopy(raw)
    parsed = parse_work_mode_settings(raw)
    assert parsed["mode"] == 8 and parsed["readable"] is True
    assert parsed["available_modes"] == [1, 8]
    assert writable_modes(parsed) == [1]
    assert parsed["active_settings"] == {}
    assert parsed["reserve_soc_verified"] is False
    assert 8 not in parsed["mode_settings"]
    assert raw == before
    with pytest.raises(BatterySettingsError):
        work_mode_command_data(8, parsed["active_settings"])


@pytest.mark.parametrize("mode", [2, 3])
def test_conflicting_soc_never_hides_mode_or_advertises_self_consumption_write(mode):
    raw = snapshot(mode)
    raw["data"].update(soc_l=20, soc_h=90)
    parsed = parse_work_mode_settings(raw)
    assert parsed["mode"] == (1 if mode == 2 else 8)
    assert parsed["readable"] is True
    assert 1 not in writable_modes(parsed)
    assert parsed["reserve_soc_verified"] is False


@pytest.mark.parametrize("code", [False, True, "0", 0.0, 1, 2, None])
def test_readable_mode_still_requires_successful_normalized_command(code):
    raw = snapshot(3)
    raw["code"] = code
    with pytest.raises(BatterySettingsError):
        parse_work_mode_settings(raw)


async def test_known_mode_without_any_safe_target_remains_read_only():
    parsed = parse_work_mode_settings({"code": 0, "data": {"mode": 3, "k_3": {"mode": 2}}})
    assert parsed["readable"] is True and parsed["mode"] == 8
    assert parsed["writable"] is False and writable_modes(parsed) == []


async def test_incomplete_tou_does_not_fall_back_to_legacy_mode(caplog):
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(return_value={"status": 0, "data": "synthetic-job"})
    raw = snapshot(3, {"mode": 2})
    api._async_poll_station_setting_job = AsyncMock(return_value=raw)
    api._async_battery_settings_request = AsyncMock()
    result = await api.async_battery_settings(123)
    assert result["mode"] == 8 and result["request_method"] == "station_action_83"
    api._json.assert_awaited_once()
    api._async_battery_settings_request.assert_not_awaited()
    assert caplog.text == ""


async def test_select_displays_tou_and_only_allows_verified_target(hass):
    api = AsyncMock()
    current = parse_work_mode_settings(snapshot(3, {"mode": 2}))
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.battery_settings = current
    entry = SimpleNamespace(entry_id="entry", data={"station_id": 123})
    select = HoymilesBatteryModeSelect(coordinator, entry)
    reserve = HoymilesBatteryReserveSocNumber(coordinator, entry)
    assert select.available and select.current_option == "Time of Use"
    assert select.options == ["Self-Consumption", "Time of Use"]
    assert select.extra_state_attributes["mode_change_available"] is True
    assert reserve.available is False
    assert select.unique_id == "entry_battery_mode_control"
    with pytest.raises(HoymilesConnectionError, match="not supported"):
        await coordinator.async_set_battery_mode(8)
    api.async_write_battery_settings.assert_not_awaited()
    fresh = parse_work_mode_settings(snapshot(3, {"mode": 2}))
    fresh["mode_settings"][1].update(reserve_soc=25, soc_l=25)
    confirmed = parse_work_mode_settings(snapshot(2, {"mode": 2}))
    confirmed["active_settings"].update(reserve_soc=25, soc_l=25)
    api.async_battery_settings.side_effect = [fresh, confirmed]
    await coordinator.async_set_battery_mode(1)
    assert api.async_write_battery_settings.await_args.args[1:3] == (
        1, {"reserve_soc": 25, "soc_l": 25, "soc_h": 95})
    api.async_write_battery_settings.assert_awaited_once()
    await coordinator.async_shutdown()


async def test_fresh_read_losing_safe_soc_target_blocks_switch(hass):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.battery_settings = parse_work_mode_settings(snapshot(3, {"mode": 2}))
    api.async_battery_settings.return_value = parse_work_mode_settings({"code": 0, "data": {
        "mode": 3, "k_3": {"mode": 2},
    }})
    with pytest.raises(HoymilesConnectionError):
        await coordinator.async_set_battery_mode(1)
    api.async_write_battery_settings.assert_not_awaited()
    await coordinator.async_shutdown()
