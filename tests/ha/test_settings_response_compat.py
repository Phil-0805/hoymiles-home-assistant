"""App-compatible response formats and private, actionable failure diagnostics."""

from copy import deepcopy
import json
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.device_settings import parse_cutoffs, parse_heating, parse_lighting
from custom_components.hoymiles_home.diagnostics import _cutoff_diagnostics, _device_settings_diagnostics
from custom_components.hoymiles_home.errors import HoymilesConnectionError, HoymilesSettingsError

TARGET = {"dev_sn": "ABCDEF000001", "dtu_sn": "ABCDEF000002"}
TREE = [{"type": 12, "sn": TARGET["dev_sn"], "dtu_sn": TARGET["dtu_sn"]}]
RAW = {"r": 10, "g": 20, "b": 30, "slb": 128, "slot": 300, "ldb": 128, "sot": 300}


def test_integer_response_strings_follow_android_parsing():
    assert parse_cutoffs({"sl": "12", "sh": "100"}) == {"sl": 12, "sh": 100}
    assert parse_heating({"enable": "1"}) == {"enable": 1}
    raw = {**{key: str(value) for key, value in RAW.items()}, "vendor_option": "123"}
    parsed = parse_lighting(raw, TARGET)
    assert parsed["values"] == RAW
    assert parsed["snapshot"] == {**RAW, "vendor_option": "123"}
    assert raw["ldb"] == "128"  # Caller input remains untouched.


@pytest.mark.parametrize("value", [True, False, 12.0, "12.0", " 12", "12 ", "+12", "1e1", "１２", "000000000012"])
def test_response_compatibility_does_not_accept_arbitrary_coercion(value):
    with pytest.raises(HoymilesConnectionError):
        parse_cutoffs({"sl": value, "sh": 100})


async def test_lighting_json_text_and_numeric_station_id():
    api = HoymilesHomeClient(AsyncMock(), "test@example.com", "synthetic")
    raw = {**{key: str(value) for key, value in RAW.items()}, "sid": "123"}
    api._async_device_settings_action = AsyncMock(return_value=json.dumps(raw))
    data = await api.async_light_display_settings(123, TARGET)
    assert "sid" not in data
    assert parse_lighting(data, TARGET)["values"] == RAW
    api._async_device_settings_action.return_value = json.dumps({**raw, "sid": "456"})
    with pytest.raises(HoymilesSettingsError) as caught:
        await api.async_light_display_settings(123, TARGET)
    assert caught.value.reason == "invalid_station"


async def test_mixed_numeric_response_types_confirm_one_write(hass):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, device_controls=True)
    coordinator.device_tree = deepcopy(TREE)
    manager = coordinator.device_settings
    manager.target = TARGET
    manager._store("lighting", parse_lighting(RAW, TARGET))
    api.async_light_display_settings.side_effect = [
        {key: str(value) for key, value in RAW.items()},
        {**{key: str(value) for key, value in RAW.items()}, "ldb": "255"},
    ]
    with patch("custom_components.hoymiles_home.device_settings.READBACK_ATTEMPTS", 1):
        await manager.async_set_lighting({"ldb": 255})
    api.async_write_light_display_settings.assert_awaited_once_with(123, TARGET, {**RAW, "ldb": 255})
    assert manager.available("lighting")
    await coordinator.async_shutdown()


async def test_cutoff_failure_reports_only_field_types_and_clears_on_recovery(hass):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    coordinator.device_tree = deepcopy(TREE)
    manager = coordinator.cutoff_settings
    bad = {"sl": "SENSITIVE_VALUE", "sh": 100, "private_token": "SENSITIVE_TOKEN"}
    try:
        parse_cutoffs(bad)
    except HoymilesSettingsError as error:
        api.async_cutoff_settings.side_effect = error
    await manager._async_refresh()
    diag = _cutoff_diagnostics(manager)
    assert diag["last_error"] == {"reason": "invalid_cutoffs", "response_shape": {
        "type": "object", "field_types": {"sh": "integer", "sl": "string"},
    }}
    assert diag["target_selected"] is True
    assert "SENSITIVE" not in json.dumps(diag)
    assert TARGET["dev_sn"] not in json.dumps(diag)
    api.async_cutoff_settings.side_effect = None
    api.async_cutoff_settings.return_value = {"sl": "12", "sh": "100"}
    await manager._async_refresh()
    assert _cutoff_diagnostics(manager)["last_error"] is None
    assert manager.available("cutoffs")
    await coordinator.async_shutdown()


async def test_cloud_command_failure_is_distinct_from_parsing_failure(hass):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, device_controls=True)
    coordinator.device_tree = deepcopy(TREE)
    api.async_heating_settings.return_value = {"enable": 1}
    api.async_light_display_settings.side_effect = HoymilesSettingsError("command_failed", "fixed message")
    await coordinator.device_settings._async_refresh()
    diag = _device_settings_diagnostics(coordinator.device_settings)
    assert diag["heating"]["status"] == "readable"
    assert diag["lighting"]["last_error"]["reason"] == "command_failed"
    await coordinator.async_shutdown()
