"""Manufacturer-backed sampleless startup and read-only PV capability guards."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.config_entries import current_entry, ConfigEntryState
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError
from custom_components.hoymiles_home.const import DOMAIN, STATION_INTERVAL, LIVE_MIN_INTERVAL
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.diagnostics import async_get_config_entry_diagnostics
from custom_components.hoymiles_home.errors import HoymilesConnectionError, HoymilesAuthError, HoymilesRateLimitError
from custom_components.hoymiles_home.inverter import pv_only_topology, standalone_hms_target
from custom_components.hoymiles_home.sensor import HoymilesStationSensor, STATION_SENSORS

URI = "https://neapi.hoymiles.com/synthetic-live"
TREE = [{"id": 99, "type": 3}]
SAMPLE = {"con": 1, "power": {"pv": 42, "load": 200}}


def envelope(data):
    return {"status": "0", "data": data}


def api_client(*replies, profile="home"):
    api = HoymilesHomeClient(MagicMock(), "synthetic@example.invalid", "synthetic", profile=profile)
    api._token = "synthetic"
    api._token_expires = datetime.now(UTC) + timedelta(hours=1)
    api._live_uri = URI
    api._json = AsyncMock(side_effect=replies)
    return api


def coordinator(hass, api, *, rows=None):
    api.async_list_stations = AsyncMock(return_value=rows if rows is not None else [{"sid": 123}])
    api.async_device_tree = AsyncMock(return_value=deepcopy(TREE))
    api.async_enrich_inverters = AsyncMock(side_effect=lambda sid, nodes: nodes)
    api.async_station_realtime = AsyncMock(return_value={"today_eq": 100})
    api.async_module_values = AsyncMock(return_value={})
    api.async_battery_settings = AsyncMock(return_value={"readable": False})
    c = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    for manager in (c.module_polling, c.battery_telemetry, c.device_settings,
                    c.cutoff_settings, c.output_settings):
        manager.start = MagicMock()
    return c


@pytest.fixture(autouse=True)
def entry_context(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"station_id": 123})
    entry.add_to_hass(hass)
    entry._async_set_state(hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
    token = current_entry.set(entry)
    yield entry
    current_entry.reset(token)


@pytest.mark.parametrize("sampleless", [{}, {"dly": 0}, {"dly": 5000}, {"dly": 2**63 - 1}])
async def test_sampleless_home_replies_allow_real_first_refresh_but_no_measurements(hass, sampleless):
    api = api_client(envelope(sampleless), envelope({"uri": URI}), envelope(sampleless))
    c = coordinator(hass, api, rows=[{"sid": 123, "battery_capability": "pv_without_battery"}])
    try:
        await c.async_config_entry_first_refresh()
        assert c.last_update_success
        assert c.data["live"] == {}
        assert not c.data["live_available"]
        assert c.data["station"]["today_eq"] == 100
        assert c.update_interval == STATION_INTERVAL
        assert api._json.await_count == 3  # Same bounded live/URI/live sequence.
        api.async_list_stations.assert_awaited_once()  # Reuse access validation.
        api.async_battery_settings.assert_not_awaited()
        c.battery_telemetry.start.assert_not_called()
        assert not c.battery_reads_applicable
        assert c.battery_read_applicability_reason == "station_pv_without_battery"
        assert standalone_hms_target(c.device_tree, c.inverters) is None
        assert c.output_settings.target is None  # No new control authorization.
        desc = next(d for d in STATION_SENSORS if d.key == "pv_power")
        entity = HoymilesStationSensor(c, SimpleNamespace(entry_id="test", data={"station_id":123}), desc)
        assert not entity.available
        assert entity.native_value is None
    finally:
        await c.async_shutdown()


async def test_partial_polling_is_bounded_and_diagnostics_contain_only_fixed_status(hass, freezer):
    freezer.move_to("2026-11-18 00:00:00+00:00")
    api = api_client()
    api.async_live = AsyncMock(side_effect=CloudDiagnosticError("live_no_measurements", "synthetic"))
    c = coordinator(hass, api, rows=[{"sid":123,"battery_capability":"pv_without_battery"}])
    hass.data.setdefault(DOMAIN, {})["synthetic"] = c
    try:
        await c.async_refresh()
        freezer.tick(3)
        await c.async_refresh()
        assert api.async_live.await_count == 1
        freezer.tick(57)
        await c.async_refresh()
        assert api.async_live.await_count == 2
        diag = await async_get_config_entry_diagnostics(hass, SimpleNamespace(entry_id="synthetic"))
        assert diag["polling"]["live_unavailable_reason"] == "live_no_measurements"
        assert diag["polling"]["battery_read_applicability_reason"] == "station_pv_without_battery"
        assert diag["battery_telemetry"]["applicable"] is False
        c._live_unavailable_reason = "PRIVATE"
        diag = await async_get_config_entry_diagnostics(hass, SimpleNamespace(entry_id="synthetic"))
        assert "PRIVATE" not in repr(diag)
    finally:
        await c.async_shutdown()


@pytest.mark.parametrize("invalid", [None, [], {"con": None}, {"con": True}, {"flow": None},
    {"power": None}, {"dly": True}, {"dly": "5000"}, {"dly": -1}, {"dly": 2**63},
    {"error": "private"}, {"dly": 5000, "unknown": 1}])
async def test_malformed_samples_still_block_setup(hass, invalid):
    api = api_client(envelope(invalid), envelope({"uri": URI}), envelope(invalid))
    c = coordinator(hass, api)
    try:
        with pytest.raises(ConfigEntryNotReady):
            await c.async_config_entry_first_refresh()
        api.async_list_stations.assert_not_awaited()
        api.async_device_tree.assert_not_awaited()
    finally:
        await c.async_shutdown()


@pytest.mark.parametrize("profile", ["installer", "enduser"])
async def test_sampleless_change_does_not_apply_to_other_profiles(profile):
    api = api_client(envelope({}), envelope({"uri": URI}), envelope({}), profile=profile)
    if profile == "enduser":
        api._async_enduser_classification = AsyncMock(return_value=1)
        api._live_station_id = 123
    with pytest.raises(CloudDiagnosticError) as exc:
        await api.async_live(123)
    assert exc.value.reason == "invalid_live_data"


async def test_a_malformed_reply_is_not_hidden_by_a_second_empty_reply():
    api = api_client(envelope({"con": None}), envelope({"uri": URI}), envelope({}))
    with pytest.raises(CloudDiagnosticError) as exc:
        await api.async_live(123)
    assert exc.value.reason == "invalid_live_data"


@pytest.mark.parametrize("rows", [[], [{"sid":456}], [{"sid":"123"}], [{"sid":True}]])
async def test_sampleless_setup_requires_exact_independent_station_access(hass, rows):
    api = api_client(envelope({}), envelope({"uri":URI}), envelope({}))
    c = coordinator(hass, api, rows=rows)
    try:
        with pytest.raises(ConfigEntryNotReady):
            await c.async_config_entry_first_refresh()
        api.async_device_tree.assert_not_awaited()
    finally:
        await c.async_shutdown()


async def test_daylight_recovers_existing_entry_and_does_not_integrate_across_gap(hass, freezer):
    freezer.move_to("2026-11-18 00:00:00+00:00")
    api = api_client()
    api.async_live = AsyncMock(side_effect=[SAMPLE, CloudDiagnosticError("live_no_measurements", "synthetic"), SAMPLE, SAMPLE])
    c = coordinator(hass, api)
    try:
        await c.async_refresh()
        freezer.tick(3)
        await c.async_refresh()
        assert c.last_update_success and not c.data["live_available"]
        freezer.tick(3600)
        await c.async_refresh()
        assert c.data["live"] == SAMPLE and c.data["live_available"]
        assert c.update_interval == LIVE_MIN_INTERVAL
        assert c.data["battery_energy"]["consumption_wh"] == 0
        freezer.tick(3)
        await c.async_refresh()
        assert c.data["battery_energy"]["consumption_wh"] == pytest.approx(0.167, abs=0.001)
    finally:
        await c.async_shutdown()


@pytest.mark.parametrize("row,skip", [
    ({"id":123,"classify":1,"bt":0}, True),
    ({"sid":123,"classify":1,"bt":0}, True),
    ({"sid":123,"classify":1}, False),
    ({"sid":123,"bt":0}, False),
    ({"sid":123,"classify":True,"bt":0}, False),
    ({"sid":123,"classify":"1","bt":0}, False),
    ({"sid":123,"classify":1,"bt":False}, False),
    ({"sid":123,"classify":1,"bt":"0"}, False),
    ({"sid":123,"classify":1,"bt":1}, False),
    ({"sid":123,"classify":10,"bt":0}, False),
    ({"sid":123,"classify":11,"bt":0}, False),
])
async def test_exact_home_station_capability_is_normalized_without_private_values(row, skip):
    api = api_client(envelope({"list":[{**row,"private":"SECRET"}]}))
    stations = await api.async_list_stations()
    assert (stations[0].get("battery_capability") == "pv_without_battery") is skip
    assert "SECRET" not in repr(stations)


async def test_duplicate_station_rows_cannot_authorize_battery_suppression():
    api = api_client(envelope({"list":[{"sid":123,"classify":1,"bt":1},
                                        {"sid":123,"classify":1,"bt":0}]}))
    assert "battery_capability" not in (await api.async_list_stations())[0]


@pytest.mark.parametrize("tree", [[], {}, [None], [{"id":99,"type":12}],
    [{"id":99,"type":True}], [{"id":True,"type":3}],
    [{"id":99,"type":3,"children":{}}], TREE+TREE,
    [{"id":99,"type":3,"metadata":{"type":12}}]])
def test_unknown_or_conflicting_topology_never_proves_pv_only(tree):
    assert not pv_only_topology(tree)


async def test_capability_is_read_once_and_invalidated_by_station_or_tree_change(hass):
    api = api_client()
    api.async_live = AsyncMock(return_value=SAMPLE)
    c = coordinator(hass, api, rows=[{"sid":123,"battery_capability":"pv_without_battery"}])
    try:
        await c.async_refresh()
        await c.async_refresh()
        assert not c.battery_reads_applicable
        api.async_list_stations.assert_awaited_once()
        with pytest.raises(HoymilesConnectionError, match="not applicable"):
            c._check_battery_controls()
        c.device_tree = [{"id":99,"type":3},{"id":100,"type":12}]
        assert c.battery_reads_applicable
        c.device_tree = TREE
        c.station_id = 456
        assert c.battery_reads_applicable
    finally:
        await c.async_shutdown()


@pytest.mark.parametrize("change", ["station", "tree", "unload"])
async def test_capability_result_is_discarded_after_concurrent_target_change(hass, change):
    api = api_client()
    c = coordinator(hass, api)
    c.device_tree = deepcopy(TREE)
    started, release = asyncio.Event(), asyncio.Event()
    async def rows():
        started.set()
        await release.wait()
        return [{"sid":123,"battery_capability":"pv_without_battery"}]
    api.async_list_stations.side_effect = rows
    task = asyncio.create_task(c._async_check_battery_capability())
    await started.wait()
    if change == "station": c.station_id = 456
    elif change == "tree": c.device_tree = [{"id":100,"type":3}]
    else: await c.async_shutdown()
    release.set()
    await task
    assert c._battery_capability_context is None
    await c.async_shutdown()


@pytest.mark.parametrize("error", [HoymilesAuthError("synthetic"), HoymilesRateLimitError("synthetic", 300)])
async def test_capability_auth_and_rate_errors_do_not_fall_through_to_battery_probes(hass, error):
    api = api_client()
    api.async_live = AsyncMock(return_value=SAMPLE)
    c = coordinator(hass, api)
    api.async_list_stations.side_effect = error
    try:
        await c.async_refresh()
        assert not c.last_update_success
        api.async_battery_settings.assert_not_awaited()
    finally:
        await c.async_shutdown()
