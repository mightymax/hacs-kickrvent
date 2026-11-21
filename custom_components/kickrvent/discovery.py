"""Bounded, on-demand mDNS discovery using Home Assistant's shared instance."""

import asyncio
from dataclasses import dataclass

from homeassistant.components.zeroconf import async_get_async_instance
from homeassistant.core import HomeAssistant
from zeroconf import IPVersion, ServiceStateChange
from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

SERVICE_TYPE = "_wahoo-fitness-tnp._tcp.local."
SCAN_SECONDS = 3
MAX_DEVICES = 32


@dataclass(frozen=True)
class DiscoveredTrainer:
    name: str
    host: str
    port: int
    serial: str


async def async_discover(hass: HomeAssistant) -> dict[str, DiscoveredTrainer]:
    """Scan once, resolve concurrently, and cancel only our own browser."""
    shared = await async_get_async_instance(hass)
    names: dict[str, None] = {}

    def changed(zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Removed:
            names.pop(name, None)
        elif len(names) < MAX_DEVICES:
            names[name] = None

    browser = AsyncServiceBrowser(shared.zeroconf, SERVICE_TYPE, handlers=[changed])
    try:
        await asyncio.sleep(SCAN_SECONDS)
    finally:
        await browser.async_cancel()

    async def resolve(name):
        info = AsyncServiceInfo(SERVICE_TYPE, name)
        if not await info.async_request(shared.zeroconf, 1500):
            return None
        addresses = info.parsed_addresses(IPVersion.V4Only) or info.parsed_scoped_addresses()
        if not addresses or not info.port:
            return None
        serial = info.properties.get(b"serial-number", b"")
        if isinstance(serial, bytes):
            serial = serial.decode("utf-8", errors="replace")
        return name, DiscoveredTrainer(
            name=name.removesuffix(f".{SERVICE_TYPE}"),
            host=addresses[0],
            port=info.port,
            serial=str(serial or "").strip(),
        )

    results = await asyncio.gather(
        *(resolve(name) for name in sorted(names)), return_exceptions=True
    )
    return dict(result for result in results if isinstance(result, tuple))
