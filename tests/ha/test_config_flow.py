"""Exercise setup using Home Assistant's flow manager and real selectors."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_home.api import HoymilesAuthError, HoymilesConnectionError
from custom_components.hoymiles_home.const import DOMAIN

CREDENTIALS = {"username": "User@example.com", "password": "test-password"}


async def login(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)


async def test_selects_station_and_preserves_existing_entry_schema(hass, client):
    result = await login(hass)
    assert result["step_id"] == "select_station"
    selector = next(iter(result["data_schema"].schema.values()))
    assert selector.config["options"] == [
        {"value": "123", "label": "Home (123)"},
        {"value": "456", "label": "Home (456)"},
    ]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": "456"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {**CREDENTIALS, "station_id": 456}
    assert result["result"].unique_id == "user@example.com_456"
    client.async_device_tree.assert_awaited_once_with(456)
    await hass.async_block_till_done()


async def test_allows_manual_id_in_dropdown(hass, client):
    result = await login(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": "789"}
    )
    assert result["data"]["station_id"] == 789
    client.async_device_tree.assert_awaited_once_with(789)
    await hass.async_block_till_done()


@pytest.mark.parametrize("discovery", [[], HoymilesConnectionError("Unavailable")])
async def test_discovery_fallback_keeps_working_manual_setup(hass, client, discovery):
    if isinstance(discovery, Exception):
        client.async_list_stations.side_effect = discovery
    else:
        client.async_list_stations.return_value = discovery
    result = await login(hass)
    assert result["step_id"] == "manual_station"
    assert result["errors"]["base"] in {"no_stations", "discovery_failed"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": 123}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    client.async_login.assert_awaited_once()
    await hass.async_block_till_done()


@pytest.mark.parametrize("station_id", ["not-an-id", "0", "-2", "1_2", "123.0"])
async def test_rejects_invalid_custom_ids_without_api_call(hass, client, station_id):
    result = await login(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": station_id}
    )
    assert result["step_id"] == "select_station"
    assert result["errors"] == {"station_id": "invalid_station_id"}
    client.async_device_tree.assert_not_awaited()


async def test_rejects_empty_device_tree_then_allows_retry(hass, client):
    client.async_device_tree.side_effect = [[], [{"id": 111}]]
    result = await login(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": "123"}
    )
    assert result["errors"] == {"base": "invalid_station"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": "456"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_existing_manual_entry_is_not_duplicated(hass, client):
    MockConfigEntry(
        domain=DOMAIN, unique_id="user@example.com_123",
        data={**CREDENTIALS, "station_id": 123},
    ).add_to_hass(hass)
    result = await login(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": "123"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_authentication_failure_does_not_attempt_discovery(hass, client):
    client.async_login.side_effect = HoymilesAuthError("Rejected")
    result = await login(hass)
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}
    client.async_list_stations.assert_not_awaited()


async def test_auth_expiry_returns_to_login(hass, client):
    result = await login(hass)
    client.async_device_tree.side_effect = HoymilesAuthError("Expired")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"station_id": "123"}
    )
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_discovery_auth_failure_requires_new_credentials(hass, client):
    client.async_list_stations.side_effect = HoymilesAuthError("Expired")
    result = await login(hass)
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}
