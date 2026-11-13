"""Do not turn b4's successful live URI recovery into a pending-data outage."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesConnectionError

OLD = "https://neapi.hoymiles.com/synthetic-old"
NEW = "https://neapi.hoymiles.com/synthetic-new"
BASE = "https://neapi.hoymiles.com"
SAMPLE = {"flow": [], "con": 1, "power": {"pv": 42}}


def ok(data):
    return {"status": "0", "data": data}


def client(*responses, profile="home"):
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic", profile=profile)
    api._token = "synthetic"
    api._token_expires = datetime.now(UTC) + timedelta(hours=1)
    api._live_uri = OLD
    api._json = AsyncMock(side_effect=responses)
    api.async_device_tree = AsyncMock(return_value=[])
    api.async_enrich_inverters = AsyncMock(return_value=[])
    api.async_station_realtime = AsyncMock(return_value={})
    api.async_battery_settings = AsyncMock(return_value={"readable": False})
    return api


@pytest.mark.parametrize("delay", [0, 5000, 60000, 3 * 86400000, 2**63 - 1])
@pytest.mark.parametrize("profile", ["home", "installer"])
async def test_wait_reply_recovers_via_uri_and_keeps_real_ha_refresh_available(hass, caplog, delay, profile):
    caplog.set_level(logging.INFO)
    api = client(ok({"dly": delay}), ok({"uri": NEW}), ok(SAMPLE), profile=profile)
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.async_set_updated_data({"live": {"con": 1, "power": {"pv": 12}}})
    await asyncio.wait_for(coordinator.async_refresh(), timeout=1)
    assert coordinator.last_update_success
    assert coordinator.data["live"] == SAMPLE
    assert "Cloud live retry recovered" in caplog.text
    assert "Cloud request failed: stage=live_data" not in caplog.text
    assert "Cloud request recovered: stage=live_data" not in caplog.text
    body = {"sid": 123, "m": 0} if profile == "home" else {"m": 0, "t": 1}
    path = "/pvmc/api/0/station/get_sd_uri_c" if profile == "home" else "/pvm/api/0/station/get_sd_uri"
    assert [c.args for c in api._json.call_args_list] == [
        (OLD, body), (BASE + path, {"sid": 123}), (NEW, body),
    ]
    await coordinator.async_shutdown()


async def test_recurring_wait_replies_do_not_accumulate_a_stuck_deadline(hass):
    api = client(*[reply for _ in range(3) for reply in (
        ok({"dly": 60000}), ok({"uri": NEW}), ok(SAMPLE),
    )])
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    for _ in range(3):
        await asyncio.wait_for(coordinator.async_refresh(), timeout=1)
        assert coordinator.last_update_success
        assert coordinator.data["live"] == SAMPLE
    assert api._json.await_count == 9
    await coordinator.async_shutdown()


async def test_missing_telemetry_after_both_attempts_still_becomes_unavailable(hass, caplog):
    api = client(ok({"dly": 60000}), ok({"uri": NEW}), ok({"dly": 60000}))
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    old_data = {"live": {"con": 1, "power": {"pv": 12}}}
    coordinator.async_set_updated_data(old_data)
    await asyncio.wait_for(coordinator.async_refresh(), timeout=1)
    assert not coordinator.last_update_success
    assert coordinator.data is old_data
    assert "no usable telemetry after retry" in str(coordinator.last_exception)
    assert api._json.await_count == 3
    assert caplog.text.count("reason=invalid_live_data") == 1
    assert "Cloud live retry recovered" not in caplog.text
    api.async_station_realtime.assert_not_awaited()
    await coordinator.async_shutdown()


@pytest.mark.parametrize("payload", [
    {}, {"dly": -1}, {"dly": True}, {"dly": "5000"}, {"dly": 2**63},
    {"dly": 5000, "power": None}, {"dly": 5000, "con": None},
])
async def test_other_invalid_samples_keep_existing_warning_path(payload, caplog):
    api = client(ok(payload), ok({"uri": NEW}), ok(SAMPLE))
    assert await api.async_live(123) == SAMPLE
    assert "reason=invalid_live_data" in caplog.text
    assert "Cloud request recovered: stage=live_data" in caplog.text
    assert "Cloud live retry recovered" not in caplog.text


async def test_real_failure_episode_still_reports_recovery_after_a_delay_hint(caplog):
    api = client(ok({}), ok({"uri": NEW}), ok({}),
                 ok({"uri": NEW}), ok({"dly": 5000}), ok({"uri": NEW}), ok(SAMPLE))
    with pytest.raises(HoymilesConnectionError):
        await api.async_live(123)
    assert await api.async_live(123) == SAMPLE
    assert caplog.text.count("Cloud request failed: stage=live_data reason=invalid_live_data") == 1
    assert "recovery_scope=later_refresh" in caplog.text
