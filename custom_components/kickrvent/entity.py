"""Shared stable entity identity and device information."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import KickrCoordinator


class KickrEntity(CoordinatorEntity[KickrCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: KickrCoordinator, key: str):
        super().__init__(coordinator)
        serial = coordinator.entry.data["serial"]
        self._attr_unique_id = f"{serial.casefold()}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial.casefold())},
            name=coordinator.entry.title,
            manufacturer="Wahoo",
            model=coordinator.entry.data.get("model") or "KICKR (WFTNP)",
            serial_number=serial,
        )
