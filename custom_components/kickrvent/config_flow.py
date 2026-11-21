"""UI setup, mDNS discovery, options and host reconfiguration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations

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
from .discovery import DiscoveredTrainer, async_discover
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
        self._devices: dict[str, DiscoveredTrainer] | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return KickrOptionsFlow()

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is not None:
            choice = user_input["device"]
            if choice == "__manual__":
                return await self.async_step_manual()
            if choice == "__rescan__":
                self._devices = None
                return await self.async_step_user()
            device = (self._devices or {}).get(choice)
            if device is not None:
                self._defaults = {
                    "host": device.host,
                    "port": device.port,
                    "name": device.name,
                    CONF_SERIAL: device.serial,
                }
                return await self._connection_step("manual", self._defaults)
        if self._devices is None:
            try:
                self._devices = await async_discover(self.hass)
            except OSError:
                self._devices = {}
            configured = {entry.unique_id for entry in self._async_current_entries()}
            self._devices = {
                key: device
                for key, device in self._devices.items()
                if not device.serial or device.serial.casefold() not in configured
            }
        choices = {key: f"{device.name} ({device.host})" for key, device in self._devices.items()}
        options = [{"value": key, "label": label} for key, label in choices.items()]
        labels = await async_get_translations(
            self.hass, self.hass.config.language, "selector", {DOMAIN}
        )
        prefix = f"component.{DOMAIN}.selector.trainer.options."
        options.extend(
            [
                {"value": "__rescan__", "label": labels.get(prefix + "__rescan__", "Scan again")},
                {
                    "value": "__manual__",
                    "label": labels.get(prefix + "__manual__", "Enter address manually"),
                },
            ]
        )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "device", default=next(iter(choices), "__rescan__")
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options, mode=selector.SelectSelectorMode.DROPDOWN
                        )
                    )
                }
            ),
        )

    async def async_step_manual(self, user_input=None) -> FlowResult:
        return await self._connection_step("manual", user_input)

    async def async_step_discovery_confirm(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return await self._connection_step("manual", self._defaults)
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"name": self._defaults["name"]},
        )

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
        return await self.async_step_discovery_confirm()

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
                    await self.async_set_unique_id(serial.casefold(), raise_on_progress=False)
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
