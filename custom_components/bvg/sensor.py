# mypy: disable-error-code="attr-defined"
"""Sensor platform for the BVG Berlin Connections integration.

Supports two modes:
  * ``departures``  — upcoming departures from a single stop. Exposes a
    ``departures`` attribute in the same format as
    vas3k/home-assistant-berlin-transport so the existing Lovelace card works.
  * ``connections`` — next journeys from an origin to a destination. Exposes a
    ``connections`` attribute with legs, delays and durations.
"""
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

from .bvg_api import fetch_connections, fetch_departures, products_bitmask
from .connection import Connection
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
    MODE_CONNECTIONS,
    MODE_DEPARTURES,
    SCAN_INTERVAL,  # noqa: F401  (imported so HA picks up the interval)
)
from .departure import Departure

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

# Product keys that may be toggled in the options.
_ALL_PRODUCT_KEYS = (
    CONF_TYPE_SUBURBAN, CONF_TYPE_SUBWAY, CONF_TYPE_TRAM,
    CONF_TYPE_BUS, CONF_TYPE_REGIONAL, CONF_TYPE_IC, CONF_TYPE_ICE,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the BVG sensor from a config entry."""
    async_add_entities([BvgTransportSensor(config_entry)], True)


class BvgTransportSensor(SensorEntity):
    """Sensor showing upcoming BVG departures or connections."""

    _attr_attribution = "Data provided by www.bvg.de"
    connections: list[Connection] = []
    departures: list[Departure] = []

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config = config_entry
        self._attr_unique_id = f"{DOMAIN}_{config_entry.entry_id}"
        self._attr_has_entity_name = True
        self._session = None
        self.last_update_success: datetime | None = None
        self._attr_available = True

    @property
    def _data(self) -> dict[str, Any]:
        """Merged config-entry data + options (options take precedence)."""
        return {**self._config.data, **self._config.options}

    @property
    def _mode(self) -> str:
        return self._data.get(CONF_MODE, MODE_CONNECTIONS)

    @property
    def _is_departures(self) -> bool:
        return self._mode == MODE_DEPARTURES

    @property
    def session(self) -> Any:
        """Return the HA aiohttp session."""
        if self._session is None:
            self._session = async_get_clientsession(self.hass)
        return self._session

    @property
    def name(self) -> str:  # type: ignore[override]
        return "Next departure" if self._is_departures else "Next connection"

    @property
    def icon(self) -> str:
        if self._is_departures:
            return self.departures[0].icon if self.departures else DEFAULT_ICON
        return self.connections[0].icon if self.connections else DEFAULT_ICON

    @property
    def native_value(self) -> str:
        """Human-readable summary of the next departure / connection."""
        if self._is_departures:
            if not self.departures:
                return "N/A"
            d = self.departures[0]
            delay = f" ({'+' if (d.delay or 0) > 0 else ''}{d.delay}')" if d.delay else ""
            return f"Next {d.line_name} at {d.time}{delay}"
        if not self.connections:
            return "N/A"
        c = self.connections[0]
        delay = f" ({'+' if (c.dep_delay or 0) > 0 else ''}{c.dep_delay}')" if c.dep_delay else ""
        lines = " → ".join(leg.line_name for leg in c.legs)
        return f"{c.dep_time}{delay} → {c.arr_time} ({c.duration}m) {lines}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._data
        origin = data.get(CONF_ORIGIN_NAME)
        attrs: dict[str, Any] = {
            "origin": origin,
            "from": origin,
            "mode": self._mode,
            "walking_time": data.get(CONF_WALKING_TIME, 0),
        }
        if self._is_departures:
            attrs["to"] = None
            walking = int(data.get(CONF_WALKING_TIME, 0) or 0)
            attrs["departures"] = [d.to_dict(walking) for d in self.departures]
        else:
            destination = data.get(CONF_DESTINATION_NAME)
            attrs["to"] = destination
            attrs["destination"] = destination
            attrs["time_selection"] = data.get(CONF_TIME_SEL, "depart")
            attrs["connections"] = [c.to_dict() for c in self.connections]
        return attrs

    async def async_update(self) -> None:
        """Fetch new data from the BVG API."""
        if self._is_departures:
            await self._update_departures()
        else:
            await self._update_connections()

    # -- departures mode -------------------------------------------------

    async def _update_departures(self) -> None:
        data = self._data
        max_results = int(data.get(CONF_MAX_RESULTS, 10) or 10)
        # The API caps maxJourneys; fetch a few extra so product/walking
        # filters still leave enough entries.
        fetch_n = min(max(max_results, 10), 20)
        result = await fetch_departures(
            self.session,
            data[CONF_ORIGIN_NAME],
            max_journeys=fetch_n,
        )
        await self._apply_result(
            result,
            apply_filters=lambda items: self._filter_departures(items),
        )

    def _filter_departures(self, departures: list[Departure]) -> list[Departure]:
        data = self._data
        enabled = {k: bool(data.get(k, True)) for k in _ALL_PRODUCT_KEYS}
        walking = int(data.get(CONF_WALKING_TIME, 0) or 0)
        now = datetime.now()
        cutoff = now + timedelta(minutes=walking)
        max_results = int(data.get(CONF_MAX_RESULTS, 10) or 10)
        filtered = [
            d for d in departures
            if enabled.get(d.line_type, True)
            and (d.timestamp is None or d.timestamp >= cutoff)
        ]
        return filtered[:max_results]

    # -- connections mode ------------------------------------------------

    async def _update_connections(self) -> None:
        data = self._data
        products = products_bitmask(
            {k: bool(data.get(k, True)) for k in _ALL_PRODUCT_KEYS}
        )
        result = await fetch_connections(
            self.session,
            data[CONF_ORIGIN_ID],
            data[CONF_DESTINATION_ID],
            time_sel=data.get(CONF_TIME_SEL, "depart"),
            products=products,
        )
        await self._apply_result(
            result,
            apply_filters=lambda items: self._filter_connections(items),
        )

    def _filter_connections(self, connections: list[Connection]) -> list[Connection]:
        data = self._data
        walking = int(data.get(CONF_WALKING_TIME, 0) or 0)
        now = datetime.now()
        cutoff = now + timedelta(minutes=walking)
        max_conn = int(data.get(CONF_MAX_CONNECTIONS, 5) or 5)
        filtered = [
            c for c in connections
            if c.timestamp is None or c.timestamp >= cutoff
        ]
        return filtered[:max_conn]

    # -- shared error/fallback handling ----------------------------------

    async def _apply_result(self, result, apply_filters) -> None:
        """Store a freshly fetched result, with graceful fallback on failure.

        ``result`` is None on API failure, otherwise a list of Connection or
        Departure. ``apply_filters`` maps the raw list to the filtered list
        to keep, and also prunes past entries during the fallback window.
        """
        now = datetime.now()
        if result is None:
            current = self.departures if self._is_departures else self.connections
            if (
                current
                and self.last_update_success
                and (now - self.last_update_success) <= FALLBACK_TIME
            ):
                kept = apply_filters(current)
                self._store(kept)
                if not kept:
                    self._attr_available = False
            else:
                self._attr_available = False
                self._store([])
            return

        self._attr_available = True
        self.last_update_success = now
        self._store(apply_filters(result))

    def _store(self, items) -> None:
        if self._is_departures:
            self.departures = items  # type: ignore[assignment]
        else:
            self.connections = items  # type: ignore[assignment]
