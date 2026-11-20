"""Push coordinator with independent connection health and publication clocks."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from contextlib import suppress

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    CONF_INTERVAL,
    CONF_SLEEP,
    CONF_STALE,
    DEFAULT_INTERVAL,
    DEFAULT_SLEEP,
    DEFAULT_STALE,
)
from .protocol import Client, ProtocolError
from .telemetry import Snapshot, Telemetry

_LOGGER = logging.getLogger(__name__)


class KickrCoordinator(DataUpdateCoordinator[Snapshot]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(hass, _LOGGER, name="KickrVent", config_entry=entry, always_update=False)
        self.entry = entry
        self.telemetry = Telemetry(
            entry.options.get(CONF_INTERVAL, DEFAULT_INTERVAL),
            entry.options.get(CONF_STALE, DEFAULT_STALE),
            entry.options.get(CONF_SLEEP, DEFAULT_SLEEP),
        )
        self.client = Client(lambda sample: self.telemetry.ingest(sample, time.monotonic()))
        self.connected = False
        self.data = Snapshot()
        self._tasks: list[asyncio.Task] = []
        self._reported_failure = False

    def start(self) -> None:
        for coro, name in ((self._run(), "connection"), (self._tick(), "publication")):
            self._tasks.append(
                self.entry.async_create_background_task(self.hass, coro, f"kickrvent-{name}")
            )

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.client.close()

    def _publish(self) -> None:
        snapshot = self.telemetry.publish(time.monotonic(), self.connected)
        if snapshot is not None:
            self.async_set_updated_data(snapshot)

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(1)
            self._publish()

    async def _run(self) -> None:
        delay = 2.0
        try:
            while True:
                started = time.monotonic()
                try:
                    await self.client.connect(self.entry.data["host"], self.entry.data["port"])
                    device = await self.client.initialize()
                    if (
                        device.serial
                        and device.serial.casefold() != self.entry.data["serial"].casefold()
                    ):
                        raise ProtocolError(
                            "Trainer serial number does not match the configured device"
                        )
                    self.connected = True
                    self._publish()
                    if self._reported_failure:
                        _LOGGER.info("KICKR connection restored")
                        self._reported_failure = False
                    while True:
                        try:
                            await asyncio.wait_for(self.client.closed.wait(), timeout=20)
                            raise ConnectionError("Trainer closed the connection")
                        except TimeoutError:
                            # Discovery is read-only and works even when not pedalling.
                            await self.client.services()
                except (OSError, TimeoutError, ProtocolError) as err:
                    # One warning per outage; retries only at debug level.
                    if not self._reported_failure:
                        _LOGGER.warning(
                            "KICKR unavailable; reconnecting in the background: %s", err
                        )
                        self._reported_failure = True
                    else:
                        _LOGGER.debug("KICKR reconnect failed: %s", err)
                finally:
                    self.connected = False
                    self.telemetry.reset()
                    self._publish()
                    await self.client.close()
                if time.monotonic() - started > 60:
                    delay = 2.0
                await asyncio.sleep(delay + random.uniform(0, delay * 0.2))
                delay = min(delay * 2, 60)
        finally:
            self.connected = False
            with suppress(Exception):
                await self.client.close()
