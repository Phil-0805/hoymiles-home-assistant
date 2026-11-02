"""Shared credentials, pacing, concurrency, cooldown and server backoff."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientResponseError

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.cloud_runtime import AccountPool, AccountRuntime, retry_delay
from custom_components.hoymiles_home.errors import HoymilesRateLimitError
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.button import HoymilesRefreshBatterySettingsButton
from homeassistant.exceptions import HomeAssistantError
from custom_components.hoymiles_home import async_setup_entry as real_setup_entry
from custom_components.hoymiles_home.const import DOMAIN
from pytest_homeassistant_custom_component.common import MockConfigEntry


def test_identical_accounts_share_budget_until_last_entry_unloads():
    pool = AccountPool()
    key, one = pool.acquire("Test@example.com", "secret")
    key2, two = pool.acquire("test@example.com", "secret")
    _, other = pool.acquire("other@example.com", "secret")
    assert key == key2 and one is two and one is not other
    assert "secret" not in key and "example" not in key
    pool.release(key)
    assert key in pool._accounts
    pool.release(key)
    assert key not in pool._accounts


async def test_multiple_station_clients_share_one_login():
    runtime = AccountRuntime()
    clients = [HoymilesHomeClient(MagicMock(), "test@example.com", "secret", runtime) for _ in range(3)]
    async def login():
        await asyncio.sleep(0)
        runtime.token = "TOKEN"
        runtime.token_expires = datetime.now(UTC) + timedelta(hours=1)
    method = AsyncMock(side_effect=login)
    for client in clients:
        client._async_login_unlocked = method
    await asyncio.gather(*(client.async_ensure_login() for client in clients))
    method.assert_awaited_once()
    assert all(client._token == "TOKEN" for client in clients)
    clients[0]._live_uri = "https://neapi.hoymiles.com/one"
    assert clients[1]._live_uri is None


async def test_budget_spaces_starts_and_limits_concurrency():
    runtime = AccountRuntime()
    clock = [100.0]
    original_sleep = asyncio.sleep
    starts, active, peak = [], 0, 0
    async def sleep(delay):
        clock[0] += delay
        await original_sleep(0)
    async def request():
        nonlocal active, peak
        async with runtime.request():
            starts.append(clock[0])
            active += 1
            peak = max(peak, active)
            await original_sleep(0)
            active -= 1
    with patch("custom_components.hoymiles_home.cloud_runtime.monotonic", side_effect=lambda: clock[0]), patch("custom_components.hoymiles_home.cloud_runtime.asyncio.sleep", side_effect=sleep):
        await asyncio.gather(*(request() for _ in range(8)))
    assert all(b - a >= 1 for a, b in zip(starts, starts[1:]))
    assert peak <= 2


async def test_server_limit_pauses_other_station_before_http_request():
    runtime = AccountRuntime()
    one = HoymilesHomeClient(MagicMock(), "test@example.com", "secret", runtime)
    two = HoymilesHomeClient(MagicMock(), "test@example.com", "secret", runtime)
    response = MagicMock(status=429)
    response.raise_for_status.side_effect = ClientResponseError(
        SimpleNamespace(real_url="https://neapi.hoymiles.com/test"), (), status=429,
        headers={"Retry-After": "120"},
    )
    one._session.post.return_value.__aenter__.return_value = response
    with pytest.raises(HoymilesRateLimitError):
        await one._json("https://neapi.hoymiles.com/test", {})
    with pytest.raises(HoymilesRateLimitError):
        await two._json("https://neapi.hoymiles.com/other", {})
    two._session.post.assert_not_called()


async def test_button_cooldown_avoids_additional_cloud_reads(hass):
    api = AsyncMock()
    api.async_battery_settings.return_value = {"readable": True}
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    entry = SimpleNamespace(entry_id="test", data={"station_id": 123})
    button = HoymilesRefreshBatterySettingsButton(coordinator, entry)
    await button.async_press()
    with pytest.raises(HomeAssistantError):
        await button.async_press()
    api.async_battery_settings.assert_awaited_once()
    await coordinator.async_shutdown()


def test_retry_after_http_date_and_bad_values(freezer):
    freezer.move_to("2026-10-29 10:00:00+00:00")
    assert retry_delay("Thu, 29 Oct 2026 10:02:00 GMT") == 120
    assert retry_delay("invalid") == 60
    assert retry_delay("nan") == 60
    assert retry_delay("0") == 60


@pytest.mark.parametrize("constructor_failure", [False, True])
async def test_failed_setup_releases_shared_account(hass, constructor_failure):
    entry = MockConfigEntry(domain=DOMAIN, data={"username": "test@example.com", "password": "secret", "station_id": 123})
    entry.add_to_hass(hass)
    coordinator = SimpleNamespace(
        async_initialize=AsyncMock(),
        async_config_entry_first_refresh=AsyncMock(side_effect=RuntimeError("failed setup")),
        async_shutdown=AsyncMock(),
    )
    with patch("custom_components.hoymiles_home.HoymilesHomeCoordinator", return_value=coordinator,
               side_effect=RuntimeError("failed constructor") if constructor_failure else None):
        with pytest.raises(RuntimeError):
            await real_setup_entry(hass, entry)
    assert not hass.data[DOMAIN]["_accounts"]._accounts
    assert entry.entry_id not in hass.data[DOMAIN]
    if not constructor_failure:
        coordinator.async_shutdown.assert_awaited_once()
