"""Real HA config flows, entities and unload against a local TCP trainer."""

import asyncio
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kickrvent.const import DOMAIN
from custom_components.kickrvent.telemetry import Snapshot


async def wait_for(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.01)


async def test_setup_flow_options_and_duplicate(hass, trainer):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": "__manual__"}
    )
    assert result["step_id"] == "manual"
    inputs = {"host": "127.0.0.1", "port": trainer.port, "name": "My KICKR"}
    with patch("custom_components.kickrvent.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], inputs)
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    entry = result["result"]
    assert entry.unique_id == trainer.serial.casefold()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": "__manual__"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], inputs)
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"publish_interval": 10, "stale_timeout": 30, "sleep_timeout": 15}
    )
    assert result["type"] == "create_entry"
    assert entry.options["publish_interval"] == 10


async def test_real_platforms_publish_freshness_disconnect_and_unload(hass, trainer):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=trainer.serial.casefold(),
        title="Test KICKR",
        data={
            "host": "127.0.0.1",
            "port": trainer.port,
            "serial": trainer.serial,
            "model": "KICKR v6",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    await wait_for(lambda: coordinator.connected)
    await trainer.emit()
    await wait_for(lambda: "power" in coordinator.telemetry.values)
    coordinator.telemetry.last_publish = -100
    coordinator._publish()
    await hass.async_block_till_done()
    entities = list(hass.states.async_all())
    power_id = next(
        s.entity_id
        for s in entities
        if s.attributes.get("unit_of_measurement") == "W" and s.entity_id.startswith("sensor.")
    )
    assert hass.states.get(power_id).state == "225"
    assert "last_seen" not in hass.states.get(power_id).attributes
    connection_id = next(
        s.entity_id for s in entities if s.attributes.get("device_class") == "connectivity"
    )
    assert hass.states.get(connection_id).state == "on"
    coordinator.telemetry.values = {
        k: (v, t - 60) for k, (v, t) in coordinator.telemetry.values.items()
    }
    coordinator._publish()
    await hass.async_block_till_done()
    assert hass.states.get(power_id).state == "unavailable"
    await trainer.drop_connections()
    await wait_for(lambda: not coordinator.connected)
    assert coordinator.data == Snapshot()
    await hass.async_block_till_done()
    assert hass.states.get(connection_id).state == "off"
    await wait_for(lambda: coordinator.connected)
    assert trainer.connections == 2
    assert coordinator.data.power is None
    await trainer.emit(power=300)
    await wait_for(lambda: coordinator.telemetry.values.get("power", (None,))[0] == 300)
    coordinator.telemetry.last_publish = -100
    coordinator._publish()
    await hass.async_block_till_done()
    assert hass.states.get(power_id).state == "300"
    tasks = list(coordinator._tasks)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert all(task.done() for task in tasks)
    assert coordinator.client._reader_task is None


async def test_reconfigure_rejects_another_serial(hass, trainer):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="other-serial",
        data={
            "host": "127.0.0.1",
            "port": trainer.port,
            "serial": "other-serial",
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reconfigure", "entry_id": entry.entry_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "127.0.0.1", "port": trainer.port, "name": "KICKR"}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "unique_id_mismatch"


async def test_offline_setup_and_unload(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="offline",
        data={"host": "127.0.0.1", "port": 1, "serial": "offline"},
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.kickrvent.protocol.asyncio.open_connection",
            side_effect=ConnectionRefusedError,
        ),
        patch("custom_components.kickrvent.coordinator._LOGGER") as logger,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data
        await wait_for(lambda: logger.warning.call_count == 1)
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert not coordinator._tasks


async def test_retry_backoff_and_log_suppression(hass):
    from custom_components.kickrvent.coordinator import KickrCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="offline",
        data={"host": "127.0.0.1", "port": 1, "serial": "offline"},
    )
    entry.add_to_hass(hass)
    coordinator = KickrCoordinator(hass, entry)
    with (
        patch.object(coordinator.client, "connect", side_effect=ConnectionRefusedError),
        patch(
            "custom_components.kickrvent.coordinator.asyncio.sleep",
            side_effect=[None, None, asyncio.CancelledError],
        ) as sleep,
        patch("custom_components.kickrvent.coordinator.random.uniform", return_value=0),
        patch("custom_components.kickrvent.coordinator._LOGGER") as logger,
    ):
        import pytest

        with pytest.raises(asyncio.CancelledError):
            await coordinator._run()
        assert [call.args[0] for call in sleep.call_args_list] == [2, 4, 8]
        assert logger.warning.call_count == 1
        assert logger.debug.call_count == 2
    assert coordinator.client.closed.is_set()


async def test_zeroconf_updates_host_without_creating_duplicate(hass, trainer):
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=trainer.serial.casefold(),
        data={"host": "192.0.2.1", "port": 36866, "serial": trainer.serial},
    )
    entry.add_to_hass(hass)
    info = ZeroconfServiceInfo(
        ip_address="127.0.0.1",
        ip_addresses=["127.0.0.1"],
        port=trainer.port,
        hostname="kickr.local.",
        type="_wahoo-fitness-tnp._tcp.local.",
        name="KICKR._wahoo-fitness-tnp._tcp.local.",
        properties={"serial-number": trainer.serial},
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=info
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == "127.0.0.1"
    assert entry.data["port"] == trainer.port


async def test_user_selects_discovered_trainer_without_entering_address(hass, trainer):
    from custom_components.kickrvent.discovery import DiscoveredTrainer

    device = DiscoveredTrainer("KICKR test", "127.0.0.1", trainer.port, trainer.serial)
    with patch(
        "custom_components.kickrvent.config_flow.async_discover", return_value={"test": device}
    ):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    with patch("custom_components.kickrvent.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "test"}
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"]["host"] == "127.0.0.1"
    assert result["data"]["port"] == trainer.port
    assert result["data"]["serial"] == trainer.serial


async def test_user_can_rescan(hass, trainer):
    from custom_components.kickrvent.discovery import DiscoveredTrainer

    device = DiscoveredTrainer("KICKR test", "127.0.0.1", trainer.port, trainer.serial)
    with patch(
        "custom_components.kickrvent.config_flow.async_discover", side_effect=[{}, {"test": device}]
    ) as scan:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device": "__rescan__"}
        )
        assert result["type"] == "form"
        assert scan.call_count == 2
    assert result["data_schema"]({"device": "test"}) == {"device": "test"}
