"""RGB and brightness settings for the battery's indicator strip."""

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ColorMode, LightEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .device_settings import STRIP_FIELDS
from .device_settings_entity import DeviceSettingsEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.device_controls:
        async_add_entities([HoymilesIndicatorLight(coordinator, entry)])


class HoymilesIndicatorLight(DeviceSettingsEntity, LightEntity):
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_icon = "mdi:led-strip-variant"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "battery_indicator")

    @property
    def available(self):
        return super().available and STRIP_FIELDS.keys() <= self.values.keys()

    @property
    def brightness(self):
        return self.values.get("slb")

    @property
    def rgb_color(self):
        return tuple(self.values[key] for key in ("r", "g", "b")) if all(key in self.values for key in ("r", "g", "b")) else None

    @property
    def is_on(self):
        return self.brightness > 0 if self.brightness is not None else None

    async def async_turn_on(self, **kwargs):
        if not kwargs.keys() <= {ATTR_BRIGHTNESS, ATTR_RGB_COLOR}:
            raise HomeAssistantError("Unsupported battery indicator option")
        updates = {"slb": kwargs[ATTR_BRIGHTNESS]} if ATTR_BRIGHTNESS in kwargs else {}
        if ATTR_RGB_COLOR in kwargs:
            color = kwargs[ATTR_RGB_COLOR]
            if not isinstance(color, (tuple, list)) or len(color) != 3:
                raise HomeAssistantError("Invalid battery indicator color")
            updates.update(zip(("r", "g", "b"), color))
        await self._async_change(self.manager.async_set_lighting(updates, turn_on=True))

    async def async_turn_off(self, **kwargs):
        if kwargs:
            raise HomeAssistantError("Unsupported battery indicator option")
        await self._async_change(self.manager.async_set_lighting({"slb": 0}))
