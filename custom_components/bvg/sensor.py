# mypy: disable-error-code="attr-defined"
"""Sensor platform for the BVG Berlin Connections integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.helpers.config_validation as cv

from .bvg_api import fetch_connections, products_bitmask
from .const import (
    CONF_DESTINATION_ID,
    CONF_DESTINATION_NAME,
    CONF_DURATION,
    CONF_MAX_CONNECTIONS,
    CONF_ORIGIN_ID,
    CONF_ORIGIN_NAME,
    CONF_TIME_SEL,
    CONF_TYPE_BUS,
    CONF_TYPE_IC,
    CONF_TYPE_ICE,
    CONF_TYPE_REGIONAL,
    CONF_TYPE_SUBURBAN,
    CONF_TYPE_SUBWAY,
    CONF_TYPE_TRAM,
    CONF_WALKING_TIME,
    DEFAULT_ICON,
    DOMAIN,
    FALLBACK_TIME,
    SCAN_INTERVAL,  # noqa: F401  (imported so HA picks up the interval)
)
from .connection import Connection

_LOGGER = logging.getLogger(__name__)

TRANSPORT_TYPES_SCHEMA = {
    vol.Optional(CONF_TYPE_SUBURBAN, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_SUBWAY, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_TRAM, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_BUS, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_REGIONAL, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_IC, default=True): cv.boolean,
    vol.Optional(CONF_TYPE_ICE, default=True): cv.boolean,
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BVG sensor from a config entry."""
    async_add_entities([BvgConnectionsSensor(config_entry)], True)


class BvgConnectionsSensor(SensorEntity):
    """Sensor that shows the next BVG connections from origin to destination."""

    _attr_attribution = "Data provided by www.bvg.de"
    connections: list[Connection] = []

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config = config_entry
        self._attr_unique_id = f"{DOMAIN}_{config_entry.entry_id}"
        self._attr_has_entity_name = True
        self._attr_name = "Next connection"
        self._session = None
        self.last_update_success: datetime | None = None
        self._attr_available = True

    @property
    def _data(self) -> dict[str, Any]:
        """Merged config-entry data + options (options take precedence)."""
        return {**self._config.data, **self._config.options}

    @property
    def session(self) -> Any:
        """Return the HA aiohttp session (set up in async_added_to_hass)."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)
        return self._session

    @property
    def icon(self) -> str:
        if self.connections:
            return self.connections[0].icon
        return DEFAULT_ICON

    @property
    def native_value(self) -> str:
        """Human-readable summary of the next connection."""
        if not self.connections:
            return "N/A"
        c = self.connections[0]
        delay = ""
        if c.dep_delay:
            delay = f" ({'+' if c.dep_delay > 0 else ''}{c.dep_delay}')"
        lines = " → ".join(leg.line_name for leg in c.legs)
        return f"{c.dep_time}{delay} → {c.arr_time} ({c.duration}m) {lines}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._data
        origin = data.get(CONF_ORIGIN_NAME)
        destination = data.get(CONF_DESTINATION_NAME)
        return {
            "origin": origin,
            "destination": destination,
            "from": origin,
            "to": destination,
            "time_selection": data.get(CONF_TIME_SEL, "depart"),
            "walking_time": data.get(CONF_WALKING_TIME, 0),
            "connections": [c.to_dict() for c in self.connections],
        }

    async def async_update(self) -> None:
        """Fetch new connections from the BVG API."""
        data = self._data
        products = products_bitmask(
            {k: bool(data.get(k, True)) for k in (
                CONF_TYPE_SUBURBAN, CONF_TYPE_SUBWAY, CONF_TYPE_TRAM,
                CONF_TYPE_BUS, CONF_TYPE_REGIONAL, CONF_TYPE_IC, CONF_TYPE_ICE,
            )}
        )
        result = await fetch_connections(
            self.session,
            data[CONF_ORIGIN_ID],
            data[CONF_DESTINATION_ID],
            time_sel=data.get(CONF_TIME_SEL, "depart"),
            products=products,
        )

        now = datetime.now()
        if result is None:
            # API failed: keep last good result for a grace period.
            if (
                self.connections
                and self.last_update_success
                and (now - self.last_update_success) <= FALLBACK_TIME
            ):
                self.connections = [
                    c for c in self.connections if (c.timestamp is None or c.timestamp >= now)
                ]
                if not self.connections:
                    self._attr_available = False
            else:
                self._attr_available = False
                self.connections = []
            return

        self._attr_available = True
        self.last_update_success = now

        walking = int(data.get(CONF_WALKING_TIME, 0) or 0)
        if walking:
            cutoff = now + timedelta(minutes=walking)
            result = [
                c for c in result
                if c.timestamp is None or c.timestamp >= cutoff
            ]

        max_conn = int(data.get(CONF_MAX_CONNECTIONS, 5) or 5)
        self.connections = result[:max_conn]
