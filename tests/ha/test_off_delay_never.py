"""App Never sentinel must not disable all light/display settings."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import UnitOfTime

from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.device_settings import light_update, parse_lighting
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from custom_components.hoymiles_home.number import HoymilesDeviceSettingNumber
from custom_components.hoymiles_home.select import HoymilesOffDelaySelect
from custom_components.hoymiles_home.light import HoymilesIndicatorLight

TARGET = {"dev_sn": "ABCDEF000001", "dtu_sn": "ABCDEF000002"}
RAW = {"r": 10, "g": 20, "b": 30, "slb": 255, "slot": 65535, "ldb": 128, "sot": 300,
       "vendor_mode": {"keep": True}}
ENTRY = SimpleNamespace(entry_id="entry", data={"station_id": 123})


@pytest.mark.parametrize("field", ["slot", "sot"])
@pytest.mark.parametrize("value", [65535, "65535"])
def test_never_is_a_valid_timeout_and_preserved_for_unrelated_edits(field, value):
    raw = {**RAW, field: value}
    parsed = parse_lighting(raw, TARGET)
    assert parsed["values"][field] == 65535
    changed = light_update(parsed, {"ldb": 64})
    assert changed[field] == 65535
    assert changed["vendor_mode"] == raw["vendor_mode"]
    assert raw[field] == value


@pytest.mark.parametrize("field", ["slot", "sot"])
@pytest.mark.parametrize("value", [3601, 65534, 65536, -1, True, 65535.0, "65535.0"])
def test_other_out_of_range_timeouts_remain_rejected(field, value):
    with pytest.raises(HoymilesConnectionError):
        parse_lighting({**RAW, field: value}, TARGET)


def test_never_is_not_a_valid_brightness():
    with pytest.raises(HoymilesConnectionError):
        parse_lighting({**RAW, "slb": 65535}, TARGET)


@pytest.mark.parametrize("updates", [{"slot": 65535}, {"sot": 65535}])
def test_never_can_be_written_without_mutating_original_snapshot(updates):
    parsed = parse_lighting({**RAW, "slot": 300}, TARGET)
    before = deepcopy(parsed)
    assert light_update(parsed, updates) == {**parsed["snapshot"], **updates}
    assert parsed == before


async def test_never_controls_round_trip_and_keep_counterpart(hass):
    api = AsyncMock()
    api.async_heating_settings.return_value = {"enable": 1}
    api.async_light_display_settings.return_value = deepcopy(RAW)
    coordinator = HoymilesHomeCoordinator(hass, api, 123, device_controls=True)
    coordinator.device_tree = [{"type": 12, "sn": TARGET["dev_sn"], "dtu_sn": TARGET["dtu_sn"]}]
    manager = coordinator.device_settings
    try:
        await manager._async_refresh()
        coordinator.last_update_success = True
        strip = HoymilesOffDelaySelect(coordinator, ENTRY, "strip_off_delay_preset", "slot")
        display = HoymilesOffDelaySelect(coordinator, ENTRY, "display_off_delay_preset", "sot")
        number = HoymilesDeviceSettingNumber(coordinator, ENTRY, "strip_off_delay", "slot", 3600, UnitOfTime.SECONDS)
        assert strip.available and display.available
        assert strip.current_option == "never"
        assert display.current_option == "five_minutes"
        assert not number.available and number.native_value is None
        assert strip.extra_state_attributes == {"delay_seconds": None, "automatic_off": False}
        assert HoymilesIndicatorLight(coordinator, ENTRY).available
        brightness = HoymilesDeviceSettingNumber(coordinator, ENTRY, "display_brightness", "ldb", 100, "%")
        assert brightness.available
        api.async_light_display_settings.side_effect = [deepcopy(RAW), {**RAW, "sot": 65535}]
        with patch("custom_components.hoymiles_home.device_settings.READBACK_ATTEMPTS", 1):
            await display.async_select_option("never")
        written = api.async_write_light_display_settings.call_args.args[-1]
        assert written == {**RAW, "sot": 65535}
        assert display.current_option == "never"
        # Existing seconds entity returns when a regular duration is selected.
        api.async_light_display_settings.side_effect = [{**RAW, "sot": 65535}, {**RAW, "slot": 60, "sot": 65535}]
        with patch("custom_components.hoymiles_home.device_settings.READBACK_ATTEMPTS", 1):
            await strip.async_select_option("one_minute")
        assert number.available and number.native_value == 60
        assert strip.current_option == "one_minute"
        with pytest.raises(HomeAssistantError):
            await strip.async_select_option("invalid")
        coordinator.device_controls = False
        assert not strip.available
    finally:
        await coordinator.async_shutdown()


async def test_custom_seconds_option_preserves_existing_automation_duration(hass):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, device_controls=True)
    try:
        coordinator.device_settings.lighting = parse_lighting({**RAW, "sot": 720}, TARGET)
        entity = HoymilesOffDelaySelect(coordinator, ENTRY, "display_off_delay_preset", "sot")
        assert entity.current_option == "custom"
        assert "custom" in entity.options
        assert entity.extra_state_attributes == {"delay_seconds": 720, "automatic_off": True}
        await entity.async_select_option("custom")
        api.async_write_light_display_settings.assert_not_called()
    finally:
        await coordinator.async_shutdown()
