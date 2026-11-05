"""Device controls preserve fresh settings and require confirmed readback."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.device_settings import (
    light_target, light_update, parse_heating, parse_lighting, settings_equal,
)
from custom_components.hoymiles_home.errors import HoymilesConnectionError, HoymilesRateLimitError
from custom_components.hoymiles_home.light import HoymilesIndicatorLight
from custom_components.hoymiles_home.number import HoymilesDeviceSettingNumber
from custom_components.hoymiles_home.switch import HoymilesHeatingPermissionSwitch

TARGET = {"dev_sn": "ABCDEF000001", "dtu_sn": "ABCDEF000002"}
TREE = [{"type": 12, "sn": TARGET["dev_sn"], "dtu_sn": TARGET["dtu_sn"]}]
RAW = {"r": 10, "g": 20, "b": 30, "slb": 128, "slot": 300,
       "ldb": 128, "sot": 300, "vendor_option": {"value": 1}}
ENTRY = SimpleNamespace(entry_id="entry", data={"station_id": 123})


@pytest.fixture
async def controls(hass):
    api = AsyncMock()
    api.async_heating_settings.return_value = {"enable": 0}
    api.async_light_display_settings.return_value = deepcopy(RAW)
    coordinator = HoymilesHomeCoordinator(hass, api, 123, device_controls=True)
    coordinator.device_tree = deepcopy(TREE)
    manager = coordinator.device_settings
    await manager._async_refresh()
    api.reset_mock()
    with patch("custom_components.hoymiles_home.device_settings.READBACK_ATTEMPTS", 1):
        yield coordinator, api, manager
    await coordinator.async_shutdown()


@pytest.mark.parametrize("value", [True, False, -1, 2, "1", None, 1.0])
def test_heating_requires_explicit_integer_permission(value):
    with pytest.raises(HoymilesConnectionError):
        parse_heating({"enable": value})


def test_target_selection_never_guesses_among_controllers():
    assert light_target(TREE) == TARGET
    assert light_target([TREE, TREE]) == TARGET
    assert light_target([*TREE, {"type": 12, "sn": "ABCDEF000003"}]) is None
    assert light_target([{"type": 3, "sn": TARGET["dev_sn"]}]) is None
    assert light_target([{"type": 12, "sn": "untrusted/address"}]) is None


@pytest.mark.parametrize("change", [{"r": True}, {"slb": 256}, {"slot": -1},
                                    {"sot": 3601}, {"effect": "rainbow"}, {}])
def test_invalid_updates_do_not_change_snapshot(change):
    parsed = parse_lighting(RAW, TARGET)
    with pytest.raises(HoymilesConnectionError):
        light_update(parsed, change)
    assert parsed["snapshot"] == RAW


def test_capabilities_and_private_snapshot_are_separate():
    parsed = parse_lighting(RAW, TARGET)
    assert "vendor_option" not in parsed["values"]
    changed = light_update(parsed, {"ldb": 255})
    assert changed == {**RAW, "ldb": 255}
    changed["vendor_option"]["value"] = 2
    assert RAW["vendor_option"]["value"] == 1
    assert set(parse_lighting(RAW, {"dev_sn": "280500000001"})["values"]) == {"ldb", "sot"}
    assert set(parse_lighting({k: v for k, v in RAW.items() if k != "r"}, TARGET)["values"]) == {"ldb", "sot"}
    assert not settings_equal({"value": True}, {"value": 1})


@pytest.mark.parametrize("data", [{}, {"ldb": True, "sot": 300}, {"ldb": 1, "sot": 3601},
                                  {**RAW, "bad": float("nan")}])
def test_incomplete_or_invalid_display_is_unavailable(data):
    with pytest.raises(HoymilesConnectionError):
        parse_lighting(data, TARGET)


async def test_light_write_preserves_fresh_app_settings_and_checks_complete_readback(controls):
    coordinator, api, manager = controls
    fresh = {**deepcopy(RAW), "sot": 900, "vendor_option": {"value": 2}}
    expected = {**fresh, "slb": 200}
    api.async_light_display_settings.side_effect = [fresh, expected]
    await manager.async_set_lighting({"slb": 200})
    api.async_write_light_display_settings.assert_awaited_once_with(123, TARGET, expected)
    assert manager.lighting["values"]["sot"] == 900


@pytest.mark.parametrize("readback", [RAW, {**RAW, "slb": 200, "sot": 500},
                                      {**RAW, "slb": 200, "vendor_option": {"value": True}}])
async def test_failed_confirmation_never_resends_write(controls, readback):
    _, api, manager = controls
    api.async_light_display_settings.side_effect = [RAW, readback]
    with pytest.raises(HoymilesConnectionError, match="did not confirm"):
        await manager.async_set_lighting({"slb": 200})
    api.async_write_light_display_settings.assert_awaited_once()
    assert not manager.available("lighting")


@pytest.mark.parametrize("kind", ["permission", "unload", "target"])
async def test_changed_preflight_prevents_writes(controls, kind):
    coordinator, api, manager = controls

    async def fresh(*args):
        if kind == "permission":
            coordinator.device_controls = False
        elif kind == "unload":
            await coordinator.async_shutdown()
        else:
            coordinator.device_tree = []
        return RAW

    api.async_light_display_settings.side_effect = fresh
    with pytest.raises(HoymilesConnectionError):
        await manager.async_set_lighting({"ldb": 255})
    api.async_write_light_display_settings.assert_not_awaited()


async def test_heating_switch_is_permission_with_readback(controls):
    coordinator, api, manager = controls
    entity = HoymilesHeatingPermissionSwitch(coordinator, ENTRY)
    assert entity.is_on is False
    api.async_heating_settings.side_effect = [{"enable": 0}, {"enable": 1}]
    await entity.async_turn_on()
    api.async_write_heating_settings.assert_awaited_once_with(123, 1)
    assert entity.is_on is True
    assert entity.extra_state_attributes is None


async def test_concurrent_changes_take_new_snapshots(controls):
    _, api, manager = controls
    state = deepcopy(RAW)

    async def read(*args):
        await asyncio.sleep(0)
        return deepcopy(state)

    async def write(station, target, settings):
        state.update(deepcopy(settings))

    api.async_light_display_settings.side_effect = read
    api.async_write_light_display_settings.side_effect = write
    await asyncio.gather(manager.async_set_lighting({"ldb": 255}), manager.async_set_lighting({"sot": 900}))
    assert state == {**RAW, "ldb": 255, "sot": 900}
    assert api.async_write_light_display_settings.await_count == 2


@pytest.mark.parametrize("value", [True, -1, 101, 2.5, float("nan"), float("inf"), "50"])
async def test_invalid_number_values_do_not_contact_cloud(controls, value):
    coordinator, api, _ = controls
    entity = HoymilesDeviceSettingNumber(coordinator, ENTRY, "display_brightness", "ldb", 100, "%")
    with pytest.raises(HomeAssistantError):
        await entity.async_set_native_value(value)
    api.async_light_display_settings.assert_not_awaited()


async def test_entity_units_rgb_and_private_attributes(controls):
    coordinator, _, manager = controls
    manager.async_set_lighting = AsyncMock()
    light = HoymilesIndicatorLight(coordinator, ENTRY)
    brightness = HoymilesDeviceSettingNumber(coordinator, ENTRY, "display_brightness", "ldb", 100, "%")
    timeout = HoymilesDeviceSettingNumber(coordinator, ENTRY, "display_off_delay", "sot", 3600, "s")
    assert light.rgb_color == (10, 20, 30)
    assert light.brightness == 128
    assert brightness.native_value == 50
    assert timeout.native_value == 300
    await brightness.async_set_native_value(100)
    manager.async_set_lighting.assert_awaited_with({"ldb": 255})
    await timeout.async_set_native_value(900)
    manager.async_set_lighting.assert_awaited_with({"sot": 900})
    await light.async_turn_on(brightness=100, rgb_color=(1, 2, 3))
    manager.async_set_lighting.assert_awaited_with({"slb": 100, "r": 1, "g": 2, "b": 3}, turn_on=True)
    await light.async_turn_off()
    manager.async_set_lighting.assert_awaited_with({"slb": 0})
    assert light.extra_state_attributes is None
    assert brightness.unique_id == "entry_device_setting_display_brightness"
    with pytest.raises(HomeAssistantError):
        await light.async_turn_on(effect="rainbow")


async def test_disabled_controls_make_no_extra_requests(hass):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    manager = coordinator.device_settings
    assert manager.start() is None
    assert await manager.async_refresh() is False
    with pytest.raises(HoymilesConnectionError):
        await manager.async_set_heating(True)
    api.async_heating_settings.assert_not_awaited()
    await coordinator.async_shutdown()


async def test_refresh_coalesces_and_cache_expires(controls):
    _, api, manager = controls
    await asyncio.gather(manager.async_refresh(), manager.async_refresh())
    api.async_heating_settings.assert_awaited_once()
    assert await manager.async_refresh() is False
    manager.updated["heating"] = datetime.now(UTC) - timedelta(minutes=61)
    assert not manager.available("heating")


async def test_rate_limit_stops_followup_and_respects_pause(controls):
    _, api, manager = controls
    api.async_heating_settings.side_effect = HoymilesRateLimitError("limited", 3600)
    await manager._async_refresh()
    api.async_light_display_settings.assert_not_awaited()
    assert manager.start() is None
    assert await manager.async_refresh() is False


@pytest.mark.parametrize("operation,expected", [
    ("heating_read", {"action": 1518, "data": {"sid": 123}}),
    ("heating_write", {"action": 1518, "data": {"sid": 123, "enable": 1}}),
    ("light_read", {"action": 1529, **TARGET, "sid": 123}),
    ("light_write", {"action": 1529, **TARGET, "data": {**RAW, "sid": 123}}),
])
async def test_exact_vendor_envelopes_and_device_endpoints(operation, expected):
    client = HoymilesHomeClient(AsyncMock(), "test@example.com", "secret")
    client.async_ensure_login = AsyncMock()
    data = {"enable": 0} if operation.startswith("heating") else RAW
    client._json = AsyncMock(side_effect=[{"status": 0, "data": "command"},
        {"status": 0, "data": {"code": 2}},
        {"status": 0, "data": json.dumps({"code": 0, "data": data})}])
    with patch("custom_components.hoymiles_home.api.BATTERY_SETTINGS_POLL_INTERVAL", 0):
        if operation == "heating_read":
            assert await client.async_heating_settings(123) == data
        elif operation == "heating_write":
            await client.async_write_heating_settings(123, 1)
        elif operation == "light_read":
            assert await client.async_light_display_settings(123, TARGET) == data
        else:
            await client.async_write_light_display_settings(123, TARGET, RAW)
    first = client._json.await_args_list[0]
    assert first.args[0].endswith("/dev/setting/" + ("write" if operation.endswith("write") else "read"))
    assert first.args[1] == expected
    assert client._json.await_args_list[1].args[1] == {"id": "command"}
    assert client._json.await_args_list[1].args[0].endswith("/dev/setting/status")


@pytest.mark.parametrize("response", [True, None, {}, "", "x" * 257])
async def test_invalid_command_ids_cannot_be_polled(response):
    client = HoymilesHomeClient(AsyncMock(), "test@example.com", "secret")
    client.async_ensure_login = AsyncMock()
    client._json = AsyncMock(return_value={"status": 0, "data": response})
    with pytest.raises(HoymilesConnectionError):
        await client.async_heating_settings(123)
    assert client._json.await_count == 1


async def test_color_only_keeps_fresh_brightness(controls):
    _, api, manager = controls
    fresh = {**RAW, "slb": 200}
    expected = {**fresh, "r": 1, "g": 2, "b": 3}
    api.async_light_display_settings.side_effect = [fresh, expected]
    await manager.async_set_lighting({"r": 1, "g": 2, "b": 3}, turn_on=True)
    api.async_write_light_display_settings.assert_awaited_once_with(123, TARGET, expected)


async def test_turn_on_from_zero_uses_full_brightness_and_preserves_color(controls):
    _, api, manager = controls
    fresh = {**RAW, "slb": 0}
    expected = {**RAW, "slb": 255}
    api.async_light_display_settings.side_effect = [fresh, expected]
    await manager.async_set_lighting({}, turn_on=True)
    api.async_write_light_display_settings.assert_awaited_once_with(123, TARGET, expected)


async def test_already_matching_settings_do_not_send_write(controls):
    _, api, manager = controls
    await manager.async_set_heating(False)
    await manager.async_set_lighting({"sot": 300})
    api.async_write_heating_settings.assert_not_awaited()
    api.async_write_light_display_settings.assert_not_awaited()


@pytest.mark.parametrize("kwargs", [{"brightness": True}, {"brightness": 256},
    {"rgb_color": (1, 2)}, {"rgb_color": (1, -1, 2)}, {"rgb_color": (1, 2, 3.5)}])
async def test_invalid_light_values_do_not_contact_cloud(controls, kwargs):
    coordinator, api, _ = controls
    entity = HoymilesIndicatorLight(coordinator, ENTRY)
    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on(**kwargs)
    api.async_light_display_settings.assert_not_awaited()


async def test_fresh_loss_of_strip_capability_prevents_write(controls):
    _, api, manager = controls
    api.async_light_display_settings.return_value = {"ldb": 128, "sot": 300}
    with pytest.raises(HoymilesConnectionError):
        await manager.async_set_lighting({}, turn_on=True)
    api.async_write_light_display_settings.assert_not_awaited()


async def test_failed_live_update_is_not_hidden_by_settings_refresh(controls):
    coordinator, _, manager = controls
    coordinator.data = {"live": {}}
    coordinator.last_update_success = False
    await manager._async_refresh()
    assert coordinator.last_update_success is False
    assert not HoymilesHeatingPermissionSwitch(coordinator, ENTRY).available


async def test_shutdown_cancels_background_read(controls):
    coordinator, api, manager = controls
    started = asyncio.Event()

    async def read(*args):
        started.set()
        await asyncio.Event().wait()

    api.async_heating_settings.side_effect = read
    task = manager.start()
    await started.wait()
    await coordinator.async_shutdown()
    assert task.cancelled()
    api.async_light_display_settings.assert_not_awaited()


@pytest.mark.parametrize("status", [{"code": True}, {"code": 1}, None, "invalid json"])
async def test_bad_device_status_fails_without_raw_response_leak(status):
    client = HoymilesHomeClient(AsyncMock(), "test@example.com", "secret")
    client.async_ensure_login = AsyncMock()
    client._json = AsyncMock(side_effect=[{"status": 0, "data": 1}, {"status": 0, "data": status}])
    with patch("custom_components.hoymiles_home.api.BATTERY_SETTINGS_POLL_INTERVAL", 0):
        with pytest.raises(HoymilesConnectionError):
            await client.async_heating_settings(123)


async def test_light_read_rejects_wrong_station():
    client = HoymilesHomeClient(AsyncMock(), "test@example.com", "secret")
    client._async_device_settings_action = AsyncMock(return_value={**RAW, "sid": 456})
    with pytest.raises(HoymilesConnectionError):
        await client.async_light_display_settings(123, TARGET)


async def test_platforms_are_opt_in_and_create_expected_controls(controls, hass):
    from custom_components.hoymiles_home import light, switch, number, button
    coordinator, _, _ = controls
    hass.data.setdefault("hoymiles_home", {})[ENTRY.entry_id] = coordinator
    entities = []
    for platform in (light, switch, number, button):
        await platform.async_setup_entry(hass, ENTRY, entities.extend)
    assert len(entities) == 8  # Reserve SOC, existing refresh and six opt-in additions.
    assert len({entity.unique_id for entity in entities}) == 8
    coordinator.device_controls = False
    entities = []
    for platform in (light, switch, number, button):
        await platform.async_setup_entry(hass, ENTRY, entities.extend)
    assert len(entities) == 2
