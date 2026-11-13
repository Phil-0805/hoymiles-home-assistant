"""Enduser V3.14.0 contracts with synthetic data and no real accounts."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.entity_component import EntityComponent
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.cloud_runtime import AccountRuntime
from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.diagnostics import async_get_config_entry_diagnostics
from custom_components.hoymiles_home.enduser import parse_live, parse_totals
from custom_components.hoymiles_home.errors import HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError
from custom_components.hoymiles_home.sensor import HoymilesStationSensor, STATION_SENSORS
from custom_components.hoymiles_home.telemetry import battery_activity
from test_installer_profile import ok, response, BASE, PRE, LOGIN, SECRET, LIVE


def client(*responses, runtime=None):
    api = HoymilesHomeClient(MagicMock(), SECRET, "password", runtime, profile="enduser")
    api.runtime.request = MagicMock()
    api.runtime.request.return_value.__aenter__ = AsyncMock()
    api.runtime.request.return_value.__aexit__ = AsyncMock(return_value=False)
    api._session.post.return_value.__aenter__.side_effect = responses
    return api


def ready(*responses):
    api = client(*responses)
    api._token = SECRET
    api._token_expires = datetime.now(UTC) + timedelta(hours=1)
    return api


def es(**changes):
    return {"con": 1, "dly": 5000, "soc": "42.5", "es": {
        "pp": "123.5", "gp": "20", "lp": "100", "bp": "43.5", "sp": "0"},
        "flow": [{"o": 4, "i": 2}, {"o": 4, "i": 10}, {"o": 1, "i": 10}],
        **changes}


@pytest.mark.parametrize("version,expected", [
    (1, "5f4dcc3b5aa765d61d8327deb882cf99"),
    (2, "5f4dcc3b5aa765d61d8327deb882cf99.XohImNooBHFR0OVvjcYpJ3NgPQ1qq73WKhHvch0VQtg="),
    (3, "68617368"),
])
@pytest.mark.parametrize("dc", [0, 1, "0", "1"])
async def test_enduser_login_has_own_identity_and_no_home_region_request(version, expected, dc):
    api = client(ok({"v": version, "dc": dc, "a": "0123456789abcdef", "n": SECRET}), ok({"token": SECRET}))
    with patch("custom_components.hoymiles_home.api.asyncio.to_thread", new=AsyncMock(return_value=b"hash")):
        await api.async_login()
    calls = api._session.post.call_args_list
    assert [c.args[0] for c in calls] == [PRE, LOGIN]
    assert calls[0].kwargs["headers"]["User-Agent"] == "smo/ad/3.14.0/159/0"
    assert calls[1].kwargs["headers"]["User-Agent"] == f"smo/ad/3.14.0/159/{dc}"
    assert calls[1].kwargs["json"] == {"u": SECRET, "ch": expected, "n": SECRET}
    assert all("Authorization" not in c.kwargs["headers"] and not c.kwargs["allow_redirects"] for c in calls)


@pytest.mark.parametrize("challenge", [
    {"v": 4, "dc": 0}, {"v": 1, "dc": 4}, {"v": 1, "dc": True},
    {"v": 1, "dc": 0, "f": 1}, {"v": 1, "dc": 0, "f": 2},
    {"v": 3, "dc": 0, "a": "bad", "n": SECRET},
])
async def test_bad_challenge_stops_before_password_submission(challenge):
    api = client(ok(challenge))
    with pytest.raises((HoymilesConnectionError, HoymilesAuthError)):
        await api.async_login()
    assert api._session.post.call_count == 1


@pytest.mark.parametrize("where", ["pre", "login"])
async def test_enduser_rejection_has_safe_profile_label_and_no_fallback(where, caplog):
    responses = [] if where == "pre" else [ok({"v": 1, "dc": 0})]
    api = client(*responses, response(data={"status": 1, "data": SECRET, "message": SECRET}))
    with pytest.raises((HoymilesConnectionError, HoymilesAuthError)):
        await api.async_login()
    assert api._session.post.call_count == len(responses) + 1
    assert "client_profile=enduser" in caplog.text and SECRET not in caplog.text


async def test_all_profiles_have_separate_tokens_and_shared_budget():
    runtime = AccountRuntime()
    apis = [HoymilesHomeClient(MagicMock(), SECRET, SECRET, runtime, profile=p)
            for p in ("home", "installer", "enduser")]
    for i, api in enumerate(apis):
        api._token = str(i)
        api._auth_state.auth_dc = i
    assert [api._token for api in apis] == ["0", "1", "2"]
    other = HoymilesHomeClient(MagicMock(), SECRET, SECRET, runtime, profile="enduser")
    assert other._token == "2" and other._auth_state is apis[2]._auth_state
    assert all(api._lock is runtime.login_lock for api in apis)
    runtime.pause(60)
    for api in apis:
        with pytest.raises(HoymilesRateLimitError):
            async with api.runtime.request():
                pytest.fail("Shared server pause was bypassed")


async def test_enduser_discovery_follows_app_continuation_without_nested_device_ids(caplog):
    rows = [{"id": i, "name": " Plant ", "devices": [{"id": 999}]} for i in range(1, 11)]
    api = ready(ok({"list": rows, "ntk": SECRET}), ok({"list": [{"id": 11}]}))
    stations = await api.async_list_stations()
    assert [s["sid"] for s in stations] == list(range(1, 12))
    assert stations[0]["name"] == "Plant"
    assert [c.kwargs["json"] for c in api._session.post.call_args_list] == [
        {"classify": 0, "page": 1, "page_size": 10},
        {"classify": 0, "page": 2, "page_size": 10, "ntk": SECRET}]
    assert all(c.args[0] == BASE + "/pvm/api/0/station_v3/next_p_a" for c in api._session.post.call_args_list)
    assert SECRET not in caplog.text


@pytest.mark.parametrize("data", [None, {}, {"list": None}, {"list": [{"id": True}]},
    {"list": [{"id": -1}]}, {"list": [{"sid": 123}]},
    {"list": [{"id": i} for i in range(1, 11)], "ntk": True}])
async def test_invalid_enduser_list_is_not_empty_success(data):
    api = ready(ok(data))
    with pytest.raises(HoymilesConnectionError):
        await api.async_list_stations()
    assert api._session.post.call_count == 1


async def test_empty_discovery_and_repeated_continuation_are_bounded():
    assert await ready(ok({"list": []})).async_list_stations() == []
    api = ready(*[ok({"list": [{"id": i} for i in range(1, 11)], "ntk": SECRET}) for _ in range(2)])
    with pytest.raises(HoymilesConnectionError):
        await api.async_list_stations()
    assert api._session.post.call_count == 2


async def test_full_page_without_token_still_uses_bounded_page_numbers():
    api = ready(ok({"list": [{"id": i} for i in range(1, 11)]}), ok({"list": []}))
    assert len(await api.async_list_stations()) == 10
    assert api._session.post.call_args.kwargs["json"] == {"classify": 0, "page": 2, "page_size": 10}


async def test_continuous_full_pages_stop_at_limit_without_partial_success():
    api = ready(*[ok({"list": [{"id": page * 10 + i} for i in range(1, 11)]}) for page in range(20)])
    with pytest.raises(HoymilesConnectionError):
        await api.async_list_stations()
    assert api._session.post.call_count == 20


async def test_metadata_concurrent_reads_coalesce_and_login_invalidates_cached_classification():
    api = ready()
    api._json = AsyncMock(return_value={"status": 0, "data": {"id": 123, "classify": 5}})
    assert await asyncio.gather(*[api._async_enduser_classification(123) for _ in range(2)]) == [5, 5]
    assert api._json.await_count == 1
    api._json.side_effect = [{"status": 0, "data": {"v": 1, "dc": 0}},
                            {"status": 0, "data": {"token": SECRET}}]
    await api.async_login()
    assert api._station_classifications == {}


@pytest.mark.parametrize("metadata", [{}, {"id": 999, "classify": 5},
    {"id": 123, "classify": True}, {"id": 123, "classify": 999}, {"id": 123, "classify": 2}])
async def test_manual_station_requires_matching_supported_classification(metadata):
    api = ready(ok(metadata))
    with pytest.raises(HoymilesConnectionError):
        await api.async_device_tree(123)
    assert api._session.post.call_count == 1


async def test_hybrid_read_sequence_is_exact_and_metadata_is_coalesced():
    tree = [{"id": 7, "type": 6, "station_id": 123, "children": []}]
    api = ready(ok({"id": 123, "classify": 5}), ok(tree), ok({"uri": LIVE}), ok(es()),
                ok({"today_eq": "1234", "month_eq": "2000", "pv_eq": 99999}))
    assert await api.async_device_tree(123) == tree
    live = await api.async_live(123)
    assert live["power"] == {"pv": 123.5, "grid": 20, "load": 100, "bat": 43.5}
    assert battery_activity(live) == "charging" and live["soc"] == 42.5
    assert await api.async_station_realtime(123) == {"today_eq": 1234, "month_eq": 2000}
    assert [(c.args[0], c.kwargs["json"]) for c in api._session.post.call_args_list] == [
        (BASE + "/pvm/api/0/station/find", {"id": 123}),
        (BASE + "/pvm/api/0/station/select_device_of_tree", {"id": 123}),
        (BASE + "/pvm/api/0/station/get_sd_uri", {"sid": 123}),
        (LIVE, {"m": 0, "t": 1}),
        (BASE + "/pvm-data/api/0/station/data/count_station_real_data", {"sid": 123, "off_real": 1})]
    assert await asyncio.gather(*[api._async_enduser_classification(123) for _ in range(2)]) == [5, 5]
    assert api._session.post.call_count == 5


async def test_station_change_never_reuses_previous_signed_live_uri():
    other_uri = BASE + "/live?other=" + SECRET
    api = ready(ok({"id": 123, "classify": 5}), ok({"uri": LIVE}), ok(es()),
                ok({"id": 456, "classify": 1}), ok({"uri": other_uri}),
                ok({"con": 1, "power": {"pv": "8"}}))
    assert (await api.async_live(123))["power"]["pv"] == 123.5
    assert (await api.async_live(456))["power"]["pv"] == 8
    assert api._session.post.call_args.args[0] == other_uri


@pytest.mark.parametrize("path", ["/pvmc/api/0/station_ctl/write_c", "/pvm-ctl/api/0/dev/setting/read",
    "/pvm-ctl/api/0/dev/setting/write", "/pvmc/api/0/station/select_device_c", "/unknown"])
async def test_home_and_unverified_commands_never_reach_transport(path):
    api = ready()
    with pytest.raises(HoymilesConnectionError):
        await api._json(BASE + path, {"action": 83})
    api._session.post.assert_not_called()
    with pytest.raises(HoymilesConnectionError):
        await api._async_binary_data(BASE + path, {})
    api._session.post.assert_not_called()


@pytest.mark.parametrize("classification", [4, 5, 100])
def test_es_adapter_uses_classification_and_not_home_codes(classification):
    live = parse_live(es(power={"pv": 999}, brs=2, token=SECRET), classification)
    assert live["power"]["pv"] == 123.5
    assert "brs" not in live and SECRET not in json.dumps(live)
    assert battery_activity(live) == "charging"


@pytest.mark.parametrize("flows,battery,grid", [
    ([{"o": 2, "i": 10}, {"o": 4, "i": 1}], -43.5, -20),
    ([{"o": 1, "i": 2}], 43.5, 20),
    ([{"o": 2, "i": 1}], -43.5, -20),
    ([], None, None), (None, None, None), ([None], None, None),
    ([{"o": 2, "i": 10}, {"o": 4, "i": 2}], None, None),
    ([{"o": True, "i": 2}], None, None),
    ([{"o": 999, "i": 2}], None, None),
])
def test_directions_are_explicit_and_ambiguous_flow_never_becomes_idle(flows, battery, grid):
    live = parse_live(es(flow=flows), 5)
    assert live["power"].get("bat") == battery
    assert live["power"].get("grid") == grid
    assert live["power"]["pv"] == 123.5
    if battery is None:
        assert battery_activity(live) is None


@pytest.mark.parametrize("bad", [None, True, "nan", "inf", {}, []])
def test_bad_field_is_absent_without_discarding_valid_sibling(bad):
    live = parse_live(es(es={"pp": bad, "gp": 0, "lp": "100", "bp": bad}, soc=bad), 5)
    assert "pv" not in live["power"] and "bat" not in live["power"] and "soc" not in live
    assert live["power"]["grid"] == 0 and live["power"]["load"] == 100


def test_valid_zero_is_distinct_from_missing_and_offline_retained_values():
    live = parse_live(es(es={"pp": 0, "gp": 0, "lp": 0, "bp": 0}, flow=[]), 5)
    assert live["power"] == {"pv": 0, "grid": 0, "load": 0, "bat": 0}
    assert battery_activity(live) == "idle"
    assert parse_live(es(con=0), 5)["power"] == {}
    assert parse_live(es(con=0, es={"pp": 0, "bp": 0}), 5)["power"] == {"pv": 0}
    assert parse_live({"con": 0}, 5)["power"] == {}
    for payload in ({"con": True}, {"con": 1}, {"con": 1, "power": {"pv": 10}}):
        with pytest.raises(HoymilesConnectionError):
            parse_live(payload, 5)


def test_no_guessed_generation_totals_or_units():
    assert parse_totals({"pv_eq": 1, "consumption_eq": 2}) == {}
    assert parse_totals({"today_eq": "1234.5", "total_eq": 0, "month_eq": True,
                         "year_eq": -1}) == {"today_eq": 1234.5, "total_eq": 0}


@pytest.mark.parametrize("source", [SOURCE_USER, SOURCE_REAUTH])
async def test_flow_can_select_enduser_and_preserves_station_identity(hass, client, source):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="synthetic@example.invalid_123", data={
        "username": "synthetic@example.invalid", "password": SECRET, "station_id": 123})
    if source == SOURCE_REAUTH:
        entry.add_to_hass(hass)
    context = {"source": source, **({"entry_id": entry.entry_id} if source == SOURCE_REAUTH else {})}
    with patch("custom_components.hoymiles_home.config_flow.HoymilesHomeClient", return_value=client) as factory, \
            patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)):
        result = await hass.config_entries.flow.async_init(DOMAIN, context=context,
                                                          data=entry.data if source == SOURCE_REAUTH else None)
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            **({"username": "synthetic@example.invalid"} if source == SOURCE_USER else {}),
            "password": SECRET, "client_profile": "enduser"})
        if source == SOURCE_USER:
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {"station_id": "123"})
            assert result["type"] is FlowResultType.CREATE_ENTRY
            entry = result["result"]
        await hass.async_block_till_done()
    assert entry.unique_id == "synthetic@example.invalid_123"
    assert entry.data["client_profile"] == "enduser" and entry.data["station_id"] == 123
    assert factory.call_args.kwargs == {"profile": "enduser"}


async def test_enduser_options_exclude_home_controls_and_unrelated_pv2_selection(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"client_profile": "enduser"})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert {key.schema for key in result["data_schema"].schema} == {"station_timezone"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"station_timezone": "UTC"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {"station_timezone": "UTC"}


async def test_unsupported_classification_has_specific_setup_error(hass, client):
    client.async_validate_station.side_effect = CloudDiagnosticError(
        "unsupported_profile_operation", "Unsupported Enduser station classification")
    with patch("custom_components.hoymiles_home.config_flow.HoymilesHomeClient", return_value=client):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "username": "synthetic@example.invalid", "password": SECRET, "client_profile": "enduser"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"station_id": "123"})
        assert result["errors"] == {"base": "unsupported_station"}


async def test_sensor_setup_omits_home_controls_and_unimplemented_module_entities(hass):
    from custom_components.hoymiles_home.sensor import async_setup_entry
    api = ready()
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True,
                                          device_controls=True, inverter_details=True)
    coordinator.inverters = [{"id": 7, "type": 3, "model_no": "HMS-2000-4WB"}]
    hass.data.setdefault(DOMAIN, {})["synthetic"] = coordinator
    added = MagicMock()
    try:
        await async_setup_entry(hass, SimpleNamespace(entry_id="synthetic", data={"station_id": 123}), added)
        entities = added.call_args.args[0]
        assert all(isinstance(entity, HoymilesStationSensor) for entity in entities)
        assert all(entity.entity_description.key not in {"ems", "brs", "battery_mode", "battery_settings_access"}
                   for entity in entities)
        coordinator.async_set_updated_data({"live": parse_live(es(flow=[]), 5), "live_available": True,
                                           "battery_energy": {"charge_wh": 0, "discharge_wh": 0}})
        charge = next(entity for entity in entities if entity.entity_description.key == "battery_charge_energy_today")
        assert not charge.available
    finally:
        await coordinator.async_shutdown()


async def test_coordinator_publishes_es_sensors_and_never_starts_home_readers(hass):
    api = ready()
    api.async_live = AsyncMock(return_value=parse_live(es(), 5))
    api.async_device_tree = AsyncMock(return_value=[{"id": 7, "type": 6}])
    api.async_station_realtime = AsyncMock(return_value={"today_eq": 1234})
    coordinator = HoymilesHomeCoordinator(hass, api, 123, pv_power_source="pv2", battery_controls=True,
        device_controls=True, battery_temperatures=True, inverter_details=True)
    coordinator.update_interval = None
    coordinator.module_polling.start = MagicMock()
    entities = [HoymilesStationSensor(coordinator, SimpleNamespace(entry_id="synthetic", data={"station_id": 123}), d)
                for d in STATION_SENSORS if d.key in {"pv_power", "grid_power", "battery_power", "battery_soc"}]
    for entity in entities:
        entity.entity_id = "sensor.synthetic_" + entity.entity_description.key
        entity._attr_name = entity.entity_id
        entity._attr_device_info = None
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    try:
        coordinator.async_set_updated_data(await coordinator._async_update_data())
        await component.async_add_entities(entities)
        assert hass.states.get("sensor.synthetic_pv_power").state == "123.5"
        assert hass.states.get("sensor.synthetic_battery_power").state == "43.5"
        assert not coordinator.battery_controls and not coordinator.device_controls
        assert not coordinator.battery_telemetry.enabled and not coordinator.inverters
        coordinator.module_polling.start.assert_not_called()
        api._session.post.assert_not_called()
        api.async_live.return_value = parse_live(es(flow=[]), 5)
        coordinator.async_set_updated_data(await coordinator._async_update_data())
        assert hass.states.get("sensor.synthetic_grid_power").state == "unavailable"
        assert hass.states.get("sensor.synthetic_battery_power").state == "unavailable"
        api.async_live.return_value = parse_live({"con": 0}, 5)
        coordinator.async_set_updated_data(await coordinator._async_update_data())
        assert hass.states.get("sensor.synthetic_pv_power").state == "unavailable"
        api.async_live.return_value = parse_live(es(), 5)
        coordinator.async_set_updated_data(await coordinator._async_update_data())
        assert hass.states.get("sensor.synthetic_pv_power").state == "123.5"
        hass.data.setdefault(DOMAIN, {})["synthetic"] = coordinator
        diagnostic = await async_get_config_entry_diagnostics(hass, SimpleNamespace(entry_id="synthetic"))
        assert diagnostic["client_profile"] == "enduser" and diagnostic["live_schema"] == "es"
        assert SECRET not in json.dumps(diagnostic)
    finally:
        for entity in entities:
            if entity.hass is not None:
                await entity.async_remove()
        await coordinator.async_shutdown()
