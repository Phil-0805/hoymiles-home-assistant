"""Issue 61: private diagnostic reasons and bounded recovery, with no HTTP."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun import freeze_time
import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.diagnostics import async_get_config_entry_diagnostics
from custom_components.hoymiles_home.errors import (
    HoymilesAuthError, HoymilesConnectionError, HoymilesRateLimitError,
)
from custom_components.hoymiles_home.inverter import standalone_hms_target

RAW = [{"id": 99, "type": 3, "sn": "PRIVATE-SERIAL"}]
MODEL = {**RAW[0], "model_no": "HMS-2000-4WB"}


def envelope(data):
    return {"status": 0, "data": data}


def api_with(*responses):
    api = HoymilesHomeClient(MagicMock(), "private@example.invalid", "PASSWORD")
    api._json = AsyncMock(side_effect=responses)
    return api


@pytest.mark.parametrize("detail,reason,retryable", [
    (None, "empty_data", True),
    ({}, "empty_data", True),
    (RAW[0], "model_missing", True),
    ({**MODEL, "id": "99"}, "invalid_identity_type", False),
    ({**MODEL, "id": True}, "invalid_identity_type", False),
    ({**MODEL, "id": 98}, "identity_mismatch", False),
    ({**MODEL, "sn": "OTHER-PRIVATE"}, "serial_mismatch", False),
    ({**RAW[0], "model_no": 123}, "invalid_model_type", False),
    ({**RAW[0], "model_no": "UNRECOGNIZED-PRIVATE"}, "unsupported_model", False),
    (json.dumps(MODEL), "unexpected_data_type", False),
])
async def test_rejection_reasons_do_not_relax_identity_or_model_checks(detail, reason, retryable):
    api = api_with(envelope([]), envelope(detail))
    original = deepcopy(RAW)
    enriched = await api.async_enrich_inverters(123, original)
    discovery = enriched[0]["_model_discovery"]
    assert discovery["web_tree_reason"] == "empty_data"
    assert discovery["detail_reason"] == reason
    assert discovery["retryable"] is retryable
    assert standalone_hms_target(original, enriched) is None
    assert original == RAW
    assert enriched[0]["id"] == 99
    assert enriched[0]["sn"] == "PRIVATE-SERIAL"


@pytest.mark.parametrize("tree,reason", [
    ([{**MODEL, "id": 100}], "candidate_missing"),
    ([MODEL, {**MODEL, "model_no": "HMS-800-2WB"}], "ambiguous_candidate"),
    (json.dumps([MODEL]), "unexpected_data_type"),
    ([{**MODEL, "sn": "OTHER"}], "serial_mismatch"),
])
async def test_web_candidate_failures_have_fixed_reasons(tree, reason):
    api = api_with(envelope(tree), envelope({}))
    enriched = await api.async_enrich_inverters(123, deepcopy(RAW))
    assert enriched[0]["_model_discovery"]["web_tree_reason"] == reason
    assert standalone_hms_target(RAW, enriched) is None


@pytest.mark.parametrize("error,reason,retryable", [
    (HoymilesConnectionError("PRIVATE"), "connection", True),
    (CloudDiagnosticError("http_error", "PRIVATE"), "http_error", False),
    (CloudDiagnosticError("redirect_rejected", "PRIVATE"), "redirect_rejected", False),
    (CloudDiagnosticError("cloud_rejected", "PRIVATE"), "cloud_rejected", False),
    (HoymilesAuthError("PRIVATE"), "authentication", False),
    (HoymilesRateLimitError("PRIVATE", 3600), "rate_limited", False),
])
async def test_request_errors_preserve_pause_and_no_retry_policy(error, reason, retryable):
    api = api_with(error, envelope({}))
    enriched = await api.async_enrich_inverters(123, deepcopy(RAW))
    discovery = enriched[0]["_model_discovery"]
    assert discovery["web_tree_reason"] == reason
    assert (discovery.get("retryable") is True) is retryable
    assert api._json.await_count == (1 if isinstance(error, (HoymilesAuthError, HoymilesRateLimitError)) else 2)


async def test_known_metadata_keeps_provenance_and_is_not_requested_again():
    known = {**MODEL, "_model_discovery": {"result": "identified", "source": "web_tree"}}
    api = api_with(envelope([]), envelope({}))
    enriched = await api.async_enrich_inverters(123, [known, {"id": 100, "type": 3}])
    assert enriched[0] == known
    assert standalone_hms_target(RAW, [enriched[0]]) is not None
    assert api._json.await_args.args[1] == {"id": 100, "sid": 123}
    assert "_model_discovery" not in RAW[0]


def coordinator(hass, api):
    api.async_live = AsyncMock(return_value={"power": {"pv": 42}, "con": 1})
    api.async_device_tree = AsyncMock(return_value=deepcopy(RAW))
    api.async_station_realtime = AsyncMock(return_value={})
    c = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True)
    # Isolate scheduling of unrelated readers. Recovery itself is the real API.
    for manager in (c.battery_telemetry, c.module_polling, c.device_settings,
                    c.cutoff_settings, c.output_settings):
        manager.start = MagicMock()
    return c


async def update(c):
    with patch.object(c, "_start_battery_settings_refresh"):
        c.data = await c._async_update_data()


async def test_missing_startup_metadata_recovers_on_existing_tick_and_enables_original_target(hass):
    api = api_with(envelope([]), envelope({}), envelope([MODEL]))
    c = coordinator(hass, api)
    with freeze_time("2026-11-17 10:00:00+00:00") as clock:
        try:
            await update(c)
            assert c._model_retry_at == datetime.now(UTC) + timedelta(minutes=5)
            assert standalone_hms_target(c.device_tree, c.inverters) is None
            for _ in range(3):
                await update(c)
            assert api._json.await_count == 2
            clock.move_to(c._model_retry_at)
            await update(c)
            await c._model_recovery_task
            assert api._json.await_count == 3
            assert c._model_retry_count == 1
            assert c._model_retry_at is None
            assert c.data["live_available"] is True
            assert standalone_hms_target(c.device_tree, c.inverters) is not None
            assert c.output_settings._target("output_power")["inverter"]["id"] == 99
            assert c._start_battery_settings_refresh() is None
            assert c.battery_settings["error"] == "not_applicable"
            assert c.device_tree == RAW
            clock.tick(timedelta(hours=1))
            await update(c)
            assert api._json.await_count == 3
        finally:
            await c.async_shutdown()


async def test_recovery_is_capped_after_two_attempts_and_has_completion_based_delays(hass):
    api = api_with(*([envelope([]), envelope({})] * 3))
    c = coordinator(hass, api)
    with freeze_time("2026-11-17 10:00:00+00:00") as clock:
        try:
            await update(c)
            first = c._model_retry_at
            clock.move_to(first)
            await update(c)
            await c._model_recovery_task
            assert c._model_retry_at == first + timedelta(minutes=15)
            clock.move_to(c._model_retry_at)
            await update(c)
            await c._model_recovery_task
            assert c._model_retry_count == 2
            assert c._model_retry_at is None
            clock.tick(timedelta(days=1))
            await update(c)
            assert api._json.await_count == 6
        finally:
            await c.async_shutdown()


@pytest.mark.parametrize("change", ["unload", "station", "tree", "inverter"])
async def test_inflight_metadata_is_discarded_after_unload_or_target_change(hass, change):
    api = api_with(envelope([MODEL]))
    c = coordinator(hass, api)
    c.device_tree = deepcopy(RAW)
    c.inverters = deepcopy(RAW)
    real = api.async_enrich_inverters

    async def changed(*args):
        found = await real(*args)
        if change == "unload":
            await c.async_shutdown()
        elif change == "station":
            c.station_id = 456
        elif change == "tree":
            c.device_tree = [{"type": 12, "id": 100}]
        else:
            c.inverters[0]["sn"] = "CHANGED"
        return found

    api.async_enrich_inverters = changed
    try:
        await c._async_enrich_inverter_models()
        assert c._model_retry_at is None
        assert "model_no" not in c.inverters[0]
    finally:
        await c.async_shutdown()


async def test_recovery_diagnostics_export_only_allowlisted_reasons(hass):
    api = api_with(envelope([]), envelope({**MODEL, "sn": "PRIVATE-OTHER"}))
    enriched = await api.async_enrich_inverters(123, deepcopy(RAW))
    enriched[0]["_model_discovery"].update(private="PASSWORD", raw="PRIVATE-SERIAL")
    c = coordinator(hass, api)
    c.inverters = enriched
    entry = SimpleNamespace(entry_id="synthetic", data={})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = c
    try:
        result = await async_get_config_entry_diagnostics(hass, entry)
        discovery = result["inverters"][0]["discovery"]
        assert discovery["web_tree_reason"] == "empty_data"
        assert discovery["detail_reason"] == "serial_mismatch"
        serialized = json.dumps(result)
        for private in ("PASSWORD", "PRIVATE-SERIAL", "PRIVATE-OTHER", "private@example.invalid"):
            assert private not in serialized
        enriched[0]["_model_discovery"]["detail_reason"] = "PRIVATE-OTHER"
        result = await async_get_config_entry_diagnostics(hass, entry)
        assert "detail_reason" not in result["inverters"][0]["discovery"]
    finally:
        await c.async_shutdown()


async def test_recovery_does_not_block_live_coalesces_and_is_cancelled_on_unload(hass):
    api = api_with(envelope([]), envelope({}))
    c = coordinator(hass, api)
    entered, release = asyncio.Event(), asyncio.Event()
    with freeze_time("2026-11-17 10:00:00+00:00") as clock:
        try:
            await update(c)
            real = api.async_enrich_inverters

            async def blocked(*args):
                entered.set()
                await release.wait()
                return await real(*args)

            api.async_enrich_inverters = AsyncMock(side_effect=blocked)
            clock.move_to(c._model_retry_at)
            await update(c)  # Must finish while the metadata request is blocked.
            await entered.wait()
            task = c._model_recovery_task
            for _ in range(3):
                await update(c)
            assert api.async_enrich_inverters.await_count == 1
            assert c._model_recovery_task is task
            assert c.data["live_available"] is True
            await c.async_shutdown()
            assert task.cancelled()
            assert c._model_retry_at is None
            assert "model_no" not in c.inverters[0]
            c._start_model_recovery()
            assert c._model_recovery_task is task
        finally:
            release.set()
            await c.async_shutdown()


async def test_next_recovery_delay_starts_after_request_finishes(hass):
    api = api_with(envelope([]), envelope({}), envelope([]), envelope({}))
    c = coordinator(hass, api)
    with freeze_time("2026-11-17 10:00:00+00:00") as clock:
        try:
            await update(c)
            real = api.async_enrich_inverters

            async def slow(*args):
                clock.tick(timedelta(seconds=11))
                return await real(*args)

            api.async_enrich_inverters = slow
            clock.move_to(c._model_retry_at)
            await update(c)
            await c._model_recovery_task
            assert c._model_retry_at == datetime.now(UTC) + timedelta(minutes=15)
        finally:
            await c.async_shutdown()


@pytest.mark.parametrize("error", [HoymilesAuthError("PRIVATE"), HoymilesRateLimitError("PRIVATE")])
async def test_detail_auth_or_rate_failure_stops_remaining_optional_device_requests(error):
    api = api_with(envelope([]), error)
    found = await api.async_enrich_inverters(123, [*deepcopy(RAW), {"id": 100, "type": 3}])
    assert api._json.await_count == 2
    assert all(item["_model_discovery"].get("retryable") is not True for item in found)


@pytest.mark.parametrize("error", [
    HoymilesAuthError("PRIVATE"), HoymilesRateLimitError("PRIVATE"),
    CloudDiagnosticError("http_error", "PRIVATE"),
])
async def test_nonrecoverable_errors_do_not_schedule_coordinator_recovery(hass, error):
    api = api_with(error, envelope({}))
    c = coordinator(hass, api)
    try:
        await update(c)
        assert c._model_retry_at is None
        assert c._model_retry_count == 0
    finally:
        await c.async_shutdown()


async def test_timeout_is_bounded_recoverable_and_does_not_mutate_original():
    api = api_with(TimeoutError())
    original = deepcopy(RAW)
    found = await api.async_enrich_inverters(123, original)
    assert found[0]["_model_discovery"]["timeout"] is True
    assert found[0]["_model_discovery"]["retryable"] is True
    assert api._json.await_count == 1
    assert original == RAW


@pytest.mark.parametrize("discovery", ["PRIVATE", None, {"source": "PRIVATE"}])
async def test_known_home_model_does_not_preserve_invalid_discovery_data(discovery):
    api = api_with()
    found = await api.async_enrich_inverters(123, [{**MODEL, "_model_discovery": discovery}])
    assert found[0]["_model_discovery"] == {"result": "identified", "source": "home_tree"}
    api._json.assert_not_awaited()


async def test_recovery_only_requests_retryable_devices_on_mixed_installations(hass):
    api = api_with(envelope([]), envelope([MODEL]))
    c = coordinator(hass, api)
    blocked = {"id": 100, "type": 3, "_model_discovery": {
        "result": "unresolved", "source": "none", "detail_reason": "serial_mismatch",
        "retryable": False,
    }}
    missing = {**deepcopy(RAW[0]), "_model_discovery": {
        "result": "unresolved", "source": "none", "retryable": True,
    }}
    c.device_tree = [*deepcopy(RAW), {"id": 100, "type": 3}]
    c.inverters = [missing, deepcopy(blocked)]
    c._model_retry_count = 1
    # A matching web model for the retryable device should complete recovery
    # without any detail request for the nonretryable device.
    api._json.side_effect = [envelope([MODEL])]
    try:
        await c._async_enrich_inverter_models()
        api._json.assert_awaited_once_with(
            "https://neapi.hoymiles.com/pvm/api/0/station/select_device_of_tree", {"id": 123})
        assert c.inverters[0]["model_no"] == "HMS-2000-4WB"
        assert c.inverters[1] == blocked
        assert c._model_retry_at is None
        assert standalone_hms_target(c.device_tree, c.inverters) is None
    finally:
        await c.async_shutdown()
