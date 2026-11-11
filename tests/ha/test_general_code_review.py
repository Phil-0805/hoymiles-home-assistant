"""Cross-cutting review: strict service inputs, unload guards and legacy safety."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.battery import parse_battery_settings, BatterySettingsError, battery_setting_targets
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesConnectionError, HoymilesAuthError, HoymilesRateLimitError
from custom_components.hoymiles_home.number import HoymilesBatteryReserveSocNumber


@pytest.mark.parametrize("value", [True, False, None, "50", 9, 101, 49.5, float("nan"), float("inf"), -float("inf"), 10**400])
async def test_invalid_reserve_service_values_are_not_rounded_or_forwarded(hass, value):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123, battery_controls=True)
    coordinator.async_set_battery_reserve_soc = AsyncMock()
    entry = SimpleNamespace(entry_id="entry", data={"station_id": 123})
    try:
        with pytest.raises(HomeAssistantError):
            await HoymilesBatteryReserveSocNumber(coordinator, entry).async_set_native_value(value)
        coordinator.async_set_battery_reserve_soc.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("value", [10, 50.0, 100])
async def test_valid_whole_reserve_percentages_remain_supported(hass, value):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123, battery_controls=True)
    coordinator.async_set_battery_reserve_soc = AsyncMock()
    entry = SimpleNamespace(entry_id="entry", data={"station_id": 123})
    try:
        await HoymilesBatteryReserveSocNumber(coordinator, entry).async_set_native_value(value)
        coordinator.async_set_battery_reserve_soc.assert_awaited_once_with(int(value))
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("change", ["unload", "permission"])
async def test_mode_confirmation_stops_before_another_request_after_controls_are_removed(hass, change):
    active = {"reserve_soc": 10, "soc_l": 10, "soc_h": 100}
    snapshot = {"mode": 1, "readable": True, "writable": True, "request_method": "station_action_83",
                "reserve_soc_verified": True, "active_settings": active}
    api = AsyncMock()
    api.async_battery_settings.return_value = deepcopy(snapshot)
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.battery_settings = deepcopy(snapshot)

    async def write(*args, **kwargs):
        if change == "unload":
            await coordinator.async_shutdown()
        else:
            coordinator.battery_controls = False

    api.async_write_battery_settings.side_effect = write
    try:
        with pytest.raises(HoymilesConnectionError):
            await coordinator.async_set_battery_reserve_soc(20)
        assert api.async_battery_settings.await_count == 1  # Preflight only.
        api.async_write_battery_settings.assert_awaited_once()
    finally:
        await coordinator.async_shutdown()


async def test_legacy_battery_fallback_does_not_choose_one_of_multiple_controllers():
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._async_work_mode_settings = AsyncMock(side_effect=HoymilesConnectionError("unsupported"))
    api._async_battery_settings_request = AsyncMock(side_effect=HoymilesConnectionError("device list is empty"))
    api.async_device_tree = AsyncMock(return_value=[
        {"type": 12, "sn": "ABCDEF000001", "dtu_sn": "ABCDEF000003"},
        {"type": 12, "sn": "ABCDEF000002", "dtu_sn": "ABCDEF000003"}])
    with pytest.raises(HoymilesConnectionError, match="ambiguous"):
        await api.async_battery_settings(123)
    assert api._async_battery_settings_request.await_count == 1  # Station read only.


@pytest.mark.parametrize("kind", [12.0, "12", True])
def test_legacy_device_type_must_be_an_integer(kind):
    assert battery_setting_targets([{"type": kind, "sn": "ABCDEF000001", "dtu_sn": "ABCDEF000002"}]) == []


@pytest.mark.parametrize("identity", [True, False, None, {}, "", "x" * 257])
async def test_invalid_work_mode_job_identity_never_causes_status_polling(identity):
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api._json = AsyncMock(return_value={"status": 0, "data": identity})
    api._async_poll_station_setting_job = AsyncMock()
    with pytest.raises(HoymilesConnectionError):
        await api._async_work_mode_settings(123)
    api._async_poll_station_setting_job.assert_not_awaited()


@pytest.mark.parametrize("identity", [True, False])
async def test_boolean_legacy_job_id_is_not_polled(identity):
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api._json = AsyncMock(return_value={"status": 0, "data": identity})
    api._async_poll_battery_settings_job = AsyncMock()
    with pytest.raises(HoymilesConnectionError):
        await api._async_battery_settings_request({"action": 1013, "data": {"sid": 123}}, "station")
    api._async_poll_battery_settings_job.assert_not_awaited()


@pytest.mark.parametrize("code", [False, True, 0.0, "0"])
def test_legacy_command_success_does_not_accept_boolean_or_coerced_status(code):
    with pytest.raises(BatterySettingsError):
        parse_battery_settings({"code": code, "data": {"mode": 1, "data": {"k_1": {}}}})


@pytest.mark.parametrize("error", [HoymilesAuthError("authentication"), HoymilesRateLimitError("rate", 600)])
async def test_legacy_verification_does_not_probe_after_auth_or_rate_errors(error):
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api._json = AsyncMock(side_effect=error)
    with pytest.raises(type(error)):
        await api._async_verify_battery_settings(123, {})
    assert api._json.await_count == 1


async def test_rate_failure_does_not_fall_back_from_work_mode_to_legacy_settings():
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._async_work_mode_settings = AsyncMock(side_effect=HoymilesRateLimitError("rate", 600))
    api._async_battery_settings_request = AsyncMock()
    with pytest.raises(HoymilesRateLimitError):
        await api.async_battery_settings(123)
    api._async_battery_settings_request.assert_not_awaited()


async def test_device_fallback_retains_rate_error_and_server_delay():
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._async_work_mode_settings = AsyncMock(side_effect=HoymilesConnectionError("unsupported"))
    api._async_battery_settings_request = AsyncMock(side_effect=[
        HoymilesConnectionError("device list is empty"), HoymilesRateLimitError("rate", 600)])
    api.async_device_tree = AsyncMock(return_value=[{"type": 12, "sn": "ABCDEF000001", "dtu_sn": "ABCDEF000002"}])
    with pytest.raises(HoymilesRateLimitError) as caught:
        await api.async_battery_settings(123)
    assert caught.value.retry_after == 600
    assert api._async_battery_settings_request.await_count == 2
