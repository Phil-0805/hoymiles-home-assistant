"""Upper SOC uses explicit evidence and preserves fresh settings without retry writes."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.battery import battery_charge_limit_soc, parse_work_mode_settings
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from custom_components.hoymiles_home.number import HoymilesBatteryChargeLimitSocNumber
from custom_components.hoymiles_home.sensor import HoymilesStationSensor, STATION_SENSORS


def settings(lower=12, upper=95, mode=2):
    return parse_work_mode_settings({"code": 0, "data": {
        "mode": mode, "soc_l": lower, "soc_h": upper, "k_3": {"mode": 1},
    }})


@pytest.mark.parametrize("data", [
    {"mode": 2, "soc_l": 12},
    {"mode": 2, "k_2": {"soc_l": 12}},
])
def test_default_upper_bound_is_not_explicit_charge_limit_evidence(data):
    parsed = parse_work_mode_settings({"code": 0, "data": data})
    assert parsed["active_settings"]["soc_h"] == 100  # Preserve the legacy lower-control path.
    assert not parsed["charge_limit_soc_verified"]
    assert battery_charge_limit_soc(parsed) is None


@pytest.mark.parametrize("nested", [False, True])
def test_explicit_upper_bound_is_recognized_in_both_layouts(nested):
    bounds = {"soc_l": 12, "soc_h": 90}
    parsed = parse_work_mode_settings({"code": 0, "data": {
        "mode": 2, **({"k_2": bounds} if nested else bounds),
    }})
    assert battery_charge_limit_soc(parsed) == 90


async def test_upper_change_preserves_lower_limit_from_fresh_app_read(hass):
    api = AsyncMock()
    api.async_battery_settings.side_effect = [settings(25, 95), settings(25, 80)]
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.battery_settings = settings(12, 100)
    await coordinator.async_set_battery_charge_limit_soc(80)
    api.async_write_battery_settings.assert_awaited_once_with(
        123, 1, {"reserve_soc": 25, "soc_l": 25, "soc_h": 80}, request_method="station_action_83",
    )
    assert api.async_battery_settings.await_count == 2
    await coordinator.async_shutdown()


@pytest.mark.parametrize("fresh", [
    settings(95, 100), settings(mode=3),
    {**settings(), "charge_limit_soc_verified": False},
    {**settings(), "request_method": "station"},
    {**settings(), "writable": False},
])
async def test_invalid_or_changed_fresh_capabilities_prevent_any_write(hass, fresh):
    api = AsyncMock()
    api.async_battery_settings.return_value = fresh
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.battery_settings = settings()
    with pytest.raises(HoymilesConnectionError):
        await coordinator.async_set_battery_charge_limit_soc(90)
    api.async_write_battery_settings.assert_not_awaited()
    await coordinator.async_shutdown()


@pytest.mark.parametrize("readback", [
    settings(12, 95), settings(20, 80),
    {**settings(12, 80), "charge_limit_soc_verified": False},
])
async def test_full_readback_must_match_and_failed_confirmation_does_not_repeat_write(hass, readback):
    api = AsyncMock()
    api.async_battery_settings.side_effect = [settings(), readback]
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.battery_settings = settings()
    with patch("custom_components.hoymiles_home.coordinator.BATTERY_WRITE_CONFIRM_ATTEMPTS", 1):
        with pytest.raises(HoymilesConnectionError, match="did not confirm"):
            await coordinator.async_set_battery_charge_limit_soc(80)
    api.async_write_battery_settings.assert_awaited_once()
    await coordinator.async_shutdown()


@pytest.mark.parametrize("enabled", [False, True])
async def test_permission_and_unload_during_preflight_cannot_be_bypassed(hass, enabled):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=enabled)
    coordinator.battery_settings = settings()

    async def fresh_read(station_id):
        await coordinator.async_shutdown()
        return settings()

    api.async_battery_settings.side_effect = fresh_read
    with pytest.raises(HoymilesConnectionError, match="disabled"):
        await coordinator.async_set_battery_charge_limit_soc(80)
    if not enabled:
        api.async_battery_settings.assert_not_awaited()
    api.async_write_battery_settings.assert_not_awaited()
    await coordinator.async_shutdown()


@pytest.mark.parametrize("value", [True, False, 9, 101, 80.5, float("nan"), float("inf"), 10 ** 400, "80"])
async def test_invalid_number_service_values_never_reach_cloud(hass, value):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.battery_settings = settings()
    entity = HoymilesBatteryChargeLimitSocNumber(coordinator, SimpleNamespace(entry_id="entry", data={"station_id": 123}))
    with pytest.raises(HomeAssistantError):
        await entity.async_set_native_value(value)
    api.async_battery_settings.assert_not_awaited()
    api.async_write_battery_settings.assert_not_awaited()
    await coordinator.async_shutdown()


async def test_upper_sensor_is_readable_without_control_permission(hass):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    coordinator.battery_settings = settings(25, 95)
    coordinator.data = {"battery_settings": coordinator.battery_settings}
    entry = SimpleNamespace(entry_id="entry", data={"station_id": 123})
    number = HoymilesBatteryChargeLimitSocNumber(coordinator, entry)
    sensor = HoymilesStationSensor(coordinator, entry, next(d for d in STATION_SENSORS if d.key == "battery_charge_limit_soc"))
    assert number.unique_id == "entry_battery_charge_limit_soc_control"
    assert not number.available
    assert number.native_min_value == 25
    assert sensor.native_value == number.native_value == 95
    coordinator.battery_controls = True
    assert number.available
    coordinator.battery_settings = settings(mode=3)
    assert not number.available
    await coordinator.async_shutdown()


async def test_upper_change_uses_existing_command_83_without_new_endpoints():
    api = HoymilesHomeClient(AsyncMock(), "test@example.com", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(return_value={"status": 0, "data": "synthetic-job"})
    api._async_poll_station_setting_job = AsyncMock(return_value={"code": 0})
    data = {"reserve_soc": 25, "soc_l": 25, "soc_h": 80}
    before = deepcopy(data)
    await api.async_write_battery_settings(123, 1, data, request_method="station_action_83")
    assert api._json.await_args.args[1] == {"action": 83, "data": {"sid": 123, "mode": 2, "soc_l": 25, "soc_h": 80}}
    api._json.assert_awaited_once()
    assert data == before
