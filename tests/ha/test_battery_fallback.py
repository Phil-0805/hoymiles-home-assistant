"""Battery fallback survives the lifetime of Python exception variables."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.hoymiles_home.api import (
    HoymilesAuthError,
    HoymilesConnectionError,
    HoymilesHomeClient,
)
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator


def fallback_client():
    api = HoymilesHomeClient(MagicMock(), "test@example.com", "password")
    api.async_ensure_login = AsyncMock()
    api._async_work_mode_settings = AsyncMock(
        side_effect=HoymilesConnectionError("command 83 unsupported")
    )
    api._async_verify_battery_settings = AsyncMock(
        side_effect=lambda station_id, settings: settings
    )
    api.async_device_tree = AsyncMock(return_value=[{
        "type": 12, "sn": "TEST-BATTERY", "dtu_sn": "TEST-DTU",
    }])
    return api


async def test_station_fallback_returns_settings_after_work_mode_error():
    api = fallback_client()
    api._async_battery_settings_request = AsyncMock(return_value={"readable": True})
    result = await api.async_battery_settings(123)
    assert result["readable"] is True
    assert result["work_mode_request_error"] == "command 83 unsupported"
    api.async_device_tree.assert_not_awaited()


async def test_device_fallback_returns_settings_after_station_error():
    api = fallback_client()
    api._async_battery_settings_request = AsyncMock(side_effect=[
        HoymilesConnectionError("device list is empty"), {"readable": True},
    ])
    result = await api.async_battery_settings(123)
    assert result["readable"] is True
    assert result["work_mode_request_error"] == "command 83 unsupported"
    assert api._async_battery_settings_request.await_args.args[1] == "device"


@pytest.mark.parametrize("has_target", [True, False])
async def test_exhausted_fallback_raises_connection_error_with_station_cause(has_target):
    api = fallback_client()
    station_error = HoymilesConnectionError("device list is empty")
    api._async_battery_settings_request = AsyncMock(side_effect=[
        station_error, HoymilesConnectionError("device unavailable"),
    ])
    if not has_target:
        api.async_device_tree.return_value = []
    with pytest.raises(HoymilesConnectionError, match="command 83 unsupported") as caught:
        await api.async_battery_settings(123)
    assert caught.value.__cause__ is station_error


async def test_work_mode_success_needs_no_fallback():
    api = fallback_client()
    api._async_work_mode_settings = AsyncMock(return_value={"readable": True})
    api._async_battery_settings_request = AsyncMock()
    assert await api.async_battery_settings(123) == {"readable": True}
    api._async_battery_settings_request.assert_not_awaited()


async def test_auth_failure_is_not_treated_as_unsupported_work_mode():
    api = fallback_client()
    api._async_work_mode_settings.side_effect = HoymilesAuthError("login required")
    api._async_battery_settings_request = AsyncMock()
    with pytest.raises(HoymilesAuthError):
        await api.async_battery_settings(123)
    api._async_battery_settings_request.assert_not_awaited()


async def test_exhausted_fallback_is_handled_by_background_refresh(hass):
    api = fallback_client()
    api.async_device_tree.return_value = []
    api._async_battery_settings_request = AsyncMock(
        side_effect=HoymilesConnectionError("device list is empty")
    )
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    await coordinator._async_refresh_battery_settings()
    assert coordinator.battery_settings["readable"] is False
    assert "command 83 unsupported" in coordinator.battery_settings["error"]
