"""Only optional standalone output reads pause; fresh-write guards stay intact."""

import asyncio
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.diagnostics import _output_power_diagnostics
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from custom_components.hoymiles_home.output_power import parse_output_settings
from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError
from custom_components.hoymiles_home.button import HoymilesRefreshOutputPowerButton

HMS = [{"type":3,"id":99,"model_no":"HMS-2000-4WB"}]
STORAGE = [{"type":12,"sn":"ABCDEF000001","dtu_sn":"ABCDEF000002"}]
SETTINGS = parse_output_settings({"power":600,"max_power":2000}, [])


@pytest.fixture
async def system(hass, freezer):
    freezer.move_to("2026-11-19 12:00:00+00:00")
    api = AsyncMock()
    api.profile = "home"
    api.supports_home_features = True
    api.async_output_power_settings.return_value = deepcopy(SETTINGS)
    api.async_device_tree.return_value = deepcopy(HMS)
    api.async_enrich_inverters.side_effect = lambda sid, tree: tree
    api.async_station_realtime.return_value = {}
    c = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    c.device_tree = deepcopy(HMS)
    c.inverters = deepcopy(HMS)
    for manager in (c.module_polling,c.battery_telemetry,c.device_settings,c.cutoff_settings):
        manager.start = MagicMock()
    await c.output_settings._async_refresh()
    api.reset_mock()
    yield c,api,c.output_settings
    await c.async_shutdown()


@pytest.mark.parametrize("state", ["offline","unavailable"])
async def test_pause_keeps_confirmed_value_and_age_without_cloud_requests(system, freezer, state):
    c,api,m = system
    stamp = m.updated["output_power"]
    deadline = m.next_allowed
    c._output_live_context = (123,state)
    if state == "unavailable":
        api.async_output_power_settings.side_effect = CloudDiagnosticError("cloud_rejected","synthetic")
        await m._async_refresh()
        api.async_output_power_settings.assert_awaited_once()
        api.reset_mock()
        api.async_output_power_settings.side_effect = None
    freezer.tick(3600)
    for _ in range(4):
        assert m.start() is None
    assert not await m.async_refresh()
    assert m.status["output_power"] == "waiting_for_live"
    assert m.updated["output_power"] == stamp
    assert m.next_allowed == deadline
    assert m.output == SETTINGS
    assert m.display_status() == "last_confirmed"
    diag = _output_power_diagnostics(m)
    assert diag["polling_paused"] is True
    assert diag["last_confirmed_age_seconds"] == 3600
    api.async_output_power_settings.assert_not_awaited()
    api.async_write_output_power_settings.assert_not_awaited()


async def test_recovery_reuses_normal_deadline_and_then_reads_fresh_settings(system, freezer):
    c,api,m = system
    c._output_live_context = (123,"offline")
    m.next_allowed = datetime.now(UTC)+timedelta(minutes=5)
    assert m.start() is None
    c._output_live_context = (123,"available")
    freezer.tick(30)
    assert m.start() is None
    api.async_output_power_settings.assert_not_awaited()
    freezer.tick(270)
    task = m.start()
    assert task is not None
    assert m.start() is None  # The next regular deadline prevents another read.
    await task
    assert m.status["output_power"] == "readable"
    assert m.display_status() == "current"
    api.async_output_power_settings.assert_awaited_once_with(123)


async def test_pause_is_rechecked_under_lock_before_a_queued_read(system):
    c,api,m = system
    c._output_live_context = (123,"available")
    await m.lock.acquire()
    task = m.start()
    await asyncio.sleep(0)
    c._output_live_context = (123,"offline")
    m.lock.release()
    await task
    assert m.status["output_power"] == "waiting_for_live"
    api.async_output_power_settings.assert_not_awaited()


@pytest.mark.parametrize("tree,state", [(STORAGE,"offline"), (STORAGE,"unavailable"),
    (HMS,"available"), (HMS,"unavailable"), (HMS,None)])
async def test_storage_or_legacy_unknown_state_does_not_gain_a_night_heuristic(system, tree, state):
    c,api,m = system
    c.device_tree = deepcopy(tree)
    c._output_live_context = (123,state)
    task = m.start()
    assert task is not None
    await task
    api.async_output_power_settings.assert_awaited_once()
    assert m.status["output_power"] == "readable"


@pytest.mark.parametrize("mutation", ["permission","disabled","unload","station","tree"])
async def test_target_permission_and_unload_do_not_reuse_paused_authority(system, mutation):
    c,api,m = system
    c._output_live_context = (123,"offline")
    m.start()
    if mutation == "permission": c.battery_controls = False
    elif mutation == "disabled": m.enabled = False
    elif mutation == "unload": await c.async_shutdown()
    elif mutation == "station":
        c.station_id = 456
        m.station_id = 456
    else: c.device_tree = [{"type":3,"id":100}]
    if mutation in {"permission","disabled","unload"}:
        assert m.start() is None
    else:
        assert not m.polling_paused
    assert m.display_status() == "unavailable"
    api.async_write_output_power_settings.assert_not_awaited()


@pytest.mark.parametrize("failure", ["reject","lower_limit"])
async def test_user_write_still_requires_fresh_read_and_never_uses_retained_limit(system, failure):
    c,api,m = system
    c._output_live_context = (123,"offline")
    m.start()
    if failure == "reject":
        api.async_output_power_settings.side_effect = HoymilesConnectionError("synthetic")
    else:
        api.async_output_power_settings.return_value = parse_output_settings({"power":600,"max_power":800}, [])
    with pytest.raises(HoymilesConnectionError):
        await m.async_set_power(900)
    api.async_output_power_settings.assert_awaited_once()
    api.async_write_output_power_settings.assert_not_awaited()


@pytest.mark.parametrize("missing", [False,True])
async def test_coordinator_uses_current_live_result_and_recovers_without_reload(system, freezer, missing):
    c,api,m = system
    api.async_live.return_value = {"con":1,"power":{"pv":0}}
    await c.async_refresh()
    if m.task: await m.task
    api.reset_mock()
    if missing:
        api.async_live.side_effect = CloudDiagnosticError("missing_uri","synthetic")
        api.async_list_stations.return_value = [{"sid":123}]
        api.async_output_power_settings.side_effect = CloudDiagnosticError("cloud_rejected","synthetic")
    else:
        api.async_live.return_value = {"con":0}
    freezer.tick(1900)
    await c.async_refresh()
    if m.task: await m.task
    assert c.last_update_success
    if missing:
        api.async_output_power_settings.assert_awaited_once()
        api.reset_mock()
        freezer.tick(60)
        await c.async_refresh()
    assert m.status["output_power"] == "waiting_for_live"
    api.async_output_power_settings.assert_not_awaited()
    api.async_live.side_effect = None
    api.async_output_power_settings.side_effect = None
    api.async_live.return_value = {"con":1,"power":{"pv":0}}
    freezer.tick(1900)
    await c.async_refresh()
    if m.task: await m.task
    assert m.status["output_power"] == "readable"
    api.async_output_power_settings.assert_awaited_once()


async def test_genuine_cloud_failure_is_not_hidden_while_live_is_available(system):
    c,api,m = system
    c._output_live_context = (123,"available")
    api.async_output_power_settings.side_effect = HoymilesConnectionError("synthetic")
    await m.start()
    assert m.status["output_power"] == "unavailable"
    assert m.last_error["output_power"]["reason"] == "connection"


async def test_old_rejection_cannot_pause_a_different_verified_inverter(system):
    c,api,m = system
    c._output_live_context = (123,"unavailable")
    api.async_output_power_settings.side_effect = CloudDiagnosticError("cloud_rejected","synthetic")
    await m._async_refresh()
    assert m.polling_paused
    c.device_tree = [{"type":3,"id":100,"model_no":"HMS-2000-4WB"}]
    c.inverters = deepcopy(c.device_tree)
    assert not m.polling_paused
    assert m.display_status() == "unavailable"
    api.async_write_output_power_settings.assert_not_awaited()


async def test_inflight_read_rejection_is_not_attributed_to_a_replacement_target(system):
    c,api,m = system
    c._output_live_context = (123,"unavailable")
    async def rejected(sid):
        c.device_tree = [{"type":3,"id":100,"model_no":"HMS-2000-4WB"}]
        c.inverters = deepcopy(c.device_tree)
        raise CloudDiagnosticError("cloud_rejected","synthetic")
    api.async_output_power_settings.side_effect = rejected
    await m._async_refresh()
    assert m._rejected_read_target is None
    assert not m.polling_paused


async def test_refresh_button_is_unavailable_during_pause_instead_of_reporting_a_cooldown(system):
    c,api,m = system
    c.async_set_updated_data({"live":{"con":1}})
    button = HoymilesRefreshOutputPowerButton(c, SimpleNamespace(entry_id="synthetic",data={"station_id":123}))
    assert button.available
    c._output_live_context = (123,"offline")
    assert not button.available
    c._output_live_context = (123,"available")
    assert button.available
