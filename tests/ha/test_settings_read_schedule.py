"""Bound failed read recovery without changing successful polling or writes."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.device_settings import read_retry_delay
from custom_components.hoymiles_home.errors import (
    HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError, HoymilesSettingsError,
)
from custom_components.hoymiles_home.output_power import parse_output_settings

TREE = [{"type": 12, "sn": "ABCDEF000001", "dtu_sn": "ABCDEF000002"}]
LIGHT = {"r": 10, "g": 20, "b": 30, "slb": 128, "slot": 300, "ldb": 128, "sot": 300}


@pytest.fixture
async def settings(hass, freezer):
    freezer.move_to("2026-11-06 12:00:00+00:00")
    api = AsyncMock()
    api.async_heating_settings.return_value = {"enable": 1}
    api.async_light_display_settings.return_value = deepcopy(LIGHT)
    api.async_cutoff_settings.return_value = {"sl": 10, "sh": 100}
    api.async_output_power_settings.return_value = parse_output_settings({"power": 600, "max_power": 800}, [])
    api.async_battery_settings.return_value = {"readable": True}
    coordinator = HoymilesHomeCoordinator(hass, api, 123, device_controls=True, battery_controls=True)
    coordinator.device_tree = deepcopy(TREE)
    try:
        yield coordinator, api, coordinator.device_settings
    finally:
        await coordinator.async_shutdown()


async def test_only_failed_feature_retries_after_completion_and_success_cancels_retry(settings, freezer):
    _, api, manager = settings
    api.async_light_display_settings.side_effect = [CloudDiagnosticError("cloud_rejected", "synthetic"), LIGHT]
    await manager.start()
    regular = manager.next_allowed
    assert manager.available("heating") and not manager.available("lighting")
    assert manager.read_retry_at == {"lighting": datetime.now(UTC) + timedelta(seconds=60)}
    freezer.tick(timedelta(seconds=59))
    assert manager.start() is None
    freezer.tick(timedelta(seconds=1))
    await manager.start()
    assert manager.next_allowed == regular
    assert manager.available("lighting")
    assert manager.read_retry_at == {} and manager.read_retry_count == {}
    api.async_heating_settings.assert_awaited_once()
    assert api.async_light_display_settings.await_count == 2
    assert manager.start() is None
    api.async_write_light_display_settings.assert_not_awaited()


async def test_two_retries_then_regular_thirty_minute_cycle(settings, freezer):
    _, api, manager = settings
    api.async_light_display_settings.side_effect = HoymilesConnectionError("synthetic")
    await manager.start()
    regular = manager.next_allowed
    freezer.tick(timedelta(minutes=1))
    await manager.start()
    assert manager.read_retry_at["lighting"] == datetime.now(UTC) + timedelta(minutes=3)
    freezer.tick(timedelta(seconds=179))
    assert manager.start() is None
    freezer.tick(timedelta(seconds=1))
    await manager.start()
    assert manager.read_retry_at == {}
    assert api.async_light_display_settings.await_count == 3
    assert manager.next_allowed == regular
    freezer.move_to(regular - timedelta(seconds=1))
    assert manager.start() is None
    freezer.tick(timedelta(seconds=1))
    await manager.start()
    assert api.async_light_display_settings.await_count == 4
    assert api.async_heating_settings.await_count == 2
    assert manager.read_retry_at["lighting"] == datetime.now(UTC) + timedelta(minutes=1)


async def test_retry_wait_is_from_failure_completion_not_request_start(settings, freezer):
    _, api, manager = settings
    async def slow_failure(*args):
        freezer.tick(timedelta(seconds=40))
        raise HoymilesConnectionError("synthetic")
    api.async_light_display_settings.side_effect = slow_failure
    await manager.start()
    assert manager.read_retry_at["lighting"] == manager.last_attempt + timedelta(seconds=100)


@pytest.mark.parametrize("error", [
    HoymilesAuthError("synthetic"), HoymilesRateLimitError("synthetic", 3600),
    HoymilesSettingsError("invalid_lighting", "synthetic"),
    CloudDiagnosticError("redirect_rejected", "synthetic"),
    CloudDiagnosticError("http_error", "synthetic"),
])
async def test_auth_rate_structural_and_unsafe_errors_do_not_accelerate_reads(settings, freezer, error):
    _, api, manager = settings
    api.async_heating_settings.side_effect = error
    await manager.start()
    assert manager.read_retry_at == {}
    freezer.tick(timedelta(minutes=5))
    assert manager.start() is None
    api.async_heating_settings.assert_awaited_once()
    if isinstance(error, HoymilesRateLimitError):
        freezer.tick(timedelta(minutes=30))
        assert manager.start() is None
        assert await manager.async_refresh() is False


@pytest.mark.parametrize("change", ["permission", "unload", "ambiguous_target"])
async def test_retry_revalidates_permission_unload_and_target(settings, freezer, change):
    coordinator, api, manager = settings
    api.async_light_display_settings.side_effect = HoymilesConnectionError("synthetic")
    await manager.start()
    if change == "permission":
        coordinator.device_controls = False
    elif change == "unload":
        await manager.async_shutdown()
    else:
        coordinator.device_tree.append({"type": 12, "sn": "ABCDEF000003"})
    freezer.tick(timedelta(minutes=1))
    task = manager.start()
    if task is not None:
        await task
    api.async_light_display_settings.assert_awaited_once()


async def test_inflight_retry_coalesces_with_manual_refresh(settings, freezer):
    _, api, manager = settings
    api.async_light_display_settings.side_effect = HoymilesConnectionError("synthetic")
    await manager.start()
    started, finish = asyncio.Event(), asyncio.Event()
    async def recover(*args):
        started.set()
        await finish.wait()
        return deepcopy(LIGHT)
    api.async_light_display_settings.side_effect = recover
    freezer.tick(timedelta(minutes=1))
    task = manager.start()
    await started.wait()
    manual = asyncio.create_task(manager.async_refresh())
    await asyncio.sleep(0)
    finish.set()
    await task
    assert await manual is True
    assert api.async_light_display_settings.await_count == 2
    api.async_heating_settings.assert_awaited_once()
    assert await manager.async_refresh() is False


async def test_read_recovery_never_repeats_a_failed_write(settings, freezer):
    _, api, manager = settings
    await manager.start()
    api.async_write_heating_settings.side_effect = HoymilesConnectionError("synthetic")
    api.async_heating_settings.return_value = {"enable": 0}
    with pytest.raises(HoymilesConnectionError):
        await manager.async_set_heating(True)
    assert manager.read_retry_at == {}
    freezer.tick(timedelta(minutes=5))
    assert manager.start() is None
    api.async_write_heating_settings.assert_awaited_once()


async def test_whole_read_timeout_does_not_disable_already_successful_feature(settings):
    _, api, manager = settings
    async def pending(*args):
        await asyncio.Event().wait()
    api.async_light_display_settings.side_effect = pending
    real_timeout = asyncio.timeout
    with patch("custom_components.hoymiles_home.device_settings.asyncio.timeout",
               side_effect=lambda _: real_timeout(0)):
        await manager.start()
    assert manager.available("heating")
    assert manager.status["lighting"] == "unavailable"
    assert set(manager.read_retry_at) == {"lighting"}


@pytest.mark.parametrize("attribute,read_method", [
    ("cutoff_settings", "async_cutoff_settings"),
    ("output_settings", "async_output_power_settings"),
])
async def test_cutoffs_and_output_share_bounded_read_recovery(settings, freezer, attribute, read_method):
    coordinator, api, _ = settings
    manager = getattr(coordinator, attribute)
    method = getattr(api, read_method)
    recovered = deepcopy(method.return_value)
    method.side_effect = [HoymilesConnectionError("synthetic"), recovered]
    await manager.start()
    assert manager.read_retry_at
    freezer.tick(timedelta(minutes=1))
    await manager.start()
    assert not manager.read_retry_at
    assert method.await_count == 2
    assert all(state == "readable" for state in manager.status.values())


async def test_battery_mode_reads_retry_on_live_tick_then_reset_on_success(settings, freezer):
    coordinator, api, _ = settings
    api.async_live.return_value = {"con": 0, "dly": 3000}
    api.async_station_realtime.return_value = {}
    api.async_battery_settings.side_effect = [HoymilesConnectionError("synthetic"), {"readable": True}]
    await coordinator._async_update_data()
    await coordinator._battery_settings_task
    assert coordinator._battery_read_retry_at == datetime.now(UTC) + timedelta(minutes=1)
    freezer.tick(timedelta(seconds=59))
    await coordinator._async_update_data()
    api.async_battery_settings.assert_awaited_once()
    freezer.tick(timedelta(seconds=1))
    await coordinator._async_update_data()
    await coordinator._battery_settings_task
    assert api.async_battery_settings.await_count == 2
    assert coordinator._battery_read_retry_at is None
    assert coordinator._battery_read_retry_count == 0
    assert coordinator.battery_settings["readable"] is True


async def test_battery_mode_retry_cap_and_server_pause(settings, freezer):
    coordinator, api, _ = settings
    api.async_battery_settings.side_effect = HoymilesConnectionError("synthetic")
    await coordinator._start_battery_settings_refresh()
    for delay in (60, 180):
        freezer.tick(timedelta(seconds=delay))
        await coordinator._start_battery_settings_refresh(retry=True)
    assert coordinator._battery_read_retry_at is None
    assert api.async_battery_settings.await_count == 3
    api.async_battery_settings.side_effect = HoymilesRateLimitError("synthetic", 7200)
    await coordinator._start_battery_settings_refresh()
    assert coordinator._battery_read_retry_at is None
    freezer.tick(timedelta(minutes=31))
    assert await coordinator.async_refresh_battery_settings() is False
    assert coordinator._start_battery_settings_refresh(retry=True) is None
    await coordinator.async_shutdown()
    assert coordinator._start_battery_settings_refresh(retry=True) is None


def test_read_retry_policy_has_no_unbounded_or_write_retry_branch():
    error = HoymilesConnectionError("synthetic")
    assert read_retry_delay(error, 0) == timedelta(minutes=1)
    assert read_retry_delay(error, 1) == timedelta(minutes=3)
    assert read_retry_delay(error, 2) is None
