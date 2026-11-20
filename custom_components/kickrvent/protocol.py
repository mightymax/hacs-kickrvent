"""Independent, read-only DIRCON/WFTNP client. No HA dependencies.

Wire format: https://github.com/elfrances/wahoo-fitness-tnp
Only discovery, characteristic reads and notification subscriptions are allowed.
"""

from __future__ import annotations

import asyncio
import socket
import struct
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from uuid import UUID


def uuid(short: str) -> UUID:
    return UUID(f"0000{short}-0000-1000-8000-00805f9b34fb")


FTMS = uuid("1826")
DIS = uuid("180a")
CPS = uuid("1818")
BIKE = uuid("2ad2")
POWER = uuid("2a63")
SERIAL = uuid("2a25")
MODEL = uuid("2a24")
HEADER = struct.Struct("!BBBBH")
MAX_PAYLOAD = 8192


class ProtocolError(Exception):
    """Malformed, unsupported or rejected DIRCON data."""


class RequestError(ProtocolError):
    """A trainer rejected a request."""


@dataclass(frozen=True)
class Device:
    serial: str | None
    model: str | None
    measurement: UUID


def encode(kind: int, seq: int, data: bytes = b"", code: int = 0) -> bytes:
    """Construct a frame (also used by the test trainer)."""
    return HEADER.pack(1, kind, seq, code, len(data)) + data


def parse_bike(data: bytes) -> dict[str, float | int]:
    """Parse optional FTMS fields in BLE little-endian order, validating all lengths."""
    offset = 0

    def read(fmt: str):
        nonlocal offset
        size = struct.calcsize(fmt)
        if offset + size > len(data):
            raise ProtocolError("Truncated Indoor Bike Data")
        value = struct.unpack_from(fmt, data, offset)[0]
        offset += size
        return value

    def skip(size: int):
        nonlocal offset
        if offset + size > len(data):
            raise ProtocolError("Truncated optional Indoor Bike Data field")
        offset += size

    flags = read("<H")
    result: dict[str, float | int] = {}
    if not flags & 1:  # More Data bit is inverted for instantaneous speed.
        result["speed"] = read("<H") / 100
    if flags & 2:
        skip(2)
    if flags & 4:
        result["cadence"] = read("<H") / 2
    if flags & 8:
        skip(2)
    if flags & 16:
        skip(3)
    if flags & 32:
        skip(2)
    if flags & 64:
        result["power"] = read("<h")
    for bit, size in ((7, 2), (8, 5), (9, 1), (10, 1), (11, 2), (12, 2)):
        if flags & (1 << bit):
            skip(size)
    return result


class Client:
    """One connection, one reader, serialized requests and bounded buffers.

    Notifications are delivered synchronously: the consumer must only update a
    bounded latest-value buffer, never spawn a task or queue every measurement.
    """

    def __init__(self, on_data: Callable[[dict[str, float | int]], None], timeout: float = 5):
        self.on_data = on_data
        self.timeout = timeout
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending: tuple[int, int, asyncio.Future] | None = None
        self._lock = asyncio.Lock()
        self._seq = 0
        self._measurement: UUID | None = None
        self.closed = asyncio.Event()
        self.closed.set()
        self.error: Exception | None = None

    async def connect(self, host: str, port: int) -> None:
        await self.close()
        reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), self.timeout
        )
        sock = self._writer.get_extra_info("socket")
        if sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.closed.clear()
        self.error = None
        self._reader_task = asyncio.create_task(self._read(reader), name="kickrvent-reader")

    async def close(self) -> None:
        task, self._reader_task = self._reader_task, None
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        writer, self._writer = self._writer, None
        if writer:
            writer.close()
            with suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), 2)
        self._measurement = None
        self.closed.set()

    async def _read(self, reader: asyncio.StreamReader) -> None:
        try:
            while True:
                version, kind, seq, code, size = HEADER.unpack(await reader.readexactly(6))
                if version != 1 or size > MAX_PAYLOAD or kind not in range(1, 7):
                    raise ProtocolError("Invalid DIRCON header")
                data = await reader.readexactly(size)
                if kind == 6:
                    if code or len(data) < 16:
                        raise ProtocolError("Invalid notification")
                    char = UUID(bytes=data[:16])
                    if char != self._measurement:
                        continue
                    try:
                        if char == BIKE:
                            sample = parse_bike(data[16:])
                        elif char == POWER and len(data) >= 20:
                            sample = {"power": struct.unpack_from("<h", data, 18)[0]}
                        else:
                            raise ProtocolError("Truncated power notification")
                    except ProtocolError:
                        # A malformed measurement cannot renew field freshness.
                        continue
                    self.on_data(sample)
                elif self._pending and self._pending[:2] == (kind, seq):
                    future = self._pending[2]
                    if not future.done():
                        if code:
                            future.set_exception(RequestError(f"DIRCON {kind}: response {code}"))
                        else:
                            future.set_result(data)
        except asyncio.CancelledError:
            raise
        except (OSError, asyncio.IncompleteReadError, ProtocolError) as err:
            self.error = err
        finally:
            self.closed.set()
            if self._writer:
                self._writer.close()
            if self._pending and not self._pending[2].done():
                self._pending[2].set_exception(ConnectionError("DIRCON connection closed"))

    async def request(self, kind: int, data: bytes = b"") -> bytes:
        if kind not in (1, 2, 3, 5):
            raise ValueError("KickrVent only permits discovery, reads and subscriptions")
        async with self._lock:
            if not self._writer or self.closed.is_set():
                raise ConnectionError("Not connected")
            self._seq = (self._seq + 1) % 256
            future = asyncio.get_running_loop().create_future()
            self._pending = (kind, self._seq, future)
            try:
                async with asyncio.timeout(self.timeout):
                    self._writer.write(encode(kind, self._seq, data))
                    await self._writer.drain()
                    return await future
            except TimeoutError:
                # Never reuse a connection after a timeout: delayed replies must
                # not match a future request when the 8-bit sequence wraps.
                await self.close()
                raise
            finally:
                if not future.done():
                    future.cancel()
                self._pending = None

    async def services(self) -> set[UUID]:
        data = await self.request(1)
        if len(data) % 16:
            raise ProtocolError("Invalid service list")
        return {UUID(bytes=data[i : i + 16]) for i in range(0, len(data), 16)}

    async def characteristics(self, service: UUID) -> dict[UUID, int]:
        data = await self.request(2, service.bytes)
        if len(data) < 16 or data[:16] != service.bytes or (len(data) - 16) % 17:
            raise ProtocolError("Invalid characteristic list")
        return {UUID(bytes=data[i : i + 16]): data[i + 16] for i in range(16, len(data), 17)}

    async def read_text(self, char: UUID) -> str | None:
        data = await self.request(3, char.bytes)
        if len(data) < 16 or data[:16] != char.bytes:
            raise ProtocolError("Invalid characteristic read")
        value = data[16:].decode("utf-8", errors="replace").strip("\x00 \t\r\n")
        return value or None

    async def initialize(self, *, subscribe: bool = True) -> Device:
        services = await self.services()
        serial = model = None
        if DIS in services:
            chars = await self.characteristics(DIS)
            for char in (SERIAL, MODEL):
                if chars.get(char, 0) & 1:
                    value = await self.read_text(char)
                    if char == SERIAL:
                        serial = value
                    else:
                        model = value
        selected = None
        for service, char in ((FTMS, BIKE), (CPS, POWER)):
            if service in services and (await self.characteristics(service)).get(char, 0) & 4:
                selected = char
                break
        if selected is None:
            raise ProtocolError("No FTMS Indoor Bike Data or Cycling Power notifications")
        if subscribe:
            self._measurement = selected
            reply = await self.request(5, selected.bytes + b"\x01")
            if reply != selected.bytes:
                raise ProtocolError("Invalid subscription response")
        return Device(serial, model, selected)
