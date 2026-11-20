"""UI setup, mDNS discovery, options and host reconfiguration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import (
    CONF_INTERVAL,
    CONF_SERIAL,
    CONF_SLEEP,
    CONF_STALE,
    DEFAULT_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SLEEP,
    DEFAULT_STALE,
    DOMAIN,
)
from .protocol import Client, ProtocolError


def connection_schema(defaults: dict) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("host", default=defaults.get("host", "")): vol.All(
                str, vol.Strip, vol.Length(min=1)
            ),
            vol.Required("port", default=defaults.get("port", DEFAULT_PORT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
            vol.Optional("name", default=defaults.get("name", "KICKR")): str,
            vol.Optional(CONF_SERIAL, default=defaults.get(CONF_SERIAL, "")): str,
        }
    )


async def probe(host: str, port: int):
    client = Client(lambda _: None)
    try:
        await client.connect(host, port)
        return await client.initialize(subscribe=False)
    finally:
        await client.close()


class KickrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._defaults: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return KickrOptionsFlow()

    async def async_step_user(self, user_input=None) -> FlowResult:
        return await self._connection_step("user", user_input)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> FlowResult:
        serial = str(discovery_info.properties.get("serial-number", "")).strip()
        self._defaults = {
            "host": discovery_info.host,
            "port": discovery_info.port or DEFAULT_PORT,
            "name": discovery_info.name.removesuffix("._wahoo-fitness-tnp._tcp.local."),
            CONF_SERIAL: serial,
        }
        if serial:
            await self.async_set_unique_id(serial.casefold())
            self._abort_if_unique_id_configured(
                updates={"host": discovery_info.host, "port": self._defaults["port"]}
            )
        self.context["title_placeholders"] = {"name": self._defaults["name"]}
        return await self.async_step_user()

    async def async_step_reconfigure(self, user_input=None) -> FlowResult:
        entry = self._get_reconfigure_entry()
        self._defaults = dict(entry.data)
        return await self._connection_step("reconfigure", user_input)

    async def _connection_step(self, step: str, user_input) -> FlowResult:
        errors = {}
        if user_input is not None:
            self._defaults.update(user_input)
            try:
                device = await probe(user_input["host"], user_input["port"])
                serial = (device.serial or user_input.get(CONF_SERIAL, "")).strip()
                if not serial:
                    errors["base"] = "serial_required"
                else:
                    await self.async_set_unique_id(serial.casefold())
                    data = {**user_input, CONF_SERIAL: serial, "model": device.model}
                    if step == "reconfigure":
                        self._abort_if_unique_id_mismatch()
                        return self.async_update_reload_and_abort(
                            self._get_reconfigure_entry(), data_updates=data
                        )
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input.get("name") or "KICKR", data=data
                    )
            except (OSError, TimeoutError):
                errors["base"] = "cannot_connect"
            except ProtocolError:
                errors["base"] = "unsupported_device"
        return self.async_show_form(
            step_id=step, data_schema=connection_schema(self._defaults), errors=errors
        )


class KickrOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        defaults = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_INTERVAL, default=defaults.get(CONF_INTERVAL, DEFAULT_INTERVAL)
                    ): vol.All(vol.Coerce(int), vol.Range(min=2, max=60)),
                    vol.Required(
                        CONF_STALE, default=defaults.get(CONF_STALE, DEFAULT_STALE)
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=300)),
                    vol.Required(
                        CONF_SLEEP, default=defaults.get(CONF_SLEEP, DEFAULT_SLEEP)
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
                }
            ),
        )
