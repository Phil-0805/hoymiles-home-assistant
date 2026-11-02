"""Action-83 TOU is distinct from the action-1013 BMS enum."""

from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.battery import (
    BatterySettingsError, parse_work_mode_settings, work_mode_command_data,
)
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesConnectionError

WEEK = [{"week": [1, 2, 3, 4, 5, 6, 7], "dcs": [
    {"type": 4, "start_time": "06:00", "end_time": "23:00", "power_l": 300, "soc_l": 12}
]}]


def snapshot(app_mode=2, tou=None, flat=False):
    data = {"mode": app_mode, "k_3": deepcopy(tou or {"mode": 1})}
    if flat:
        data.update(soc_l=12, soc_h=95)
    else:
        data["k_2"] = {"soc_l": 12, "soc_h": 95}
    return {"code": 0, "data": data}


@pytest.mark.parametrize("flat", [False, True])
@pytest.mark.parametrize("app_mode", [2, 3])
@pytest.mark.parametrize("tou,command", [
    ({"mode": 1}, {"mode": 1}),
    ({"mode": 2, "k_2": {"id": 123, "week": WEEK}}, {"mode": 2, "data": {"id": 123, "week": WEEK}}),
    ({"mode": 3, "k_3": {"id": 456}}, {"mode": 3, "id": 456}),
])
def test_parse_both_layouts_and_reuse_existing_tou_selection(flat, app_mode, tou, command):
    raw = snapshot(app_mode, tou, flat)
    before = deepcopy(raw)
    parsed = parse_work_mode_settings(raw)
    assert parsed["mode"] == (1 if app_mode == 2 else 8)
    assert parsed["available_modes"] == [1, 8]
    assert parsed["reserve_soc_verified"] is (app_mode == 2)
    assert work_mode_command_data(8, parsed["mode_settings"][8]) == {"mode": 3, "data": command}
    assert work_mode_command_data(1, parsed["mode_settings"][1]) == {"mode": 2, "soc_l": 12, "soc_h": 95}
    assert raw == before


@pytest.mark.parametrize("tou", [None, {}, {"mode": True}, {"mode": 4}, {"mode": 5}, {"mode": 2},
    {"mode": 2, "k_2": {"id": -1, "week": WEEK}},
    {"mode": 2, "k_2": {"id": 123, "week": []}},
    {"mode": 3, "k_3": {"id": False}},
])
def test_incomplete_or_unverified_tou_is_not_offered(tou):
    raw = snapshot()
    raw["data"]["k_3"] = tou
    assert parse_work_mode_settings(raw)["available_modes"] == [1]
    raw["data"]["mode"] = 3
    with pytest.raises(BatterySettingsError):
        parse_work_mode_settings(raw)


async def test_api_uses_station_83_payload_without_schedule_mutation():
    api = HoymilesHomeClient(MagicMock(), "test@example.com", "secret")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(return_value={"status": "0", "data": "job"})
    api._async_poll_station_setting_job = AsyncMock(return_value={"code": 0})
    settings = parse_work_mode_settings(snapshot(tou={"mode": 2, "k_2": {"id": 123, "week": WEEK}}))
    await api.async_write_battery_settings(123, 8, settings["mode_settings"][8], request_method="station_action_83")
    url, payload = api._json.await_args.args
    assert url.startswith("https://neapi.hoymiles.com/")
    assert payload == {"action": 83, "data": {"sid": 123, "mode": 3, "data": {"mode": 2, "data": {"id": 123, "week": WEEK}}}}


async def test_switch_uses_fresh_app_plan_and_confirms_readback(hass):
    api = AsyncMock()
    old = parse_work_mode_settings(snapshot(tou={"mode": 3, "k_3": {"id": 111}}))
    fresh = parse_work_mode_settings(snapshot(tou={"mode": 3, "k_3": {"id": 222}}))
    confirmed = parse_work_mode_settings(snapshot(3, {"mode": 3, "k_3": {"id": 222}}))
    api.async_battery_settings.side_effect = [fresh, confirmed]
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.battery_settings = old
    await coordinator.async_set_battery_mode(8)
    assert api.async_write_battery_settings.await_args.args[2] == {"tou_settings": {"mode": 3, "id": 222}}
    assert coordinator.battery_settings["mode"] == 8
    assert api.async_battery_settings.await_count == 2
    await coordinator.async_shutdown()


async def test_switch_to_self_consumption_preserves_stored_soc(hass):
    api = AsyncMock()
    current = parse_work_mode_settings(snapshot(3))
    api.async_battery_settings.side_effect = [current, parse_work_mode_settings(snapshot())]
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.battery_settings = current
    await coordinator.async_set_battery_mode(1)
    assert api.async_write_battery_settings.await_args.args[2] == {"reserve_soc": 12, "soc_l": 12, "soc_h": 95}
    await coordinator.async_shutdown()


async def test_changed_or_unconfirmed_plan_is_not_success(hass):
    api = AsyncMock()
    current = parse_work_mode_settings(snapshot(tou={"mode": 3, "k_3": {"id": 222}}))
    wrong = parse_work_mode_settings(snapshot(3, {"mode": 3, "k_3": {"id": 333}}))
    api.async_battery_settings.side_effect = [current, wrong]
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.battery_settings = current
    with patch("custom_components.hoymiles_home.coordinator.BATTERY_WRITE_CONFIRM_ATTEMPTS", 1):
        with pytest.raises(HoymilesConnectionError, match="did not confirm"):
            await coordinator.async_set_battery_mode(8)
    api.async_write_battery_settings.assert_awaited_once()
    await coordinator.async_shutdown()


async def test_removed_tou_capability_does_not_send_a_write(hass):
    api = AsyncMock()
    current = parse_work_mode_settings(snapshot())
    fresh = deepcopy(current)
    fresh["available_modes"] = [1]
    api.async_battery_settings.return_value = fresh
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.battery_settings = current
    with pytest.raises(HoymilesConnectionError, match="not supported"):
        await coordinator.async_set_battery_mode(8)
    api.async_write_battery_settings.assert_not_awaited()
    await coordinator.async_shutdown()
