import asyncio
import struct

import pytest

from custom_components.kickrvent.protocol import BIKE, Client, ProtocolError, encode, parse_bike

from .conftest import running_trainer


def test_optional_offsets_and_signed_power():
    data = struct.pack("<HHHHH", 0x7E, 3210, 3000, 181, 180) + b"\0" * 5 + struct.pack("<h", -12)
    assert parse_bike(data) == {"speed": 32.1, "cadence": 90.5, "power": -12}
    assert parse_bike(struct.pack("<Hh", 0x41, 250)) == {"power": 250}
    for length in range(len(data)):
        with pytest.raises(ProtocolError):
            parse_bike(data[:length])


def test_all_optional_fields_are_validated():
    # All flags except More Data: 2 + 2 + 2 + 2 + 2 + 3 + 2 + 2 + 2 + 5 + 1 + 1 + 2 + 2
    packet = struct.pack("<H", 0x1FFE) + b"\0" * 28
    assert parse_bike(packet) == {"speed": 0, "cadence": 0, "power": 0}
    with pytest.raises(ProtocolError):
        parse_bike(packet[:-1])


async def test_handshake_fragmented_frames_and_notifications(trainer):
    samples = []
    client = Client(samples.append)
    try:
        await client.connect("127.0.0.1", trainer.port)
        device = await client.initialize()
        assert device.serial == trainer.serial
        assert device.measurement == BIKE
        await trainer.emit()
        for _ in range(10):
            await asyncio.sleep(0)
            if samples:
                break
        assert samples == [{"speed": 31.2, "power": 225, "cadence": 88}]
        assert all(kind in (1, 2, 3, 5) for kind, _ in trainer.requests)
        assert [payload for kind, payload in trainer.requests if kind == 5] == [
            BIKE.bytes + b"\x01"
        ]
        with pytest.raises(ValueError, match="only permits"):
            await client.request(4, b"forbidden")
    finally:
        await client.close()
    assert client._reader_task is None


async def test_power_only_fallback():
    async with running_trainer(power_only=True) as trainer:
        event = asyncio.Event()
        samples = []

        def received(sample):
            samples.append(sample)
            event.set()

        client = Client(received)
        try:
            await client.connect("127.0.0.1", trainer.port)
            await client.initialize()
            await trainer.emit(power=190)
            await asyncio.wait_for(event.wait(), 1)
            assert samples == [{"power": 190}]
        finally:
            await client.close()


async def test_timeout_closes_session_and_fails_pending_request():
    stopped = asyncio.Event()

    async def silent(reader, writer):
        try:
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
            stopped.set()

    server = await asyncio.start_server(silent, "127.0.0.1", 0)
    client = Client(lambda _: None, timeout=0.03)
    try:
        await client.connect("127.0.0.1", server.sockets[0].getsockname()[1])
        with pytest.raises(TimeoutError):
            await client.services()
        assert client.closed.is_set()
        assert client._reader_task is None
        with pytest.raises(ConnectionError):
            await client.services()
    finally:
        await client.close()
        server.close()
        await server.wait_closed()
        await asyncio.wait_for(stopped.wait(), 1)


@pytest.mark.parametrize(
    "packet",
    [encode(1, 1, b"x"), bytes([2, 1, 1, 0, 0, 0]), struct.pack("!BBBBH", 1, 1, 1, 0, 9000)],
)
async def test_malformed_headers_and_service_lists(packet):
    async def broken(reader, writer):
        await reader.read(100)
        writer.write(packet)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(broken, "127.0.0.1", 0)
    client = Client(lambda _: None, timeout=1)
    try:
        await client.connect("127.0.0.1", server.sockets[0].getsockname()[1])
        with pytest.raises((ProtocolError, ConnectionError)):
            await client.services()
    finally:
        await client.close()
        server.close()
        await server.wait_closed()
