"""Station-only Enduser monitoring must not depend on optional device trees."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.errors import HoymilesAuthError, HoymilesConnectionError
from test_enduser_profile import ready, ok, es, LIVE, BASE, SECRET


def forbid_device_tree(api):
    api.async_device_tree = AsyncMock(side_effect=AssertionError("Station monitoring must not request device data"))


async def test_setup_validates_exact_station_without_requesting_device_tree(hass):
    api = ready(ok({"id": 123, "classify": 5}))
    api.async_login = AsyncMock()
    api.async_list_stations = AsyncMock(return_value=[{"sid": 123, "name": "synthetic"}])
    forbid_device_tree(api)
    with patch("custom_components.hoymiles_home.config_flow.HoymilesHomeClient", return_value=api):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "username": "synthetic@example.invalid", "password": SECRET, "client_profile": "enduser"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"station_id": "123"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["station_id"] == 123 and result["data"]["client_profile"] == "enduser"
    api.async_device_tree.assert_not_awaited()
    assert api._session.post.call_count == 1
    assert api._session.post.call_args.args[0] == BASE + "/pvm/api/0/station/find"
    assert api._session.post.call_args.kwargs["json"] == {"id": 123}


@pytest.mark.parametrize("response,error", [
    (ok({"id": 999, "classify": 5}), "invalid_station_response"),
    (ok({"id": 123}), "invalid_station_response"),
    (ok({"id": 123, "classify": 999}), "unsupported_station"),
    (ok(None), "invalid_station_response"),
])
async def test_manual_setup_still_rejects_wrong_or_unknown_station(hass, response, error):
    api = ready(response)
    api.async_login = AsyncMock()
    api.async_list_stations = AsyncMock(return_value=[])
    forbid_device_tree(api)
    with patch("custom_components.hoymiles_home.config_flow.HoymilesHomeClient", return_value=api):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "username": "synthetic@example.invalid", "password": SECRET, "client_profile": "enduser"})
        assert result["step_id"] == "manual_station"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"station_id": 123})
    assert result["type"] is FlowResultType.FORM and result["errors"] == {"base": error}
    api.async_device_tree.assert_not_awaited()


async def test_runtime_reads_live_and_totals_without_optional_tree(hass):
    api = ready(ok({"id": 123, "classify": 5}), ok({"uri": LIVE}), ok(es()),
                ok({"today_eq": 1234}), ok(es()))
    forbid_device_tree(api)
    coordinator = HoymilesHomeCoordinator(hass, api, 123, battery_controls=True, device_controls=True)
    try:
        first = await coordinator._async_update_data()
        second = await coordinator._async_update_data()
        assert first["live"]["power"]["pv"] == second["live"]["power"]["pv"] == 123.5
        assert first["station"] == {"today_eq": 1234}
        assert not first["device_tree"] and not first["inverters"]
        assert not coordinator.battery_controls and not coordinator.device_controls
        api.async_device_tree.assert_not_awaited()
        assert [c.args[0] for c in api._session.post.call_args_list] == [
            BASE + "/pvm/api/0/station/find", BASE + "/pvm/api/0/station/get_sd_uri", LIVE,
            BASE + "/pvm-data/api/0/station/data/count_station_real_data", LIVE]
    finally:
        await coordinator.async_shutdown()


async def test_initially_missing_live_uri_still_requires_exact_station_metadata(hass, freezer):
    api = ready(ok({"id": 123, "classify": 5}), ok({"uri": None}), ok({"uri": None}), ok({"today_eq": 1234}),
                ok({"uri": LIVE}), ok(es()), ok({"today_eq": 1250}))
    forbid_device_tree(api)
    api.async_list_stations = AsyncMock(side_effect=AssertionError("Do not replace exact metadata validation with a list fallback"))
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    try:
        first = await coordinator._async_update_data()
        assert first["live_available"] is False and first["station"] == {"today_eq": 1234}
        assert coordinator._station_access_validated
        assert api._session.post.call_count == 4
        await coordinator._async_update_data()
        assert api._session.post.call_count == 4
        freezer.tick(61)
        recovered = await coordinator._async_update_data()
        assert recovered["live_available"] is True and recovered["live"]["power"]["pv"] == 123.5
        api.async_device_tree.assert_not_awaited()
        api.async_list_stations.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("failure", [HoymilesAuthError("synthetic"),
    CloudDiagnosticError("invalid_enduser_station_id", "synthetic")])
async def test_unavailable_live_does_not_accept_failed_station_validation(hass, failure):
    api = ready()
    api.async_live = AsyncMock(side_effect=CloudDiagnosticError("missing_uri", "synthetic"))
    api.async_validate_station = AsyncMock(side_effect=failure)
    forbid_device_tree(api)
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    try:
        from homeassistant.exceptions import ConfigEntryAuthFailed
        with pytest.raises((ConfigEntryAuthFailed, UpdateFailed)):
            await coordinator._async_update_data()
        assert not coordinator._station_access_validated
        api.async_device_tree.assert_not_awaited()
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("profile", ["home", "installer"])
async def test_station_only_method_rejects_other_profiles_before_http(profile):
    from custom_components.hoymiles_home.api import HoymilesHomeClient
    from unittest.mock import MagicMock
    api = HoymilesHomeClient(MagicMock(), "synthetic", "synthetic", profile=profile)
    with pytest.raises(HoymilesConnectionError):
        await api.async_validate_station(123)
    api._session.post.assert_not_called()
