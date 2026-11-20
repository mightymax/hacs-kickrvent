"""Connectivity and pedalling/activity sensors."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import KickrEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(KickrBinary(entry.runtime_data, key) for key in ("connected", "active"))


class KickrBinary(KickrEntity, BinarySensorEntity):
    def __init__(self, coordinator, key: str):
        super().__init__(coordinator, key)
        self._key = key
        self._attr_translation_key = key
        if key == "connected":
            self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        else:
            self._attr_icon = "mdi:bike"

    @property
    def available(self) -> bool:
        if self._key == "connected":
            return True
        return self.coordinator.data.connected and self.coordinator.data.active is not None

    @property
    def is_on(self) -> bool | None:
        return getattr(self.coordinator.data, self._key)
