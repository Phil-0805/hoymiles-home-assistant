"""Model discovery uses real web API field names, with mocked cloud boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.hoymiles_home.api import HoymilesHomeClient, HoymilesConnectionError
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.diagnostics import async_get_config_entry_diagnostics
from custom_components.hoymiles_home.inverter import inverter_model, inverter_ports
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.sensor import async_setup_entry, HoymilesModuleSensor


def client(*responses):
    api = HoymilesHomeClient(MagicMock(), "private@example.com", "secret")
    api._json = AsyncMock(side_effect=responses)
    return api


@pytest.mark.parametrize("model,ports", [("HMS-800-2WB", [1, 2]), ("HMS-2000-4WB", [1, 2, 3, 4])])
async def test_web_tree_model_no_is_used(model, ports):
    original = [{"type": 3, "id": 99, "sn": "PRIVATE"}]
    api = client({"status": "0", "data": [{"type": 1, "id": 1, "children": [
        {"type": 3, "id": 99, "sn": "PRIVATE", "model_no": model}
    ]}]})
    found = await api.async_enrich_inverters(123, original)
    assert inverter_model(found[0]) == model
    assert list(inverter_ports(found[0])) == ports
    assert found[0]["id"] == 99
    assert found[0]["sn"] == "PRIVATE"
    assert "model_no" not in original[0]
    assert found[0]["_model_discovery"]["source"] == "web_tree"
    api._json.assert_awaited_once_with(
        "https://neapi.hoymiles.com/pvm/api/0/station/select_device_of_tree", {"id": 123}
    )


async def test_detail_after_rejected_web_tree():
    api = client(HoymilesConnectionError("403"), {"status": "0", "data": {
        "id": 99, "sn": "PRIVATE", "model_no": "HMS-1000-2WB"
    }})
    found = await api.async_enrich_inverters(123, [{"type": 3, "id": 99, "sn": "PRIVATE"}])
    assert inverter_model(found[0]) == "HMS-1000-2WB"
    assert found[0]["_model_discovery"]["source"] == "micro_detail"
    assert api._json.await_args.args == (
        "https://neapi.hoymiles.com/pvm/api/0/dev/micro/find", {"id": 99, "sid": 123}
    )


@pytest.mark.parametrize("detail", [
    {"id": 98, "sn": "PRIVATE", "model_no": "HMS-1000-2WB"},
    {"id": 99, "sn": "WRONG", "model_no": "HMS-1000-2WB"},
    {"id": 99, "sn": "PRIVATE", "model_no": 42},
    None,
])
async def test_wrong_identity_or_absent_model_is_not_used(detail):
    api = client({"status": "0", "data": []}, {"status": "0", "data": detail})
    found = await api.async_enrich_inverters(123, [{"type": 3, "id": 99, "sn": "PRIVATE"}])
    assert inverter_model(found[0]) == "Hoymiles microinverter"
    assert found[0]["id"] == 99
    assert found[0]["sn"] == "PRIVATE"


async def test_optional_access_failure_does_not_fail_setup():
    api = client({"status": "1", "message": "forbidden"}, HoymilesConnectionError("403"))
    found = await api.async_enrich_inverters(123, [{"type": 3, "id": 99}])
    assert found[0]["_model_discovery"]["result"] == "unresolved"
    assert list(inverter_ports(found[0])) == [1, 2, 3, 4]


async def test_optional_timeout_does_not_fail_setup():
    api = client(TimeoutError())
    found = await api.async_enrich_inverters(123, [{"type": 3, "id": 99}])
    assert found[0]["_model_discovery"]["timeout"] is True


async def test_existing_model_needs_no_optional_requests():
    api = client()
    found = await api.async_enrich_inverters(123, [{"type": 3, "id": 99, "model_no": "HMS-2000-4WB"}])
    assert inverter_model(found[0]) == "HMS-2000-4WB"
    api._json.assert_not_awaited()


async def test_home_tree_is_enriched_before_entities_are_created(hass):
    """Exercise the API, coordinator and entity factory together."""
    api = client({"status": "0", "data": [{"id": 99, "type": 3, "model_no": "HMS-800-2WB"}]})
    api.async_live = AsyncMock(return_value={"power": {}})
    api.async_device_tree = AsyncMock(return_value=[{"id": 99, "type": 3}])
    api.async_station_realtime = AsyncMock(return_value={})
    api.async_module_values = AsyncMock(return_value={"MODULE_POWER": 125.0})
    coordinator = HoymilesHomeCoordinator(hass, api, 123)
    with patch.object(coordinator, "_async_refresh_battery_settings", new=AsyncMock()):
        coordinator.data = await coordinator._async_update_data()
        await hass.async_block_till_done()
    entry = SimpleNamespace(entry_id="existing", data={"station_id": 123})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entities = []
    await async_setup_entry(hass, entry, entities.extend)
    modules = [entity for entity in entities if isinstance(entity, HoymilesModuleSensor)]
    assert len(modules) == 6
    assert all(entity.device_info["model"] == "HMS-800-2WB" for entity in modules)
    assert [call.args[2] for call in api.async_module_values.await_args_list] == [1, 2]
    # Static metadata is not probed again on the fast live-data cycle.
    await coordinator._async_update_data()
    assert api._json.await_count == 1


async def test_diagnostics_export_no_raw_device_or_account_data(hass):
    entry = SimpleNamespace(entry_id="entry", data={"password": "SECRET", "username": "EMAIL"})
    coordinator = SimpleNamespace(inverters=[{
        "id": 123456, "sn": "PRIVATE-SERIAL", "name": "HOME ADDRESS", "token": "TOKEN",
        "model_no": "HMS-800-2WB", "_model_discovery": {
            "result": "identified", "source": "web_tree", "detail": "SECRET", "raw": "TOKEN"
        },
    }])
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result == {"inverters": [{"model": "HMS-800-2WB", "queried_pv_ports": [1, 2],
                                     "discovery": {"result": "identified", "source": "web_tree"}}]}
