"""Wait for live telemetry without URI churn, stale values or unbounded reads."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.hoymiles_home import api as api_module
from custom_components.hoymiles_home import cloud_runtime
from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import (
    HoymilesAuthError, HoymilesConnectionError, HoymilesLivePending, HoymilesRateLimitError,
)
from custom_components.hoymiles_home.telemetry import live_pending_delay

SECRET = "PRIVATE_PASSWORD_TOKEN_SERIAL_URI"
LIVE = "https://neapi.hoymiles.com/live?signature=" + SECRET
SAMPLE = {"flow": [], "con": 1, "power": {"pv": 42}}
REAL_SLEEP = asyncio.sleep


def ok(data):
    return {"status": "0", "data": data}


def client(*responses, profile="home"):
    api = HoymilesHomeClient(MagicMock(), SECRET, SECRET, profile=profile)
    api._token = SECRET
    api._token_expires = datetime.now(UTC) + timedelta(hours=1)
    api._live_uri = LIVE
    api._get_live_uri = AsyncMock(return_value=LIVE)
    api._json = AsyncMock(side_effect=responses)
    return api


@pytest.fixture
def clock(monkeypatch):
    clock = SimpleNamespace(now=100.0, sleeps=[])
    monkeypatch.setattr(api_module, "monotonic", lambda: clock.now)
    monkeypatch.setattr(cloud_runtime, "monotonic", lambda: clock.now)

    async def sleep(seconds):
        clock.sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr(api_module, "live_sleep", sleep)
    return clock


@pytest.mark.parametrize("delay,expected", [(0, 3), (1, 3), (3000, 3), (5000, 5), (30000, 30)])
@pytest.mark.parametrize("profile", ["home", "installer"])
async def test_pending_waits_and_reuses_uri_without_failure_or_fake_sample(clock, caplog, delay, expected, profile):
    api = client(ok({"dly": delay, SECRET: SECRET}), ok(SAMPLE), profile=profile)
    assert await api.async_live(123) == SAMPLE
    assert clock.sleeps == [expected]
    assert api._json.await_count == 2
    body = {"sid": 123, "m": 0} if profile == "home" else {"m": 0, "t": 1}
    assert [c.args for c in api._json.call_args_list] == [(LIVE, body), (LIVE, body)]
    api._get_live_uri.assert_not_awaited()
    assert api._live_uri == LIVE
    assert "invalid_live_data" not in caplog.text and "Cloud request recovered" not in caplog.text
    assert SECRET not in caplog.text


@pytest.mark.parametrize("payload", [
    {}, None, [], {"dly": -1}, {"dly": True}, {"dly": "5000"}, {"dly": 5000.0},
    {"dly": float("inf")}, {"dly": 2**63}, {"dly": {}},
    {"dly": 5000, "flow": None}, {"dly": 5000, "con": None},
    {"dly": 5000, "power": None}, {"dly": 5000, "con": True},
])
def test_wait_classifier_rejects_invalid_values_and_conflicting_measurement_fields(payload):
    assert live_pending_delay(payload) is None


async def test_long_delay_defers_without_waiting_or_early_read(clock, caplog):
    api = client(ok({"dly": 60000}), ok(SAMPLE))
    with pytest.raises(HoymilesLivePending) as caught:
        await api.async_live(123)
    assert caught.value.retry_after == 60
    assert clock.sleeps == [] and api._json.await_count == 1
    assert api._live_uri == LIVE
    with pytest.raises(HoymilesLivePending):
        await api.async_live(123)
    assert api._json.await_count == 1
    clock.now += 60
    assert await api.async_live(123) == SAMPLE
    assert api._json.await_count == 2
    api._get_live_uri.assert_not_awaited()
    assert "rate_limited" not in caplog.text and SECRET not in caplog.text


async def test_scheduler_cap_does_not_shorten_multiday_deadline(clock):
    api = client(ok({"dly": 3 * 86400000}), ok(SAMPLE))
    for _ in range(3):
        with pytest.raises(HoymilesLivePending) as caught:
            await api.async_live(123)
        assert caught.value.retry_after == 86400
        assert api._json.await_count == 1
        clock.now += 86400
    assert await api.async_live(123) == SAMPLE
    assert api._json.await_count == 2


async def test_signed_long_upper_delay_defers_without_overflow_or_early_read(clock):
    api = client(ok({"dly": 2**63 - 1}))
    for _ in range(2):
        with pytest.raises(HoymilesLivePending) as caught:
            await api.async_live(123)
        assert caught.value.retry_after == 86400
        assert api._json.await_count == 1 and clock.sleeps == []
        clock.now += 86400


async def test_repeated_pending_is_bounded_and_next_read_keeps_deadline(clock):
    api = client(ok({"dly": 5000}), ok({"dly": 5000}), ok(SAMPLE))
    with pytest.raises(HoymilesLivePending) as caught:
        await api.async_live(123)
    assert caught.value.retry_after == 5
    assert clock.sleeps == [5]
    assert api._json.await_count == 2
    assert await api.async_live(123) == SAMPLE
    assert clock.sleeps == [5, 5]
    assert api._json.await_count == 3
    api._get_live_uri.assert_not_awaited()


async def test_sleep_waking_early_does_not_send_early(clock, monkeypatch):
    api = client(ok({"dly": 5000}), ok(SAMPLE))
    async def sleep(seconds):
        clock.sleeps.append(seconds)
        clock.now += min(1, seconds)
    monkeypatch.setattr(api_module, "live_sleep", sleep)
    assert await api.async_live(123) == SAMPLE
    assert clock.sleeps == [5, 4, 3, 2, 1]
    assert api._json.await_count == 2


@pytest.mark.parametrize("failure", [HoymilesAuthError(SECRET), HoymilesRateLimitError(SECRET, 120)])
async def test_errors_after_wait_still_propagate_without_extra_live_retry(clock, failure):
    api = client(ok({"dly": 5000}), failure)
    with pytest.raises(type(failure)):
        await api.async_live(123)
    assert api._json.await_count == 2
    assert api._live_uri is None


async def test_rejected_envelope_never_becomes_pending(clock):
    api = client({"status": "1", "data": {"dly": 5000}}, {"status": "1", "data": {"dly": 5000}})
    with pytest.raises(HoymilesConnectionError) as caught:
        await api.async_live(123)
    assert not isinstance(caught.value, HoymilesLivePending)
    assert clock.sleeps == []
    assert api._json.await_count == 2


async def test_malformed_retry_after_wait_still_warns_and_is_not_hidden(clock, caplog):
    api = client(ok({"dly": 5000}), ok({"dly": 5000, "flow": None}))
    with pytest.raises(HoymilesConnectionError) as caught:
        await api.async_live(123)
    assert not isinstance(caught.value, HoymilesLivePending)
    assert clock.sleeps == [5]
    assert api._json.await_count == 2 and api._live_uri is None
    api._get_live_uri.assert_not_awaited()
    assert "reason=invalid_live_data" in caplog.text and SECRET not in caplog.text


async def test_shared_account_pause_is_enforced_after_wait_without_http_lock(clock, monkeypatch):
    api = client()
    sends = []
    async def request(url, body):
        async with api.runtime.request():
            sends.append((url, body))
            return ok({"dly": 5000})
    api._json = AsyncMock(side_effect=request)
    async def sleep(seconds):
        assert api.runtime._requests._value == 2
        assert not api.runtime._starts.locked()
        clock.now += seconds
        api.runtime.pause(120)
    monkeypatch.setattr(api_module, "live_sleep", sleep)
    with pytest.raises(HoymilesRateLimitError):
        await api.async_live(123)
    assert len(sends) == 1
    api._get_live_uri.assert_not_awaited()


async def test_delay_is_specific_to_client_not_an_account_pause(clock):
    api = client(ok({"dly": 60000}))
    other = client(ok(SAMPLE))
    other.runtime = api.runtime
    with pytest.raises(HoymilesLivePending):
        await api.async_live(123)
    assert await other.async_live(456) == SAMPLE
    assert other.runtime._paused_until == 0


@pytest.mark.parametrize("change", ["station", "profile"])
async def test_new_target_never_reuses_old_uri_or_deadline(clock, change):
    api = client(ok({"dly": 60000}), ok(SAMPLE))
    with pytest.raises(HoymilesLivePending):
        await api.async_live(123)
    if change == "profile":
        api.profile = "installer"
    assert await api.async_live(456 if change == "station" else 123) == SAMPLE
    api._get_live_uri.assert_awaited_once_with(456 if change == "station" else 123)
    assert clock.sleeps == []


async def test_target_changed_during_wait_does_not_send_second_read(clock, monkeypatch):
    api = client(ok({"dly": 5000}), ok(SAMPLE))
    async def sleep(seconds):
        clock.now += seconds
        api._live_uri = "https://neapi.hoymiles.com/replaced"
    monkeypatch.setattr(api_module, "live_sleep", sleep)
    with pytest.raises(HoymilesConnectionError, match="target changed"):
        await api.async_live(123)
    assert api._json.await_count == 1


async def test_changed_uri_during_response_cannot_attach_wait_to_another_target(clock):
    api = client()
    async def response(url, body):
        api._live_uri = "https://neapi.hoymiles.com/replaced"
        return ok({"dly": 5000})
    api._json = AsyncMock(side_effect=response)
    with pytest.raises(HoymilesConnectionError, match="target changed"):
        await api.async_live(123)
    assert api._json.await_count == 1 and clock.sleeps == []
    assert api._live_pending_target is None


async def test_cancelled_wait_never_sends_another_read(clock, monkeypatch):
    api = client(ok({"dly": 5000}), ok(SAMPLE))
    async def sleep(seconds):
        raise asyncio.CancelledError
    monkeypatch.setattr(api_module, "live_sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await api.async_live(123)
    assert api._json.await_count == 1 and not api._live_tasks


async def test_unload_cancels_wait_and_queued_live_call(hass, monkeypatch):
    api = client(ok({"dly": 5000}), ok(SAMPLE))
    entered = asyncio.Event()
    async def sleep(seconds):
        entered.set()
        await asyncio.Event().wait()
    monkeypatch.setattr(api_module, "live_sleep", sleep)
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    first = asyncio.create_task(api.async_live(123))
    await entered.wait()
    queued = asyncio.create_task(api.async_live(123))
    await REAL_SLEEP(0)
    await coordinator.async_shutdown()
    assert first.cancelled() and queued.cancelled()
    assert api._json.await_count == 1 and not api._live_tasks
    with pytest.raises(HoymilesConnectionError, match="stopped"):
        await api.async_live(123)


async def test_pending_coordinator_update_uses_retry_after_and_breaks_energy_integration(hass):
    api = AsyncMock()
    api.async_live.side_effect = HoymilesLivePending(60)
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator._energy_store.async_delay_save = MagicMock()
    now = datetime.now(UTC)
    live = {"con": 1, "brs": 1, "power": {"bat": 1000, "load": 1000}}
    coordinator._update_battery_energy(live, now)
    with pytest.raises(UpdateFailed) as caught:
        await coordinator._async_update_data()
    assert caught.value.retry_after == 60
    result = coordinator._update_battery_energy(live, now + timedelta(seconds=6))
    assert result["charge_wh"] == result["consumption_wh"] == 0
    await coordinator.async_shutdown()


async def test_deferred_refresh_is_unavailable_without_publishing_a_fresh_old_sample(hass):
    api = AsyncMock()
    api.async_live.side_effect = HoymilesLivePending(60)
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    old_data = {"live": SAMPLE}
    coordinator.async_set_updated_data(old_data)
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.data is old_data
    assert isinstance(coordinator.last_exception, UpdateFailed)
    api.async_station_realtime.assert_not_awaited()
    await coordinator.async_shutdown()
