"""Register the station first and link inverter sensors without deprecated keys."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.const import UnitOfTemperature
from homeassistant.components.sensor import SensorDeviceClass
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hoymiles_home import async_setup_entry as real_setup_entry
from custom_components.hoymiles_home.const import DOMAIN
from custom_components.hoymiles_home.coordinator import HoymilesHomeCoordinator
from custom_components.hoymiles_home.sensor import HoymilesModuleSensor, HoymilesInverterDetailSensor, MODULE_SENSORS


@pytest.mark.parametrize("model", ["HMS-800-2WB", "HMS-2000-4WB"])
async def test_inverter_child_links_use_real_station_registry_id(hass, model, caplog):
    entry = MockConfigEntry(domain=DOMAIN, data={
        "username": "test@example.com", "password": "synthetic", "station_id": 123,
    })
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)

    async def forward(config_entry, platforms):
        assert registry.async_get_device_by_identifier((DOMAIN, "station_123"), entry.entry_id) is not None

    with (
        patch.object(HoymilesHomeCoordinator, "async_initialize", new=AsyncMock()),
        patch.object(HoymilesHomeCoordinator, "async_config_entry_first_refresh", new=AsyncMock()),
        patch.object(hass.config_entries, "async_forward_entry_setups", new=AsyncMock(side_effect=forward)),
    ):
        assert await real_setup_entry(hass, entry)
    coordinator = hass.data[DOMAIN][entry.entry_id]
    parent = registry.async_get_device_by_identifier((DOMAIN, "station_123"), entry.entry_id)
    inverter = {"id": 42, "sn": "ABCDEF000001", "model_no": model}
    module = HoymilesModuleSensor(coordinator, entry, inverter, 1, *MODULE_SENSORS[0])
    detail = HoymilesInverterDetailSensor(coordinator, entry, inverter, "temperature",
        UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE)
    for entity in (module, detail):
        info = dict(entity.device_info)
        assert "via_device" not in info
        assert info["via_device_id"] == parent.id
        child = registry.async_get_or_create(config_entry_id=entry.entry_id, **info)
        assert child.via_device_id == parent.id
    assert "deprecated 'via_device'" not in caplog.text
    await coordinator.async_shutdown()
