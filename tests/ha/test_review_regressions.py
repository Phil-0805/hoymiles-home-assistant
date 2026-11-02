"""Synthetic regressions found during the b5 whole-repository review."""

from datetime import UTC, datetime, timedelta
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient
from custom_components.hoymiles_home.battery import parse_work_mode_settings
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesAuthError, HoymilesConnectionError
from custom_components.hoymiles_home.sensor import _battery_charge_power, _battery_discharge_power


def settings(lower=12, upper=95, mode=2):
    return parse_work_mode_settings({"code": 0, "data": {
        "mode": mode, "soc_l": lower, "soc_h": upper, "k_3": {"mode": 1},
    }})


async def test_soc_write_preserves_app_changes_since_last_periodic_read(hass):
    api = AsyncMock()
    api.async_battery_settings.side_effect = [settings(12, 80), settings(20, 80)]
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.battery_settings = settings(12, 95)
    with patch("custom_components.hoymiles_home.coordinator.BATTERY_WRITE_CONFIRM_ATTEMPTS", 1):
        await coordinator.async_set_battery_reserve_soc(20)
    assert api.async_write_battery_settings.await_args.args[2] == {
        "reserve_soc": 20, "soc_l": 20, "soc_h": 80,
    }
    assert api.async_battery_settings.await_count == 2
    await coordinator.async_shutdown()


async def test_soc_write_cannot_switch_back_to_cached_mode(hass):
    api = AsyncMock()
    api.async_battery_settings.return_value = settings(mode=3)
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.battery_settings = settings()
    with pytest.raises(HoymilesConnectionError):
        await coordinator.async_set_battery_reserve_soc(20)
    api.async_write_battery_settings.assert_not_awaited()
    await coordinator.async_shutdown()


def response_client(raw):
    response = MagicMock(status=200)
    response.json = AsyncMock(return_value=json.loads(raw))
    async def chunks(*args):
        for offset in range(0, len(raw), 256):
            yield raw[offset:offset + 256]
    response.content.iter_chunked = chunks
    session = MagicMock()
    session.post.return_value.__aenter__.return_value = response
    return HoymilesHomeClient(session, "test@example.com", "synthetic"), response


@pytest.mark.parametrize("raw", [
    json.dumps({"data": "x" * 4096}).encode(),
    ('{"data":' + '[' * 60 + '0' + ']' * 60 + '}').encode(),
], ids=["size", "depth"])
async def test_json_response_size_and_nesting_are_bounded(raw):
    api, response = response_client(raw)
    with patch("custom_components.hoymiles_home.api.MAX_JSON_BYTES", 1024, create=True):
        with pytest.raises(HoymilesConnectionError):
            await api._json("https://neapi.hoymiles.com/test", {})
    response.json.assert_not_awaited()


@pytest.mark.parametrize("message", ["token expired PRIVATE", "PRIVATE account unavailable"])
def test_cloud_errors_do_not_copy_server_strings_into_logs_or_attributes(message):
    with pytest.raises((HoymilesConnectionError, HoymilesAuthError)) as caught:
        HoymilesHomeClient._unwrap({"status": "1", "message": message})
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("relay", [1.5, 2.5])
def test_fractional_relay_code_is_not_truncated_to_a_known_direction(relay):
    data = {"live": {"brs": relay, "power": {"bat": -200}}}
    assert _battery_charge_power(data) == 0
    assert _battery_discharge_power(data) == 200


async def test_failed_live_refresh_breaks_energy_integration(hass):
    api = AsyncMock()
    api.async_live.side_effect = HoymilesConnectionError("synthetic interruption")
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator._energy_store.async_delay_save = MagicMock()
    now = datetime.now(UTC)
    live = {"con": 1, "brs": 1, "power": {"bat": 1000, "load": 1000}}
    coordinator._update_battery_energy(live, now)
    from homeassistant.helpers.update_coordinator import UpdateFailed
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    result = coordinator._update_battery_energy(live, now + timedelta(seconds=6))
    assert result["charge_wh"] == result["consumption_wh"] == 0
    await coordinator.async_shutdown()


async def test_reauth_updates_password_in_place_and_preserves_identity(hass, client):
    from homeassistant.config_entries import SOURCE_REAUTH
    from homeassistant.data_entry_flow import FlowResultType
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.hoymiles_home.const import DOMAIN
    entry = MockConfigEntry(domain=DOMAIN, unique_id="test@example.com_123",
        data={"username": "test@example.com", "password": "old-synthetic", "station_id": 123},
        options={"pv_power_source": "pv"})
    entry.add_to_hass(hass)
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock(return_value=True)) as reload:
        result = await hass.config_entries.flow.async_init(DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id}, data=entry.data)
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "new-synthetic"})
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == "reauth_successful"
        await hass.async_block_till_done()
        reload.assert_awaited_once_with(entry.entry_id)
    assert entry.data == {"username": "test@example.com", "password": "new-synthetic", "station_id": 123}
    assert entry.unique_id == "test@example.com_123"
    assert entry.options == {"pv_power_source": "pv"}
    client.async_device_tree.assert_awaited_once_with(123)


async def test_corrupt_deflate_payload_is_a_handled_connection_error():
    api = HoymilesHomeClient(MagicMock(), "test@example.com", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._async_binary_data = AsyncMock(return_value=bytes.fromhex("1f8b0800000000000003") + b"\x07" * 20)
    with pytest.raises(HoymilesConnectionError):
        await api.async_module_snapshot(123, "2026-10-29")


async def test_transport_traceback_does_not_expose_signed_url():
    import traceback
    from aiohttp import ClientConnectionError
    api = HoymilesHomeClient(MagicMock(), "test@example.com", "synthetic")
    api._session.post.side_effect = ClientConnectionError("https://neapi.hoymiles.com/?token=PRIVATE")
    with pytest.raises(HoymilesConnectionError) as caught:
        await api._json("https://neapi.hoymiles.com/test", {})
    assert "PRIVATE" not in "".join(traceback.format_exception(caught.value))


async def test_failed_station_totals_do_not_retry_at_live_frequency(hass):
    api = AsyncMock()
    api.async_live.return_value = {"con": 1, "power": {}}
    api.async_station_realtime.side_effect = HoymilesConnectionError("synthetic failure")
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    coordinator.device_tree = [{"id": 99}]
    coordinator._start_battery_settings_refresh = MagicMock()
    coordinator.module_polling.start = MagicMock()
    await coordinator._async_update_data()
    await coordinator._async_update_data()
    api.async_station_realtime.assert_awaited_once()
    await coordinator.async_shutdown()


async def test_station_daily_total_expires_at_local_day_boundary(hass, freezer):
    from types import SimpleNamespace
    from custom_components.hoymiles_home.sensor import HoymilesStationSensor, STATION_SENSORS
    freezer.move_to("2026-10-29 22:59:30+00:00")
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123, station_timezone="Europe/Berlin")
    coordinator.data = {"station": {"today_eq": 1000}, "live": {"con": 1}}
    coordinator._station_updated = datetime.now(UTC)
    description = next(d for d in STATION_SENSORS if d.key == "today_energy")
    entity = HoymilesStationSensor(coordinator, SimpleNamespace(entry_id="existing", data={"station_id": 123}), description)
    assert entity.available
    freezer.move_to("2026-10-29 23:00:01+00:00")
    assert not entity.available
    await coordinator.async_shutdown()


@pytest.mark.parametrize("failure", [HoymilesAuthError("synthetic auth"), HoymilesConnectionError("synthetic network")])
async def test_reauth_failure_preserves_old_entry(hass, client, failure):
    from homeassistant.config_entries import SOURCE_REAUTH
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.hoymiles_home.const import DOMAIN
    entry = MockConfigEntry(domain=DOMAIN, unique_id="test@example.com_123",
        data={"username": "test@example.com", "password": "old-synthetic", "station_id": 123})
    entry.add_to_hass(hass)
    client.async_login.side_effect = failure
    result = await hass.config_entries.flow.async_init(DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id}, data=entry.data)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "new-synthetic"})
    assert result["errors"]["base"] in {"invalid_auth", "cannot_connect"}
    assert entry.data["password"] == "old-synthetic"
    client.async_device_tree.assert_not_awaited()


async def test_bounded_json_preserves_valid_zero_and_nested_settings():
    raw = json.dumps({"status": "0", "data": {"zero": 0, "settings": [{"soc_l": 12}]}}).encode()
    api, _ = response_client(raw)
    assert await api._json("https://neapi.hoymiles.com/test", {}) == json.loads(raw)


@pytest.mark.parametrize("key,instant", [("month_energy", "2026-10-31 23:00:01+00:00"), ("year_energy", "2026-12-31 23:00:01+00:00")])
def test_station_period_totals_expire_at_rollover(hass, freezer, key, instant):
    from datetime import timedelta
    freezer.move_to(instant)
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123, station_timezone="Europe/Berlin")
    coordinator._station_updated = datetime.now(UTC) - timedelta(seconds=31)
    assert not coordinator.station_is_fresh(key)


def test_station_total_expiry_does_not_erase_value_or_calculated_energy(hass):
    coordinator = HoymilesHomeCoordinator(hass, AsyncMock(), 123)
    coordinator.station = {"today_eq": 1234}
    coordinator._charge_wh = 42
    coordinator._station_updated = datetime.now(UTC) - timedelta(minutes=3)
    assert not coordinator.station_is_fresh("total_energy")
    assert coordinator.station["today_eq"] == 1234
    assert coordinator._charge_wh == 42


async def test_login_network_failure_pauses_other_station_logins():
    from custom_components.hoymiles_home.cloud_runtime import AccountRuntime
    from custom_components.hoymiles_home.errors import HoymilesRateLimitError
    runtime = AccountRuntime()
    one = HoymilesHomeClient(MagicMock(), "test@example.com", "synthetic", runtime)
    two = HoymilesHomeClient(MagicMock(), "test@example.com", "synthetic", runtime)
    login = AsyncMock(side_effect=HoymilesConnectionError("synthetic network failure"))
    one._async_login_unlocked = two._async_login_unlocked = login
    with pytest.raises(HoymilesConnectionError):
        await one.async_ensure_login()
    with pytest.raises(HoymilesRateLimitError):
        await two.async_ensure_login()
    login.assert_awaited_once()


@pytest.mark.parametrize("method", ["async_station_realtime", "_get_live_uri"])
async def test_invalid_inner_response_shape_is_a_handled_connection_error(method):
    api = HoymilesHomeClient(MagicMock(), "test@example.com", "synthetic")
    api.async_ensure_login = AsyncMock()
    api._json = AsyncMock(return_value={"status": "0", "data": [1]})
    with pytest.raises(HoymilesConnectionError):
        await getattr(api, method)(123)


async def test_long_retry_after_never_restarts_http_before_server_deadline():
    from aiohttp import ClientResponseError
    from types import SimpleNamespace
    from custom_components.hoymiles_home.errors import HoymilesRateLimitError
    api = HoymilesHomeClient(MagicMock(), "test@example.com", "synthetic")
    response = MagicMock(status=429)
    response.raise_for_status.side_effect = ClientResponseError(
        SimpleNamespace(real_url="https://neapi.hoymiles.com/test"), (), status=429,
        headers={"Retry-After": "172800"},
    )
    api._session.post.return_value.__aenter__.return_value = response
    clock = [100.0]
    with patch("custom_components.hoymiles_home.cloud_runtime.monotonic", side_effect=lambda: clock[0]):
        with pytest.raises(HoymilesRateLimitError):
            await api._json("https://neapi.hoymiles.com/test", {})
        clock[0] += 86401
        with pytest.raises(HoymilesRateLimitError):
            async with api.runtime.request():
                pytest.fail("HTTP budget resumed before the server deadline")
    assert api._session.post.call_count == 1
