"""Publication review regressions; all cloud responses are synthetic."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.battery import parse_battery_settings
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from custom_components.hoymiles_home.number import HoymilesBatteryReserveSocNumber
from custom_components.hoymiles_home.select import HoymilesBatteryModeSelect
from custom_components.hoymiles_home.sensor import _battery_settings_attributes


def cloud_client(inner):
    raw = json.dumps({"status": "0", "data": inner}).encode()
    response = MagicMock(status=200)

    async def chunks(*args):
        yield raw

    response.content.iter_chunked = chunks
    session = MagicMock()
    session.post.return_value.__aenter__.return_value = response
    return HoymilesHomeClient(session, "test@example.com", "synthetic")


@pytest.mark.parametrize("depth", [33, 500, 2000])
async def test_embedded_json_cannot_bypass_depth_guard(depth):
    inner = '{"code":0,"data":' + '[' * depth + '0' + ']' * depth + '}'
    api = cloud_client(inner)
    with patch("custom_components.hoymiles_home.api.BATTERY_SETTINGS_POLL_INTERVAL", 0):
        with pytest.raises(HoymilesConnectionError):
            await api._async_poll_station_setting_job("synthetic-job")


@pytest.mark.parametrize("inner", [
    '{"code":0,"data":{"mode":2,"soc_l":12,"soc_h":95}}',
    {"code": 0, "data": {"mode": 2, "soc_l": 12, "soc_h": 95}},
])
async def test_valid_embedded_or_direct_work_mode_still_works(inner):
    api = cloud_client(inner)
    with patch("custom_components.hoymiles_home.api.BATTERY_SETTINGS_POLL_INTERVAL", 0):
        result = await api._async_poll_station_setting_job("synthetic-job")
    assert result == {"code": 0, "data": {"mode": 2, "soc_l": 12, "soc_h": 95}}


@pytest.mark.parametrize("inner", ['{"code":', '[]', 'null', '\ud800'])
async def test_invalid_embedded_json_is_a_handled_connection_error(inner):
    api = cloud_client(inner)
    with patch("custom_components.hoymiles_home.api.BATTERY_SETTINGS_POLL_INTERVAL", 0):
        with pytest.raises(HoymilesConnectionError):
            await api._async_poll_station_setting_job("synthetic-job")


def test_cloud_settings_do_not_copy_unexpected_fields_to_sensor_attributes():
    raw = {"reserve_soc": 20, "soc_h": 95, "token": "SYNTHETIC_TOKEN",
           "account_email": "synthetic@example.com", "schedule": [{"private": "SYNTHETIC"}]}
    settings = parse_battery_settings({"code": 0, "data": {"mode": 1, "data": {"k_1": raw}}})
    settings.update(error="SYNTHETIC_ERROR", user_setting_probes=[{"private": "SYNTHETIC"}],
                    available_mode_names=["SYNTHETIC"], work_mode_request_error="SYNTHETIC")
    result = _battery_settings_attributes({"battery_settings": settings})
    assert result["active_settings"] == {"reserve_soc": 20, "soc_h": 95}
    assert result["mode_settings"] == {1: {"reserve_soc": 20, "soc_h": 95}}
    assert result["available_mode_names"] == ["Self-Consumption"]
    assert result["has_error"] and result["used_work_mode_fallback"]
    assert "SYNTHETIC" not in json.dumps(result)
    # Filtering for display must not destroy the internal write snapshot.
    assert settings["active_settings"]["token"] == "SYNTHETIC_TOKEN"


@pytest.mark.parametrize("invalid", [True, "SYNTHETIC", 10 ** 400, float("nan"), float("inf"), {"private": "SYNTHETIC"}])
def test_attributes_accept_only_finite_numeric_settings(invalid):
    result = _battery_settings_attributes({"battery_settings": {"active_settings": {"reserve_soc": invalid}}})
    assert result["active_settings"] == {}


@pytest.mark.parametrize("options,enabled", [({}, False), ({"battery_controls": False}, False), ({"battery_controls": True}, True)])
async def test_control_option_can_be_enabled_and_revoked_without_changing_identity(hass, options, enabled):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="existing-id", data={"station_id": 123}, options=options)
    entry.add_to_hass(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["type"] is FlowResultType.FORM
    configured = await hass.config_entries.options.async_configure(form["flow_id"], {"battery_controls": not enabled})
    assert configured["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["battery_controls"] is (not enabled)
    assert entry.unique_id == "existing-id"
    assert entry.data == {"station_id": 123}


@pytest.mark.parametrize("call,args", [("async_set_battery_mode", (8,)), ("async_set_battery_reserve_soc", (20,))])
async def test_default_read_only_blocks_commands_before_any_cloud_access(hass, call, args):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.battery_settings = {"mode": 1, "available_modes": [1, 8], "readable": True,
        "writable": True, "reserve_soc_verified": True, "active_settings": {"reserve_soc": 12}}
    entry = SimpleNamespace(entry_id="existing", data={"station_id": 123})
    assert not HoymilesBatteryModeSelect(coordinator, entry).available
    assert not HoymilesBatteryReserveSocNumber(coordinator, entry).available
    with pytest.raises(HoymilesConnectionError, match="disabled"):
        await getattr(coordinator, call)(*args)
    api.async_battery_settings.assert_not_awaited()
    api.async_write_battery_settings.assert_not_awaited()
    await coordinator.async_shutdown()


async def test_unload_during_preflight_prevents_late_write(hass):
    from custom_components.hoymiles_home.battery import parse_work_mode_settings
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    fresh = parse_work_mode_settings({"code": 0, "data": {"mode": 2, "soc_l": 12, "soc_h": 95}})
    coordinator.battery_settings = fresh

    async def stop_during_read(*args):
        await coordinator.async_shutdown()
        return fresh

    api.async_battery_settings.side_effect = stop_during_read
    with pytest.raises(HoymilesConnectionError, match="disabled"):
        await coordinator.async_set_battery_reserve_soc(20)
    api.async_write_battery_settings.assert_not_awaited()
