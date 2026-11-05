"""Permission to use the battery heater, not actual heater activity."""

from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .device_settings_entity import DeviceSettingsEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.device_controls:
        async_add_entities([HoymilesHeatingPermissionSwitch(coordinator, entry)])


class HoymilesHeatingPermissionSwitch(DeviceSettingsEntity, SwitchEntity):
    _attr_icon = "mdi:radiator"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "battery_heating", "heating")

    @property
    def is_on(self):
        state = self.manager.heating
        return state["enable"] == 1 if state is not None else None

    async def async_turn_on(self, **kwargs):
        await self._async_change(self.manager.async_set_heating(True))

    async def async_turn_off(self, **kwargs):
        await self._async_change(self.manager.async_set_heating(False))
