"""PV source options, readable battery activity and allowlisted diagnostics."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.diagnostics import async_get_config_entry_diagnostics
from custom_components.hoymiles_home.sensor import HoymilesStationSensor, STATION_SENSORS
from custom_components.hoymiles_home.telemetry import (
    battery_activity, number, pv_power_details,
)


@pytest.mark.parametrize("power,selection,value,source", [
    ({"pv": 500, "pv2": 0}, "auto", 0, "pv2"),
    ({"pv": 500, "pv2": 0}, "pv", 500, "pv"),
    ({"pv": 0, "pv2": 500}, "pv", 0, "pv"),
    ({"pv": 500, "pv2": 0}, "pv2", 0, "pv2"),
    ({"pv": "125.5"}, "auto", 125.5, "pv"),
    ({"pv2": 500}, "pv", None, "pv"),
    ({"pv": 500}, "pv2", None, "pv2"),
    ({"pv": 500, "pv2": "NaN"}, "auto", 500, "pv"),
    ({"pv": 500, "pv2": False}, "auto", 500, "pv"),
    ({}, "auto", None, "pv"),
    ({"pv": 500, "pv2": 0}, "invalid", 0, "pv2"),
])
def test_pv_selection_never_adds_fields_or_replaces_a_valid_zero(power, selection, value, source):
    details = pv_power_details({"live": {"power": power}, "pv_power_source": selection})
    assert details["value"] == value
    assert details["source"] == source


@pytest.mark.parametrize("value", [True, False, "TOKEN", "inf", "nan", float("nan"), [], {}])
def test_only_finite_numeric_values_are_exported(value):
    assert number(value) is None


@pytest.mark.parametrize("code,activity", [
    (0, "idle"), (1, "charging"), (2, "discharging"),
    ("1", "charging"), (9, "unrecognized"), (1.5, "unrecognized"),
    (None, None), (False, None), ("invalid", None),
])
def test_battery_activity_uses_only_brs(code, activity):
    assert battery_activity({"brs": code, "ems": 2, "chs": 1}) == activity


@pytest.mark.parametrize("source", ["auto", "pv", "pv2"])
async def test_options_flow_preserves_entry_and_other_options(hass, source):
    data = {"username": "test@example.com", "password": "secret", "station_id": 123}
    entry = MockConfigEntry(domain=DOMAIN, unique_id="existing-id", data=data,
                            options={"other_option": "keep"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"pv_power_source": source}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"other_option": "keep", "pv_power_source": source,
                             "inverter_details": False, "station_timezone": hass.config.time_zone}
    assert entry.data == data
    assert entry.unique_id == "existing-id"


async def test_source_flows_through_coordinator_to_existing_sensor(hass):
    api = AsyncMock()
    api.async_live.return_value = {"power": {"pv": 420, "pv2": 0}, "brs": 1}
    api.async_station_realtime.return_value = {}
    api.async_module_values.return_value = {}
    coordinator = HoymilesHomeCoordinator(hass, api, 123, pv_power_source="pv")
    coordinator.device_tree = [{"id": 99}]
    with patch.object(coordinator, "_async_refresh_battery_settings", new=AsyncMock()):
        coordinator.data = await coordinator._async_update_data()
        await hass.async_block_till_done()
    entry = SimpleNamespace(entry_id="existing", data={"station_id": 123})
    descriptions = {item.key: item for item in STATION_SENSORS}
    pv = HoymilesStationSensor(coordinator, entry, descriptions["pv_power"])
    assert pv.unique_id == "existing_pv_power"
    assert pv.native_value == 420
    assert pv.extra_state_attributes == {"selection": "pv", "source": "pv", "pv": 420, "pv2": 0}
    activity = HoymilesStationSensor(coordinator, entry, descriptions["battery_activity"])
    assert activity.native_value == "charging"
    raw = HoymilesStationSensor(coordinator, entry, descriptions["brs"])
    assert raw.unique_id == "existing_brs"
    assert raw.native_value == 1
    assert raw.extra_state_attributes["raw_codes"]["ems"] is None


async def test_battery_diagnostics_exclude_raw_payloads_and_error_text(hass):
    entry = SimpleNamespace(entry_id="test", data={"password": "SECRET"})
    coordinator = SimpleNamespace(
        inverters=[], data={"pv_power_source": "pv", "live": {
            "power": {"pv": 500, "pv2": 0, "bat": 100, "token": "TOKEN"},
            "brs": 2, "ems": 7, "chs": "PRIVATE", "bhs": 0,
            "soc": 50, "sn": "SERIAL", "address": "ADDRESS",
        }}, battery_settings={
            "readable": True, "writable": False, "request_method": "device",
            "work_mode_request_error": "PASSWORD TOKEN", "error": "SERIAL",
            "active_settings": {"reserve_soc": 12, "max_power": "SECRET"},
            "raw_payload": "SECRET", "mode": 1,
        },
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["pv_power"] == {"selection": "pv", "source": "pv", "value": 500, "pv": 500, "pv2": 0}
    assert result["battery"]["raw_status_codes"] == {"ems": 7, "brs": 2, "chs": None, "bhs": 0}
    assert result["battery"]["settings"]["used_work_mode_fallback"] is True
    assert result["battery"]["settings"]["reserve_soc"] == 12
    assert result["battery"]["settings"]["max_power"] is None
    for secret in ("SECRET", "TOKEN", "PASSWORD", "SERIAL", "ADDRESS", "PRIVATE"):
        assert secret not in json.dumps(result)
