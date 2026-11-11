"""First-setup retries must not drop a long live-server waiting deadline."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components import hoymiles_home as integration
from custom_components.hoymiles_home import async_setup_entry as real_setup
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.errors import HoymilesLivePending

SECRET = "PRIVATE_ACCOUNT_PASSWORD_TOKEN"


@pytest.mark.parametrize("change", [None, "station_id", "client_profile", "password"])
async def test_setup_deadline_survives_retries_but_not_target_changes(hass, monkeypatch, change):
    entry = MockConfigEntry(domain=DOMAIN, data={
        "username": SECRET, "password": SECRET, "station_id": 123,
    })
    entry.add_to_hass(hass)
    clock = [100.0]
    monkeypatch.setattr(integration, "monotonic", lambda: clock[0])
    client = MagicMock()
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr(integration, "HoymilesHomeClient", constructor)
    coordinator = MagicMock()
    coordinator.async_initialize = AsyncMock()
    coordinator.async_shutdown = AsyncMock()
    coordinator.async_config_entry_first_refresh = AsyncMock(side_effect=ConfigEntryNotReady())
    coordinator.last_exception = UpdateFailed("Pending live data", retry_after=86400)
    coordinator.last_exception.__cause__ = HoymilesLivePending(3 * 86400)
    monkeypatch.setattr(integration, "HoymilesHomeCoordinator", MagicMock(return_value=coordinator))
    with pytest.raises(ConfigEntryNotReady):
        await real_setup(hass, entry)
    assert constructor.call_count == 1
    assert SECRET not in json.dumps(hass.data[DOMAIN]["_live_setup_waits"])
    assert entry.entry_id not in hass.data[DOMAIN]
    coordinator.async_shutdown.assert_awaited_once()

    clock[0] += 86400
    with pytest.raises(ConfigEntryNotReady):
        await real_setup(hass, entry)
    assert constructor.call_count == 1
    if change:
        value = {"station_id": 456, "client_profile": "installer", "password": "changed"}[change]
        hass.config_entries.async_update_entry(entry, data={**entry.data, change: value})
    else:
        clock[0] += 2 * 86400
    with pytest.raises(ConfigEntryNotReady):
        await real_setup(hass, entry)
    assert constructor.call_count == 2
    await integration.async_remove_entry(hass, entry)
    assert entry.entry_id not in hass.data[DOMAIN]["_live_setup_waits"]


async def test_reload_preserves_active_wait_before_new_client_or_http(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={
        "username": SECRET, "password": SECRET, "station_id": 123,
    })
    entry.add_to_hass(hass)
    monkeypatch.setattr(integration, "monotonic", lambda: 100.0)
    callbacks = []
    monkeypatch.setattr(entry, "async_on_unload", callbacks.append)
    client = MagicMock()
    client.live_pending_seconds.return_value = 60
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr(integration, "HoymilesHomeClient", constructor)
    coordinator = MagicMock()
    coordinator.async_initialize = AsyncMock()
    coordinator.async_shutdown = AsyncMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    monkeypatch.setattr(integration, "HoymilesHomeCoordinator", MagicMock(return_value=coordinator))
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock())
    assert await real_setup(hass, entry)
    for callback in callbacks:
        callback()
    hass.data[DOMAIN].pop(entry.entry_id)
    assert SECRET not in json.dumps(hass.data[DOMAIN]["_live_setup_waits"])
    with pytest.raises(ConfigEntryNotReady):
        await real_setup(hass, entry)
    assert constructor.call_count == 1
    await integration.async_remove_entry(hass, entry)


async def test_real_ha_first_refresh_preserves_pending_cause_and_prevents_setup_http(hass, monkeypatch):
    entry = MockConfigEntry(domain=DOMAIN, data={
        "username": SECRET, "password": SECRET, "station_id": 123,
    })
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_live.side_effect = HoymilesLivePending(3600)
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr(integration, "HoymilesHomeClient", constructor)
    monkeypatch.setattr(integration, "async_setup_entry", real_setup)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    client.async_live.assert_awaited_once_with(123)
    assert entry.entry_id in hass.data[DOMAIN]["_live_setup_waits"]
    assert not await hass.config_entries.async_reload(entry.entry_id)
    assert constructor.call_count == 1
    assert client.async_live.await_count == 1
    await hass.config_entries.async_remove(entry.entry_id)
    assert entry.entry_id not in hass.data[DOMAIN]["_live_setup_waits"]
