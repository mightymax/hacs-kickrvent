"""Discovery uses HA's shared mDNS instance and cleans up its own browser."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from zeroconf import ServiceStateChange

from custom_components.kickrvent.discovery import SERVICE_TYPE, async_discover


async def test_discovery_resolves_metadata_and_ignores_removed_or_unresolved(hass):
    shared = SimpleNamespace(zeroconf=object())
    browser = SimpleNamespace(async_cancel=AsyncMock())

    def create_browser(zc, service_type, handlers):
        assert zc is shared.zeroconf
        assert service_type == SERVICE_TYPE
        for name in ["KICKR", "gone", "missing"]:
            handlers[0](
                zeroconf=zc,
                service_type=service_type,
                name=f"{name}.{SERVICE_TYPE}",
                state_change=ServiceStateChange.Added,
            )
        handlers[0](
            zeroconf=zc,
            service_type=service_type,
            name=f"gone.{SERVICE_TYPE}",
            state_change=ServiceStateChange.Removed,
        )
        return browser

    def info_factory(service_type, name):
        info = Mock()
        info.async_request = AsyncMock(return_value=not name.startswith("missing."))
        info.parsed_addresses.return_value = ["192.0.2.25"]
        info.properties = {b"serial-number": b"TEST123"}
        info.port = 36866
        return info

    with (
        patch(
            "custom_components.kickrvent.discovery.async_get_async_instance", return_value=shared
        ),
        patch(
            "custom_components.kickrvent.discovery.AsyncServiceBrowser", side_effect=create_browser
        ),
        patch("custom_components.kickrvent.discovery.AsyncServiceInfo", side_effect=info_factory),
        patch("custom_components.kickrvent.discovery.asyncio.sleep", new=AsyncMock()),
    ):
        devices = await async_discover(hass)
    assert len(devices) == 1
    device = devices[f"KICKR.{SERVICE_TYPE}"]
    assert (device.name, device.host, device.port, device.serial) == (
        "KICKR",
        "192.0.2.25",
        36866,
        "TEST123",
    )
    browser.async_cancel.assert_awaited_once()


async def test_cancelled_scan_cancels_browser(hass):
    browser = SimpleNamespace(async_cancel=AsyncMock())
    with (
        patch(
            "custom_components.kickrvent.discovery.async_get_async_instance",
            return_value=SimpleNamespace(zeroconf=object()),
        ),
        patch("custom_components.kickrvent.discovery.AsyncServiceBrowser", return_value=browser),
        patch(
            "custom_components.kickrvent.discovery.asyncio.sleep",
            side_effect=asyncio.CancelledError,
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await async_discover(hass)
    browser.async_cancel.assert_awaited_once()
