"""Regression tests for cloud failures, lifecycle and stale measurements."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientConnectionError, ClientResponseError

from custom_components.hoymiles_home.api import (
    HoymilesAuthError, HoymilesConnectionError, HoymilesHomeClient,
    HoymilesRateLimitError,
)
from custom_components.hoymiles_home.battery import (
    BatterySettingsError, confirmed_reserve_soc, parse_work_mode_settings,
)
from custom_components.hoymiles_home.button import HoymilesRefreshBatterySettingsButton
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.sensor import (
    HoymilesModuleSensor, HoymilesStationSensor, MODULE_SENSORS, STATION_SENSORS,
)


def api_client():
    api = HoymilesHomeClient(MagicMock(), "private@example.com", "password")
    api._token = "TOKEN"
    api._token_expires = datetime.now(UTC) + timedelta(hours=1)
    return api


@pytest.mark.parametrize("failure", [HoymilesConnectionError("reset"), HoymilesAuthError("expired")])
async def test_failed_live_uri_is_replaced_once(failure):
    api = api_client()
    api._live_uri = "https://neapi.hoymiles.com/old"
    api._get_live_uri = AsyncMock(return_value="https://neapi.hoymiles.com/new")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(side_effect=[failure, {"status": "0", "data": {"con": 1, "power": {"pv": 12}}}])
    assert (await api.async_live(123))["power"]["pv"] == 12
    api._get_live_uri.assert_awaited_once_with(123)
    assert api._json.await_args.args[0].endswith("/new")
    assert api._json.await_count == 2


async def test_persistent_live_failure_is_bounded_and_cache_cleared():
    api = api_client()
    api._get_live_uri = AsyncMock(return_value="https://neapi.hoymiles.com/live")
    api._json = AsyncMock(side_effect=HoymilesConnectionError("reset"))
    with pytest.raises(HoymilesConnectionError):
        await api.async_live(123)
    assert api._json.await_count == 2
    assert api._live_uri is None


async def test_offline_envelope_without_flow_is_a_valid_sample():
    api = api_client()
    api._live_uri = "https://neapi.hoymiles.com/live"
    api._json = AsyncMock(return_value={"status": "0", "data": {"con": 0, "dly": 10000}})
    assert await api.async_live(123) == {"con": 0, "dly": 10000}
    api._json.assert_awaited_once()


async def test_concurrent_expired_token_calls_share_one_login():
    api = api_client()
    api._token = None

    async def login():
        await asyncio.sleep(0)
        api._token = "NEW"
        api._token_expires = datetime.now(UTC) + timedelta(hours=1)

    api._async_login_unlocked = AsyncMock(side_effect=login)
    await asyncio.gather(*(api.async_ensure_login() for _ in range(5)))
    api._async_login_unlocked.assert_awaited_once()


async def test_argon2_runs_outside_event_loop():
    api = api_client()
    api._json = AsyncMock(side_effect=[
        {"status": "0", "data": {"a": "0123456789abcdef", "n": "nonce"}},
        {"status": "0", "data": {"token": "NEW"}},
    ])
    with patch("custom_components.hoymiles_home.api.asyncio.to_thread", new=AsyncMock(return_value=b"challenge")) as worker:
        await api.async_login()
    worker.assert_awaited_once()
    assert api._json.await_args.args[1]["ch"] == b"challenge".hex()


@pytest.mark.parametrize("status,error", [(401, HoymilesAuthError), (403, HoymilesConnectionError), (500, HoymilesConnectionError)])
async def test_http_failures_do_not_expose_signed_url(status, error):
    api = api_client()
    response = MagicMock(status=status)
    response.raise_for_status.side_effect = ClientResponseError(
        SimpleNamespace(real_url="https://neapi.hoymiles.com/?token=PRIVATE"), (), status=status,
    )
    api._session.post.return_value.__aenter__.return_value = response
    with pytest.raises(error) as caught:
        await api._json("https://neapi.hoymiles.com/test", {})
    assert "PRIVATE" not in str(caught.value)
    if status == 401:
        assert api._token_expires < datetime.now(UTC)


async def test_transport_failure_does_not_expose_signed_url():
    api = api_client()
    api._session.post.side_effect = ClientConnectionError("https://neapi.hoymiles.com/?token=PRIVATE")
    with pytest.raises(HoymilesConnectionError) as caught:
        await api._json("https://neapi.hoymiles.com/test", {})
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("raw", [b"\x0a\x05x", b"\x0a\x01\xff", b"  {broken json}"])
async def test_malformed_chart_is_a_handled_connection_error(raw):
    api = api_client()
    response = MagicMock(status=200)
    response.read = AsyncMock(return_value=raw)
    async def chunks(*args):
        yield raw
    response.content.iter_chunked = chunks
    api._session.post.return_value.__aenter__.return_value = response
    with pytest.raises(HoymilesConnectionError):
        await api.async_module_values(123, 99, 1, "2026-10-29")


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), None])
def test_bad_samples_break_energy_integration_instead_of_bridging(hass, bad):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    coordinator._energy_store.async_delay_save = MagicMock()
    now = datetime.now(UTC)
    sample = {"con": 1, "brs": 1, "power": {"bat": 1000, "load": 1000}}
    coordinator._update_battery_energy(sample, now)
    coordinator._update_battery_energy({"con": 1, "power": {"bat": bad, "load": bad}}, now + timedelta(seconds=3))
    result = coordinator._update_battery_energy(sample, now + timedelta(seconds=6))
    assert result["charge_wh"] == result["consumption_wh"] == 0
    result = coordinator._update_battery_energy(sample, now + timedelta(seconds=9))
    assert result["charge_wh"] == pytest.approx(0.833, abs=0.001)


def test_offline_values_do_not_add_energy(hass):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    coordinator._energy_store.async_delay_save = MagicMock()
    now = datetime.now(UTC)
    sample = {"con": 1, "brs": 2, "power": {"bat": 1000, "load": 1000}}
    coordinator._update_battery_energy(sample, now)
    coordinator._update_battery_energy({**sample, "con": 0}, now + timedelta(seconds=3))
    result = coordinator._update_battery_energy(sample, now + timedelta(seconds=6))
    assert result["discharge_wh"] == result["consumption_wh"] == 0


async def test_offline_live_sensors_and_stale_module_are_unavailable(hass):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    coordinator.data = {"live": {"con": 0, "power": {"pv": 100}}}
    entry = SimpleNamespace(entry_id="existing", data={"station_id": 123})
    descriptions = {item.key: item for item in STATION_SENSORS}
    pv = HoymilesStationSensor(coordinator, entry, descriptions["pv_power"])
    energy = HoymilesStationSensor(coordinator, entry, descriptions["battery_charge_energy_today"])
    assert not pv.available
    assert energy.available
    key, quota, unit, device_class = MODULE_SENSORS[0]
    module = HoymilesModuleSensor(coordinator, entry, {"id": 99}, 1, key, quota, unit, device_class)
    coordinator.module_updated[(99, 1)] = datetime.now(UTC)
    assert not module.available
    coordinator.data["live"]["con"] = 1
    assert module.available
    coordinator.module_updated[(99, 1)] -= timedelta(minutes=11)
    assert not module.available


async def test_refresh_coalesces_and_publishes_without_marking_live_healthy(hass):
    api = AsyncMock()
    started, release = asyncio.Event(), asyncio.Event()

    async def read(*args):
        started.set()
        await release.wait()
        return {"readable": True, "mode": 1}

    api.async_battery_settings.side_effect = read
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.data = {"live": {"con": 0}}
    coordinator.last_update_success = False
    coordinator.async_update_listeners = MagicMock()
    first = asyncio.create_task(coordinator.async_refresh_battery_settings())
    await started.wait()
    second = asyncio.create_task(coordinator.async_refresh_battery_settings())
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)
    api.async_battery_settings.assert_awaited_once()
    assert coordinator.data["battery_settings"]["readable"] is True
    assert coordinator.last_update_success is False
    coordinator.async_update_listeners.assert_called_once()
    await coordinator.async_shutdown()


async def test_shutdown_cancels_background_read(hass):
    api = AsyncMock()
    started = asyncio.Event()

    async def read(*args):
        started.set()
        await asyncio.Event().wait()

    api.async_battery_settings.side_effect = read
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    task = coordinator._start_battery_settings_refresh()
    await started.wait()
    await coordinator.async_shutdown()
    assert task.cancelled()
    assert coordinator._start_battery_settings_refresh() is None


async def test_refresh_button_only_reads(hass):
    api = AsyncMock()
    api.async_battery_settings.return_value = {"readable": True}
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    button = HoymilesRefreshBatterySettingsButton(coordinator, SimpleNamespace(
        entry_id="existing", data={"station_id": 123},
    ))
    await button.async_press()
    api.async_battery_settings.assert_awaited_once_with(123)
    api.async_write_battery_settings.assert_not_awaited()
    await coordinator.async_shutdown()


async def test_queued_write_uses_settings_after_lock_is_acquired(hass):
    api = AsyncMock()
    api.async_battery_settings.return_value = {"mode": 1, "readable": True, "writable": True, "reserve_soc_verified": True, "request_method": "station_action_83", "active_settings": {"reserve_soc": 20, "soc_l": 20, "soc_h": 90}}
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.battery_settings = {"writable": True, "request_method": "station_action_83", "mode": 1,
                                    "reserve_soc_verified": True,
                                    "active_settings": {"reserve_soc": 10, "soc_h": 100}}
    await coordinator._battery_settings_lock.acquire()
    task = asyncio.create_task(coordinator.async_set_battery_reserve_soc(20))
    await asyncio.sleep(0)
    coordinator.battery_settings["active_settings"]["soc_h"] = 90
    coordinator._battery_settings_lock.release()
    with patch("custom_components.hoymiles_home.coordinator.BATTERY_WRITE_CONFIRM_ATTEMPTS", 1):
        await task
    assert api.async_write_battery_settings.await_args.args[2]["soc_h"] == 90


@pytest.mark.parametrize("upper", [None, "bad", False, float("inf"), 101, 5, 90.5])
def test_invalid_work_mode_upper_soc_is_handled(upper):
    with pytest.raises(BatterySettingsError):
        parse_work_mode_settings({"code": 0, "data": {"mode": 2, "k_2": {"soc_l": 10, "soc_h": upper}}})


def test_reserve_soc_evidence_matches_exact_mode_segment():
    assert confirmed_reserve_soc([{"path": "data.k_10.reserve_soc", "value": 80}], 1) is None
    assert confirmed_reserve_soc([{"path": "data.k_1.reserve_soc", "value": 10}], 1) == 10


def test_daily_login_limit_is_not_invalid_credentials():
    with pytest.raises(HoymilesRateLimitError) as caught:
        HoymilesHomeClient._unwrap({"status": "1", "message": "The number of logins exceeds the daily maximum limit."})
    assert caught.value.retry_after == 3600


async def test_login_rate_limit_is_cached_for_concurrent_readers():
    api = api_client()
    api._token = None
    api._async_login_unlocked = AsyncMock(side_effect=HoymilesRateLimitError("limit", 300))
    for _ in range(3):
        with pytest.raises(HoymilesRateLimitError):
            await api.async_ensure_login()
    api._async_login_unlocked.assert_awaited_once()


async def test_live_rate_limit_is_not_retried_immediately():
    api = api_client()
    api._live_uri = "https://neapi.hoymiles.com/live"
    api._json = AsyncMock(side_effect=HoymilesRateLimitError("limit"))
    with pytest.raises(HoymilesRateLimitError):
        await api.async_live(123)
    api._json.assert_awaited_once()


async def test_http_429_honors_bounded_retry_after():
    api = api_client()
    response = MagicMock(status=429)
    response.raise_for_status.side_effect = ClientResponseError(
        SimpleNamespace(real_url="https://neapi.hoymiles.com/test"), (), status=429,
        headers={"Retry-After": "120"},
    )
    api._session.post.return_value.__aenter__.return_value = response
    with pytest.raises(HoymilesRateLimitError) as caught:
        await api._json("https://neapi.hoymiles.com/test", {})
    assert caught.value.retry_after == 120


async def test_coordinator_schedules_rate_limit_retry_without_reauth(hass):
    from homeassistant.helpers.update_coordinator import UpdateFailed
    api = AsyncMock()
    api.async_live.side_effect = HoymilesRateLimitError("limit", 120)
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    with pytest.raises(UpdateFailed) as caught:
        await coordinator._async_update_data()
    assert caught.value.retry_after == 120


@pytest.mark.parametrize("delay", [float("nan"), float("inf"), 1e300, True, "bad"])
async def test_invalid_poll_delay_does_not_crash(hass, delay):
    api = AsyncMock()
    api.async_live.return_value = {"con": 0, "dly": delay}
    api.async_station_realtime.return_value = {}
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.device_tree = [{"id": 99}]
    with patch.object(coordinator, "_async_refresh_battery_settings", new=AsyncMock()):
        await coordinator._async_update_data()
        await asyncio.sleep(0)
    assert coordinator.update_interval == timedelta(seconds=3)
    await coordinator.async_shutdown()


async def test_corrupt_energy_values_are_not_restored(hass):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    from custom_components.hoymiles_home.const import BATTERY_ENERGY_CALCULATION_VERSION
    coordinator._energy_store.async_load = AsyncMock(return_value={
        "date": coordinator._energy_date,
        "calculation_version": BATTERY_ENERGY_CALCULATION_VERSION,
        "charge_wh": float("nan"), "discharge_wh": float("inf"), "consumption_wh": 42,
    })
    await coordinator.async_initialize()
    assert coordinator._charge_wh == coordinator._discharge_wh == 0
    assert coordinator._consumption_wh == 42
