"""App-compatible response types without loosening Enduser identity validation."""

import json

import pytest

from custom_components.hoymiles_home.cloud_logging import CloudDiagnosticError, log_failure
from custom_components.hoymiles_home.errors import HoymilesConnectionError
from test_enduser_profile import ready, ok, SECRET


@pytest.mark.parametrize("embedded", [False, True])
@pytest.mark.parametrize("strings", [False, True])
async def test_metadata_and_tree_accept_app_integer_strings_and_embedded_json(embedded, strings):
    integer = str if strings else int
    metadata = {"id": integer(123), "classify": integer(5)}
    tree = [{"id": integer(7), "type": integer(6), "station_id": integer(123),
             "model_no": "synthetic", "children": [
                 {"id": integer(8), "type": integer(10), "station_id": integer(123)}]}]
    api = ready(ok(json.dumps(metadata) if embedded else metadata), ok(json.dumps(tree) if embedded else tree))
    result = await api.async_device_tree(123)
    assert api._station_classifications == {123: 5}
    assert result == [{"id": 7, "type": 6, "station_id": 123, "model_no": "synthetic",
                       "children": [{"id": 8, "type": 10, "station_id": 123}]}]
    # Do not mutate the original response, including nested children.
    assert type(tree[0]["children"][0]["id"]) is (str if strings else int)
    assert api._session.post.call_count == 2


@pytest.mark.parametrize("metadata,reason", [
    (None, "invalid_enduser_metadata"),
    ({}, "invalid_enduser_station_id"),
    ({"id": "999", "classify": "5"}, "invalid_enduser_station_id"),
    ({"id": True, "classify": 5}, "invalid_enduser_station_id"),
    ({"id": "123.0", "classify": "5"}, "invalid_enduser_station_id"),
    ({"id": SECRET, "classify": 5}, "invalid_enduser_station_id"),
    ({"id": 123, "classify": True}, "invalid_enduser_classification"),
    ({"id": 123, "classify": "5.0"}, "invalid_enduser_classification"),
    ({"id": 123}, "invalid_enduser_classification"),
    ({"id": 123, "classify": "999"}, "unsupported_profile_operation"),
])
async def test_distinct_safe_metadata_failures(metadata, reason, caplog):
    api = ready(ok(metadata))
    with pytest.raises(CloudDiagnosticError) as error:
        await api.async_device_tree(123)
    assert error.value.reason == reason
    log_failure("station_validation", error.value)
    assert f"reason={reason}" in caplog.text and SECRET not in caplog.text
    assert api._session.post.call_count == 1


@pytest.mark.parametrize("tree", [
    None, {}, [None], [{"id": "0", "type": "6"}], [{"id": True, "type": "6"}],
    [{"id": "7.0", "type": "6"}], [{"id": "7", "type": "6", "station_id": "999"}],
    [{"id": "7", "type": "6", "children": {}}],
    [{"id": "7", "type": "6", "sn": "A"}, {"id": 7, "type": 6, "sn": "B"}],
])
async def test_normalization_keeps_all_device_identity_checks(tree):
    api = ready(ok({"id": 123, "classify": 5}), ok(tree))
    with pytest.raises(CloudDiagnosticError) as error:
        await api.async_device_tree(123)
    assert error.value.reason == "invalid_enduser_tree"


async def test_embedded_json_remains_bounded_and_not_repeatedly_decoded():
    from custom_components.hoymiles_home.api import _decode_json
    from unittest.mock import patch
    with patch("custom_components.hoymiles_home.api.MAX_JSON_BYTES", 32):
        with pytest.raises(HoymilesConnectionError):
            _decode_json("[" + "0," * 100 + "0]", allow_array=True)
    api = ready(ok(json.dumps(json.dumps({"id": 123, "classify": 5}))))
    with pytest.raises(HoymilesConnectionError):
        await api.async_device_tree(123)
    assert api._session.post.call_count == 1


@pytest.mark.parametrize("reason", ["invalid_enduser_metadata", "invalid_enduser_station_id",
                                    "invalid_enduser_classification", "invalid_enduser_tree"])
async def test_response_validation_is_not_displayed_as_transport_failure(hass, client, reason):
    from unittest.mock import patch
    from homeassistant.config_entries import SOURCE_USER
    from custom_components.hoymiles_home.const import DOMAIN
    client.async_validate_station.side_effect = CloudDiagnosticError(reason, "Invalid Enduser response")
    with patch("custom_components.hoymiles_home.config_flow.HoymilesHomeClient", return_value=client):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {
            "username": "synthetic@example.invalid", "password": SECRET, "client_profile": "enduser"})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"station_id": "123"})
    assert result["errors"] == {"base": "invalid_station_response"}
