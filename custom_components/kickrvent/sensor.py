"""Measurement sensors: no changing timestamp attributes and no forced updates."""

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPower, UnitOfSpeed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import KickrEntity


@dataclass(frozen=True, kw_only=True)
class Description(SensorEntityDescription):
    pass


SENSORS = (
    Description(
        key="speed",
        translation_key="speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
    Description(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
    ),
    Description(
        key="cadence",
        translation_key="cadence",
        native_unit_of_measurement="rpm",
        icon="mdi:rotate-right",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(KickrSensor(entry.runtime_data, description) for description in SENSORS)


class KickrSensor(KickrEntity, SensorEntity):
    def __init__(self, coordinator, description: Description):
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        return self.coordinator.data.connected and self.native_value is not None

    @property
    def native_value(self) -> float | int | None:
        return getattr(self.coordinator.data, self.entity_description.key)
