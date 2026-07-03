# mypy: disable-error-code="attr-defined,call-arg"
"""Config flow for the BVG Berlin Connections integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector

from .bvg_api import find_stops
from .const import (
    CONF_DESTINATION_ID,
    CONF_DESTINATION_NAME,
    CONF_DURATION,
    CONF_MAX_CONNECTIONS,
    CONF_MAX_RESULTS,
    CONF_MODE,
    CONF_ORIGIN_ID,
    CONF_ORIGIN_NAME,
    CONF_TIME_SEL,
    CONF_WALKING_TIME,
    DOMAIN,
    MODE_CONNECTIONS,
    MODE_DEPARTURES,
)
from .sensor import TRANSPORT_TYPES_SCHEMA

_LOGGER = logging.getLogger(__name__)

CONF_SEARCH = "search"
CONF_SELECTED_STOP = "selected_stop"

# Steps keep found stops in the flow storage under these keys.
_FOUND_ORIGIN = "found_origin"
_FOUND_DESTINATION = "found_destination"


SEARCH_SCHEMA = vol.Schema({vol.Required(CONF_SEARCH): str})


MODE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODE): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    selector.SelectOptionDict(
                        value=MODE_DEPARTURES,
                        label="Departures from a single stop",
                    ),
                    selector.SelectOptionDict(
                        value=MODE_CONNECTIONS,
                        label="Connections from origin to destination",
                    ),
                ],
                mode=selector.SelectSelectorMode.LIST,
            )
        )
    }
)


def _stop_schema(stops: list[dict[str, Any]]) -> vol.Schema:
    options = [
        f"{s['name']} || {s['id']}" for s in stops
    ]
    return vol.Schema(
        {
            vol.Required(CONF_SELECTED_STOP): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        }
    )


def _connections_options_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_TIME_SEL, default="depart"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value="depart", label="Depart at"),
                        selector.SelectOptionDict(value="arrive", label="Arrive by"),
                    ],
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(CONF_DURATION, default=30): vol.All(
                vol.Coerce(int), vol.Range(min=5, max=240)
            ),
            vol.Optional(CONF_WALKING_TIME, default=0): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=120)
            ),
            vol.Optional(CONF_MAX_CONNECTIONS, default=5): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=8)
            ),
            **TRANSPORT_TYPES_SCHEMA,
        }
    )


def _departures_options_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(CONF_WALKING_TIME, default=0): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=120)
            ),
            vol.Optional(CONF_MAX_RESULTS, default=10): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=20)
            ),
            **TRANSPORT_TYPES_SCHEMA,
        }
    )


def _options_schema_for(mode: str) -> vol.Schema:
    if mode == MODE_DEPARTURES:
        return _departures_options_schema()
    return _connections_options_schema()


def _parse_selected(stop_str: str) -> tuple[str, str]:
    """Split 'Name || id' back into name and id."""
    name, _, stop_id = stop_str.partition(" || ")
    return name.strip(), stop_id.strip()


class BvgConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the BVG integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        self.data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: choose the sensor mode."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=MODE_SCHEMA)
        self.data[CONF_MODE] = user_input[CONF_MODE]
        return await self.async_step_origin_search()

    async def async_step_origin_search(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: search for the origin stop."""
        if user_input is None:
            return self.async_show_form(step_id="origin_search", data_schema=SEARCH_SCHEMA)

        session = async_get_clientsession(self.hass)
        stops = await find_stops(session, user_input[CONF_SEARCH])
        if not stops:
            return self.async_show_form(
                step_id="origin_search",
                data_schema=SEARCH_SCHEMA,
                errors={"base": "no_stops_found"},
                description_placeholders={"query": user_input[CONF_SEARCH]},
            )
        self.data[_FOUND_ORIGIN] = stops
        return await self.async_step_origin()

    async def async_step_origin(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: pick the origin stop from the results."""
        if user_input is None:
            return self.async_show_form(
                step_id="origin",
                data_schema=_stop_schema(self.data[_FOUND_ORIGIN]),
            )
        name, stop_id = _parse_selected(user_input[CONF_SELECTED_STOP])
        self.data[CONF_ORIGIN_NAME] = name
        self.data[CONF_ORIGIN_ID] = stop_id
        if self.data.get(CONF_MODE) == MODE_DEPARTURES:
            return await self.async_step_options()
        return await self.async_step_destination_search()

    async def async_step_destination_search(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4: search for the destination stop."""
        if user_input is None:
            return self.async_show_form(
                step_id="destination_search", data_schema=SEARCH_SCHEMA
            )
        session = async_get_clientsession(self.hass)
        stops = await find_stops(session, user_input[CONF_SEARCH])
        if not stops:
            return self.async_show_form(
                step_id="destination_search",
                data_schema=SEARCH_SCHEMA,
                errors={"base": "no_stops_found"},
                description_placeholders={"query": user_input[CONF_SEARCH]},
            )
        self.data[_FOUND_DESTINATION] = stops
        return await self.async_step_destination()

    async def async_step_destination(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 5: pick the destination stop."""
        if user_input is None:
            return self.async_show_form(
                step_id="destination",
                data_schema=_stop_schema(self.data[_FOUND_DESTINATION]),
            )
        name, stop_id = _parse_selected(user_input[CONF_SELECTED_STOP])
        self.data[CONF_DESTINATION_NAME] = name
        self.data[CONF_DESTINATION_ID] = stop_id
        return await self.async_step_options()

    async def async_step_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 6: choose travel options."""
        schema = _options_schema_for(self.data.get(CONF_MODE, MODE_CONNECTIONS))
        if user_input is None:
            return self.async_show_form(step_id="options", data_schema=schema)

        data: dict[str, Any] = {
            CONF_MODE: self.data[CONF_MODE],
            CONF_ORIGIN_NAME: self.data[CONF_ORIGIN_NAME],
            CONF_ORIGIN_ID: self.data[CONF_ORIGIN_ID],
            **user_input,
        }
        if self.data.get(CONF_MODE) == MODE_CONNECTIONS:
            data[CONF_DESTINATION_NAME] = self.data[CONF_DESTINATION_NAME]
            data[CONF_DESTINATION_ID] = self.data[CONF_DESTINATION_ID]
            title = f"{data[CONF_ORIGIN_NAME]} → {data[CONF_DESTINATION_NAME]}"
        else:
            title = data[CONF_ORIGIN_NAME]
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "BvgOptionsFlow":
        """Return the options flow handler."""
        return BvgOptionsFlow(config_entry)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration of options."""
        entry = self._get_reconfigure_entry()
        mode = entry.data.get(CONF_MODE, MODE_CONNECTIONS)
        schema = _options_schema_for(mode)
        if user_input is not None:
            data = dict(entry.data)
            data.update(user_input)
            return self.async_update_reload_and_abort(entry, data=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                schema,
                {k: v for k, v in entry.data.items() if k in _editable_for(mode)},
            ),
        )


def _editable_for(mode: str) -> set[str]:
    if mode == MODE_DEPARTURES:
        return {CONF_WALKING_TIME, CONF_MAX_RESULTS}
    return {CONF_TIME_SEL, CONF_DURATION, CONF_WALKING_TIME, CONF_MAX_CONNECTIONS}


class BvgOptionsFlow(config_entries.OptionsFlow):
    """Edit options for an existing BVG config entry."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        mode = self._config_entry.data.get(CONF_MODE, MODE_CONNECTIONS)
        editable = _editable_for(mode)
        if user_input is None:
            data = {
                k: v for k, v in self._config_entry.data.items()
                if k in editable
            }
            # also pick up anything previously saved in options
            data.update({
                k: v for k, v in self._config_entry.options.items()
                if k in editable
            })
            return self.async_show_form(
                step_id="init",
                data_schema=self.add_suggested_values_to_schema(
                    _options_schema_for(mode), data
                ),
            )
        return self.async_create_entry(title="", data=user_input)
