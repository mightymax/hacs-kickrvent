"""HA runtime fixtures and a deterministic TCP trainer, no physical device needed."""

import asyncio
import struct
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from uuid import UUID

import pytest

from custom_components.kickrvent.protocol import BIKE, CPS, DIS, FTMS, MODEL, POWER, SERIAL, encode


@pytest.fixture(autouse=True)
def custom_integrations(
    enable_custom_integrations, socket_enabled, mock_zeroconf, mock_async_zeroconf
):
    yield


@dataclass
class FakeTrainer:
    serial: str | None = "TEST-KICKR-001"
    power_only: bool = False
    requests: list = field(default_factory=list)
    writers: set = field(default_factory=set)
    connections: int = 0
    port: int = 0

    async def handle(self, reader, writer):
        self.connections += 1
        self.writers.add(writer)
        try:
            while True:
                _, kind, seq, _, size = struct.unpack("!BBBBH", await reader.readexactly(6))
                data = await reader.readexactly(size)
                self.requests.append((kind, data))
                if kind == 1:
                    reply = DIS.bytes + (CPS if self.power_only else FTMS).bytes
                elif kind == 2:
                    service = UUID(bytes=data)
                    chars = (
                        [(MODEL, 1)] + ([(SERIAL, 1)] if self.serial else [])
                        if service == DIS
                        else [(POWER if self.power_only else BIKE, 4)]
                    )
                    reply = data + b"".join(
                        char.bytes + bytes([properties]) for char, properties in chars
                    )
                elif kind == 3:
                    reply = (
                        data + (self.serial if data == SERIAL.bytes else "KICKR v6 test").encode()
                    )
                elif kind == 5:
                    reply = data[:16]
                else:
                    raise AssertionError(f"Control request sent: {kind}")
                packet = encode(kind, seq, reply)
                writer.write(packet[:3])
                await writer.drain()
                await asyncio.sleep(0)
                writer.write(packet[3:])
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self.writers.discard(writer)
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()

    async def emit(self, speed=31.2, power=225, cadence=88):
        if self.power_only:
            data = POWER.bytes + struct.pack("<Hh", 0, power)
        else:
            data = BIKE.bytes + struct.pack(
                "<HHHh", 0x44, round(speed * 100), round(cadence * 2), power
            )
        for writer in list(self.writers):
            writer.write(encode(6, 0, data))
            await writer.drain()
        await asyncio.sleep(0)

    async def drop_connections(self):
        for writer in list(self.writers):
            writer.close()
            await writer.wait_closed()


@asynccontextmanager
async def running_trainer(**kwargs):
    trainer = FakeTrainer(**kwargs)
    server = await asyncio.start_server(trainer.handle, "127.0.0.1", 0)
    trainer.port = server.sockets[0].getsockname()[1]
    try:
        yield trainer
    finally:
        server.close()
        await server.wait_closed()
        await trainer.drop_connections()


@pytest.fixture
async def trainer():
    async with running_trainer() as device:
        yield device
