"""Config flow for Flight Watch."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_CALLSIGNS,
    CONF_MAX_SEEN,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    DEFAULT_MAX_SEEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import CannotConnect, InvalidData, fetch_aircraft_json, normalize

CALLSIGNS_SELECTOR = TextSelector(TextSelectorConfig(multiple=True))
SCAN_INTERVAL_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=5, max=300, step=1, unit_of_measurement="s", mode=NumberSelectorMode.BOX)
)
MAX_SEEN_SELECTOR = NumberSelector(
    NumberSelectorConfig(min=10, max=600, step=5, unit_of_measurement="s", mode=NumberSelectorMode.BOX)
)


def _clean_callsigns(values: list[str] | str | None) -> list[str]:
    """Normalize the watch list typed by the user (also accepts comma-separated text)."""
    if not values:
        return []
    if isinstance(values, str):
        values = [values]
    result: dict[str, None] = {}
    for value in values:
        for part in value.split(","):
            norm = normalize(part)
            if norm and norm != "*":
                result[norm] = None
    return list(result)


class FlightWatchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the aircraft.json URL and the first flights to watch."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL].strip()
            self._async_abort_entries_match({CONF_URL: url})
            try:
                await fetch_aircraft_json(async_get_clientsession(self.hass), url)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidData:
                errors["base"] = "invalid_data"
            else:
                return self.async_create_entry(
                    title=urlparse(url).hostname or "ADS-B receiver",
                    data={CONF_URL: url},
                    options={
                        CONF_CALLSIGNS: _clean_callsigns(user_input.get(CONF_CALLSIGNS)),
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                        CONF_MAX_SEEN: int(user_input[CONF_MAX_SEEN]),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
                vol.Optional(CONF_CALLSIGNS, default=[]): CALLSIGNS_SELECTOR,
                vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): SCAN_INTERVAL_SELECTOR,
                vol.Required(CONF_MAX_SEEN, default=DEFAULT_MAX_SEEN): MAX_SEEN_SELECTOR,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> FlightWatchOptionsFlow:
        """Return the options flow."""
        return FlightWatchOptionsFlow()


class FlightWatchOptionsFlow(OptionsFlow):
    """Edit the watched flights and polling settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_CALLSIGNS: _clean_callsigns(user_input.get(CONF_CALLSIGNS)),
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_MAX_SEEN: int(user_input[CONF_MAX_SEEN]),
                }
            )

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(CONF_CALLSIGNS, default=options.get(CONF_CALLSIGNS, [])): CALLSIGNS_SELECTOR,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): SCAN_INTERVAL_SELECTOR,
                vol.Required(
                    CONF_MAX_SEEN, default=options.get(CONF_MAX_SEEN, DEFAULT_MAX_SEEN)
                ): MAX_SEEN_SELECTOR,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
