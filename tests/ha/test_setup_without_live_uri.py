"""Independent station setup without inventing unavailable live measurements."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.config_entries import current_entry, ConfigEntryState
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_home import async_setup_entry as real_setup_entry
from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.binary_sensor import HoymilesConnectedSensor
from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError
from custom_components.hoymiles_home.const import DOMAIN, STATION_INTERVAL, LIVE_MIN_INTERVAL
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError
from custom_components.hoymiles_home.sensor import HoymilesStationSensor, STATION_SENSORS, LIVE_SENSOR_KEYS

TREE = [{"id": 99, "type": 3, "model_no": "HMS-2000-4WB"}]
SAMPLE = {"con": 1, "power": {"pv": 42, "bat": 100, "load": 200}, "brs": 2}
MISSING = {"status": 0, "data": {"uri": ""}}


@pytest.fixture(autouse=True)
def setup_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={
        "username": "synthetic@example.invalid", "password": "synthetic", "station_id": 123})
    entry.add_to_hass(hass)
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
    token = current_entry.set(entry)
    yield entry
    current_entry.reset(token)


def client(profile="home"):
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic", profile=profile)
    api._token = "synthetic"
    api._token_expires = datetime.now(UTC) + timedelta(hours=1)
    api._json = AsyncMock(return_value=MISSING)
    api.async_list_stations = AsyncMock(return_value=[{"sid": 123}])
    api.async_device_tree = AsyncMock(return_value=TREE)
    api.async_enrich_inverters = AsyncMock(return_value=TREE)
    api.async_station_realtime = AsyncMock(return_value={"today_eq": 1000, "total_eq": 5000, "pv_power": 99})
    api.async_module_values = AsyncMock(return_value={})
    api.async_battery_settings = AsyncMock(return_value={"readable": False})
    return api


@pytest.mark.parametrize("profile", ["home", "installer"])
async def test_first_refresh_loads_validated_station_without_live_uri(hass, profile):
    api = client(profile)
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    try:
        await coordinator.async_config_entry_first_refresh()
        assert coordinator.last_update_success
        assert coordinator.data["live"] == {}
        assert coordinator.data["live_available"] is False
        assert coordinator.data["station"]["today_eq"] == 1000
        assert coordinator.inverters == TREE
        assert coordinator.update_interval == STATION_INTERVAL
        api.async_list_stations.assert_awaited_once_with()
        api.async_device_tree.assert_awaited_once_with(123)
        api.async_station_realtime.assert_awaited_once_with(123)
        assert api._json.await_count == (4 if profile == "home" else 2)
        entry = SimpleNamespace(entry_id="entry", data={"station_id": 123})
        for description in STATION_SENSORS:
            entity = HoymilesStationSensor(coordinator, entry, description)
            if description.key in LIVE_SENSOR_KEYS | {"load_energy_today", "battery_charge_energy_today", "battery_discharge_energy_today"}:
                assert not entity.available, description.key
            elif description.key == "today_energy":
                assert entity.available
                assert entity.native_value == 1000
        connected = HoymilesConnectedSensor(coordinator, entry)
        assert not connected.available
        assert connected.is_on is None
    finally:
        await coordinator.async_shutdown()


async def test_real_entry_setup_forwards_platforms_after_partial_first_refresh(hass, setup_entry):
    api = client()
    entry = setup_entry
    with (patch("custom_components.hoymiles_home.HoymilesHomeClient", return_value=api),
          patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock()) as forward):
        assert await real_setup_entry(hass, entry)
        forward.assert_awaited_once()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert coordinator.last_update_success
    assert coordinator.data["live_available"] is False
    await coordinator.async_shutdown()


@pytest.mark.parametrize("stations", [[], None, {}, [{"sid": 456}], [{"sid": True}], [{"sid": "123"}]])
async def test_partial_setup_requires_exact_account_station_access(hass, stations):
    api = client()
    api.async_list_stations.return_value = stations
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    try:
        with pytest.raises(ConfigEntryNotReady):
            await coordinator.async_config_entry_first_refresh()
        api.async_device_tree.assert_not_awaited()
        api.async_station_realtime.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("phase", ["live", "validation", "tree", "totals"])
@pytest.mark.parametrize("error,expected", [
    (HoymilesAuthError("authentication"), ConfigEntryAuthFailed),
    (HoymilesRateLimitError("rate", 300), UpdateFailed),
])
async def test_auth_and_rate_failures_never_become_partial_success(hass, phase, error, expected):
    api = client()
    if phase == "live":
        api.async_live = AsyncMock(side_effect=error)
    elif phase == "validation":
        api.async_list_stations.side_effect = error
    elif phase == "tree":
        api.async_device_tree.side_effect = error
    else:
        api.async_station_realtime.side_effect = error
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    try:
        with pytest.raises(expected):
            await coordinator._async_update_data()
        if phase == "live":
            api.async_list_stations.assert_not_awaited()
        if isinstance(error, HoymilesRateLimitError):
            assert not coordinator.last_update_success or coordinator.data is None
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("error", [HoymilesConnectionError("missing_uri"),
    CloudDiagnosticError("invalid_live_data", "invalid"),
    CloudDiagnosticError("untrusted_uri", "blocked"),
    CloudDiagnosticError("http_error", "HTTP failure")])
async def test_only_typed_missing_uri_allows_partial_setup(hass, error):
    api = client()
    api.async_live = AsyncMock(side_effect=error)
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    try:
        with pytest.raises(ConfigEntryNotReady):
            await coordinator.async_config_entry_first_refresh()
        api.async_list_stations.assert_not_awaited()
        api.async_station_realtime.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


async def test_missing_uri_retry_is_bounded_then_live_recovers_automatically(hass, freezer):
    freezer.move_to("2026-11-11 10:00:00+00:00")
    api = client()
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    try:
        await coordinator.async_config_entry_first_refresh()
        first_count = api._json.await_count
        freezer.move_to("2026-11-11 10:00:30+00:00")
        await coordinator.async_refresh()
        assert api._json.await_count == first_count
        assert coordinator.data["live_available"] is False
        freezer.move_to("2026-11-11 10:01:01+00:00")
        await coordinator.async_refresh()
        assert api._json.await_count == first_count * 2
        api.async_list_stations.assert_awaited_once()
        api._json.side_effect = [
            {"status": 0, "data": {"uri": "https://neapi.hoymiles.com/synthetic-live"}},
            {"status": 0, "data": SAMPLE}]
        freezer.move_to("2026-11-11 10:02:02+00:00")
        await coordinator.async_refresh()
        assert coordinator.last_update_success
        assert coordinator.data["live_available"] is True
        assert coordinator.data["live"] == SAMPLE
        assert coordinator.update_interval == LIVE_MIN_INTERVAL
        entry = SimpleNamespace(entry_id="entry", data={"station_id": 123})
        assert HoymilesConnectedSensor(coordinator, entry).available
        assert HoymilesConnectedSensor(coordinator, entry).is_on
    finally:
        await coordinator.async_shutdown()


async def test_lost_uri_discards_old_live_values_and_breaks_energy_integration(hass, freezer):
    freezer.move_to("2026-11-11 10:00:00+00:00")
    api = client()
    api.async_live = AsyncMock(return_value=SAMPLE)
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    try:
        await coordinator.async_config_entry_first_refresh()
        freezer.move_to("2026-11-11 10:00:10+00:00")
        api.async_live.side_effect = CloudDiagnosticError("missing_uri", "no address")
        await coordinator.async_refresh()
        assert coordinator.data["live"] == {}
        assert coordinator.data["live_available"] is False
        assert coordinator._last_battery_sample is None
        assert coordinator._last_load_sample is None
        freezer.move_to("2026-11-11 10:01:11+00:00")
        api.async_live.side_effect = None
        await coordinator.async_refresh()
        assert coordinator.data["battery_energy"]["discharge_wh"] == 0
        assert coordinator.data["battery_energy"]["consumption_wh"] == 0
        freezer.move_to("2026-11-11 10:01:41+00:00")
        await coordinator.async_refresh()
        assert coordinator.data["battery_energy"]["discharge_wh"] == pytest.approx(0.833, abs=0.001)
        assert coordinator.data["battery_energy"]["consumption_wh"] == pytest.approx(1.667, abs=0.001)
    finally:
        await coordinator.async_shutdown()


async def test_partial_station_totals_expire_on_failed_independent_refresh(hass, freezer):
    freezer.move_to("2026-11-11 10:00:00+00:00")
    api = client()
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    try:
        await coordinator.async_config_entry_first_refresh()
        assert coordinator.station_is_fresh("today_energy")
        freezer.move_to("2026-11-11 10:03:00+00:00")
        api.async_station_realtime.side_effect = HoymilesConnectionError("unavailable")
        await coordinator.async_refresh()
        assert coordinator.last_update_success
        assert not coordinator.station_is_fresh("today_energy")
    finally:
        await coordinator.async_shutdown()


async def test_shutdown_cancels_partial_setup_background_work(hass):
    started = asyncio.Event()
    api = client()

    async def slow(*args):
        started.set()
        await asyncio.Event().wait()

    api.async_module_values.side_effect = slow
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    await coordinator.async_config_entry_first_refresh()
    await started.wait()
    task = coordinator.module_polling.task
    await coordinator.async_shutdown()
    assert task.cancelled()


async def test_explicit_valid_offline_sample_retains_offline_semantics(hass):
    api = client()
    api.async_live = AsyncMock(return_value={"con": 0})
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    try:
        await coordinator.async_config_entry_first_refresh()
        assert coordinator.data["live_available"] is True
        entry = SimpleNamespace(entry_id="entry", data={"station_id": 123})
        connected = HoymilesConnectedSensor(coordinator, entry)
        assert connected.available
        assert connected.is_on is False
        api.async_list_stations.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()
