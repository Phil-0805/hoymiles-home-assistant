"""Read-only battery temperatures: identity, Celsius, lifecycle and cadence."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.battery_telemetry import BatteryTelemetryPoller, parse_battery_temperatures
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.diagnostics import async_get_config_entry_diagnostics
from custom_components.hoymiles_home.errors import HoymilesConnectionError, HoymilesRateLimitError
from custom_components.hoymiles_home.sensor import HoymilesBatteryTemperatureSensor, async_setup_entry
from custom_components.hoymiles_home.const import DOMAIN

SN, PACK = "2800A0000001", "2805A0000002"


def test_parse_main_and_expansion_without_scaling_or_raw_exports():
    raw = [{"sn": SN.lower(), "temp": 0, "account": "PRIVATE", "pack_list": [{"sn": PACK, "temp": -2.5}]}]
    before = deepcopy(raw)
    assert parse_battery_temperatures(raw) == {SN: {"temperature": 0, "parent": None}, PACK: {"temperature": -2.5, "parent": SN}}
    assert raw == before


@pytest.mark.parametrize("value", [None, True, "20°C", float("nan"), float("inf"), 65535, -273.15])
def test_invalid_temperature_is_missing_never_zero(value):
    assert parse_battery_temperatures([{"sn": SN, "temp": value}])[SN]["temperature"] is None


@pytest.mark.parametrize("raw", [{}, None, [None, {"sn": "private@example.com", "temp": 20}]])
def test_unexpected_response_or_invalid_identity_is_not_exported(raw):
    if isinstance(raw, list):
        assert parse_battery_temperatures(raw) == {}
    else:
        with pytest.raises(HoymilesConnectionError):
            parse_battery_temperatures(raw)


def test_ambiguous_identity_and_excessive_devices_are_rejected():
    with pytest.raises(HoymilesConnectionError):
        parse_battery_temperatures([{"sn": SN, "temp": 10}, {"sn": SN, "temp": 11}])
    with pytest.raises(HoymilesConnectionError):
        parse_battery_temperatures([{}] * 65)


async def test_api_uses_dedicated_https_read_only_endpoint():
    api = HoymilesHomeClient(MagicMock(), "test@example.com", "secret")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(return_value={"status": "0", "data": [{"sn": SN, "temp": 21.5}]})
    values = await api.async_battery_temperatures(123)
    api._json.assert_awaited_once_with("https://neapi.hoymiles.com/pvm/api/0/dev/au_inv/au_s_c", {"id": 123})
    assert values[SN]["temperature"] == 21.5


async def test_disabled_poller_never_calls_endpoint(hass):
    api = AsyncMock()
    poller = BatteryTelemetryPoller(hass, api, 123, False, MagicMock())
    assert poller.start() is None
    api.async_battery_temperatures.assert_not_awaited()
    await poller.async_shutdown()


async def test_five_minute_budget_missing_values_and_expiry(hass, freezer):
    freezer.move_to("2026-10-29T12:00:00+00:00")
    api = AsyncMock()
    api.async_battery_temperatures.return_value = {SN: {"temperature": 20, "parent": None}}
    poller = BatteryTelemetryPoller(hass, api, 123, True, MagicMock())
    await poller.start()
    assert poller.start() is None
    assert poller.is_fresh(SN)
    freezer.move_to("2026-10-29T12:05:00+00:00")
    api.async_battery_temperatures.return_value = {SN: {"temperature": None, "parent": None}}
    await poller.start()
    assert poller.values[SN]["temperature"] == 20
    assert poller.updated[SN] == datetime(2026, 10, 29, 12, tzinfo=UTC)
    freezer.move_to("2026-10-29T12:10:01+00:00")
    assert not poller.is_fresh(SN)
    assert api.async_battery_temperatures.await_count == 2
    await poller.async_shutdown()


async def test_rate_limit_pause_no_immediate_retry(hass, freezer):
    freezer.move_to("2026-10-29T12:00:00+00:00")
    api = AsyncMock()
    api.async_battery_temperatures.side_effect = HoymilesRateLimitError("limited", 900)
    poller = BatteryTelemetryPoller(hass, api, 123, True, MagicMock())
    await poller.start()
    freezer.move_to("2026-10-29T12:06:00+00:00")
    assert poller.start() is None
    assert poller.status == "rate_limited"
    api.async_battery_temperatures.assert_awaited_once()
    await poller.async_shutdown()


async def test_background_read_does_not_block_live_and_unload_cancels(hass):
    started, block = asyncio.Event(), asyncio.Event()
    api = AsyncMock()
    async def slow(*args):
        started.set()
        await block.wait()
    api.async_battery_temperatures.side_effect = slow
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_temperatures=True)
    coordinator.battery_telemetry.start()
    await started.wait()
    api.async_live.return_value = {"con": 1, "power": {"pv": 12}}
    api.async_station_realtime.return_value = {}
    coordinator.device_tree = [{"id": 99}]
    with patch.object(coordinator, "_async_refresh_battery_settings", new=AsyncMock()):
        data = await asyncio.wait_for(coordinator._async_update_data(), 0.5)
    assert data["live"]["power"]["pv"] == 12
    assert not block.is_set()
    await coordinator.async_shutdown()
    assert coordinator.battery_telemetry.task.cancelled()
    assert coordinator.battery_telemetry.start() is None


async def test_dynamic_entities_share_station_device_and_keep_private_diagnostics(hass):
    api = AsyncMock()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_temperatures=True)
    coordinator.data = {"live": {"con": 1}}
    hass.data.setdefault(DOMAIN, {})["entry"] = coordinator
    unload = []
    entry = SimpleNamespace(entry_id="entry", data={"station_id": 123}, async_on_unload=unload.append)
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    assert not any(isinstance(e, HoymilesBatteryTemperatureSensor) for e in entities)
    api.async_battery_temperatures.return_value = parse_battery_temperatures([
        {"sn": SN, "temp": None, "pack_list": [{"sn": PACK, "temp": 0}]}
    ])
    await coordinator.battery_telemetry.start()
    coordinator.async_update_listeners()
    sensors = [e for e in entities if isinstance(e, HoymilesBatteryTemperatureSensor)]
    assert len(sensors) == 2  # Parent must exist even without its own valid sample.
    parent, pack = sensors
    assert not parent.available
    assert pack.available and pack.native_value == 0
    assert pack.device_info["identifiers"] == parent.device_info["identifiers"] == {(DOMAIN, "station_123")}
    assert pack.unique_id == f"entry_battery_{PACK}_temperature"
    assert pack.extra_state_attributes["battery_serial"] == PACK
    assert pack.extra_state_attributes["freshness_basis"] == "cloud_response"
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["battery_telemetry"] == {"enabled": True, "status": "readable", "device_count": 2}
    assert SN not in str(result) and PACK not in str(result)
    for callback in unload:
        callback()
    await coordinator.async_shutdown()


def test_numeric_string_uses_existing_cloud_number_parser():
    assert parse_battery_temperatures([{ "sn": SN, "temp": "20.5"}])[SN]["temperature"] == 20.5
