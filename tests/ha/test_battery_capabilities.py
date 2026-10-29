"""Unsupported capabilities are not presented as working device controls."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.hoymiles_home.battery import battery_settings_confirmed, soc_setting_candidates
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.select import HoymilesBatteryModeSelect
from custom_components.hoymiles_home.sensor import HoymilesStationSensor, STATION_SENSORS
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from custom_components.hoymiles_home.telemetry import pv_power_details


async def test_single_verified_mode_is_readable_without_a_fake_choice(hass):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    coordinator.battery_settings = {"mode": 1, "available_modes": [1], "readable": True, "writable": True}
    entry = SimpleNamespace(entry_id="entry", data={"station_id": 123})
    entity = HoymilesBatteryModeSelect(coordinator, entry)
    assert entity.current_option == "Self-Consumption"
    assert entity.available
    assert entity.options == ["Self-Consumption"]
    assert entity.extra_state_attributes["mode_change_available"] is False
    coordinator.async_set_battery_mode = AsyncMock()
    await entity.async_select_option("Self-Consumption")
    coordinator.async_set_battery_mode.assert_not_awaited()
    coordinator.battery_settings["available_modes"] = [1, 2]
    assert entity.available


async def test_hidden_active_mode_does_not_become_a_writable_choice(hass):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.battery_settings = {"mode": 5, "available_modes": [1, 5, True], "readable": True,
                                    "writable": True, "mode_settings": {1: {}, 5: {}}}
    entity = HoymilesBatteryModeSelect(coordinator, SimpleNamespace(entry_id="entry", data={"station_id": 123}))
    assert "Self-Consumption + Max Power" not in entity.options
    assert not entity.available
    with pytest.raises(HoymilesConnectionError):
        await coordinator.async_set_battery_mode(5)
    api.async_write_battery_settings.assert_not_awaited()


async def test_missing_max_power_is_unavailable_and_has_no_invented_unit(hass):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    coordinator.data = {"battery_settings": {"active_settings": {}}, "live": {"power": None}}
    description = next(d for d in STATION_SENSORS if d.key == "battery_max_power")
    entity = HoymilesStationSensor(coordinator, SimpleNamespace(entry_id="entry", data={"station_id": 123}), description)
    assert not entity.available
    assert entity.native_unit_of_measurement is None
    assert entity.extra_state_attributes["unit_verified"] is False
    assert pv_power_details(coordinator.data)["value"] is None


def test_nested_setting_changes_must_be_confirmed_too():
    settings = {"mode": 8, "active_settings": {"schedule": [1, 2]}}
    assert not battery_settings_confirmed(settings, 8, {"schedule": [1, 3]})
    assert battery_settings_confirmed(settings, 8, {"schedule": [1, 2]})


def test_soc_probe_does_not_export_arbitrary_strings():
    assert soc_setting_candidates({"minimum_soc": 10, "soc_account": "PRIVATE", "soc_flag": True}) == [{"path": "minimum_soc", "value": 10}]


@pytest.mark.parametrize("actual,expected", [(True, 1), (False, 0), ({"flag": True}, {"flag": 1}), ([True], [1])])
def test_readback_does_not_confuse_flags_with_numbers(actual, expected):
    assert not battery_settings_confirmed({"mode": 1, "active_settings": {"value": actual}}, 1, {"value": expected})


@pytest.mark.parametrize("invalid", [{"readable": False}, {"request_method": "station_action_1013"}, {"reserve_soc_verified": False}, {"mode": True}, {"active_settings": {"reserve_soc": 21, "soc_l": 21, "soc_h": 100}}])
async def test_unverified_readback_never_reports_write_success(hass, invalid):
    api = AsyncMock()
    active = {"reserve_soc": 20, "soc_l": 20, "soc_h": 100}
    snapshot = {"mode": 1, "readable": True, "writable": True, "request_method": "station_action_83", "reserve_soc_verified": True, "active_settings": active}
    api.async_battery_settings.return_value = {**snapshot, **invalid}
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.battery_settings = snapshot
    from unittest.mock import patch
    with patch("custom_components.hoymiles_home.coordinator.BATTERY_WRITE_CONFIRM_ATTEMPTS", 1):
        with pytest.raises(HoymilesConnectionError, match="did not confirm"):
            await coordinator.async_set_battery_reserve_soc(20)
    # A failed confirmation must not cause a repeated device write.
    api.async_write_battery_settings.assert_awaited_once()
    await coordinator.async_shutdown()
