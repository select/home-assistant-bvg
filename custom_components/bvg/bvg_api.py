"""Async client for the reverse-engineered www.bvg.de connection-search API."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import aiohttp
import async_timeout

from .const import (
    ALL_PRODUCTS,
    CONNECTIONS_URL,
    DEPARTUREBOARD_URL,
    LOCATIONS_URL,
    PRODUCT_BITS,
    REFERER,
)
from .connection import Connection
from .departure import Departure

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": REFERER,
}


async def find_stops(
    session: aiohttp.ClientSession, query: str, lang: str = "de"
) -> list[dict[str, Any]]:
    """Resolve a station name to a list of stops via the BVG location search."""
    url = LOCATIONS_URL.format(lang=lang) + "?" + urlencode({"input": query})
    try:
        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            resp = await session.get(url, headers=_HEADERS)
            resp.raise_for_status()
            data = await resp.json()
    except (aiohttp.ClientError, TimeoutError) as ex:
        _LOGGER.warning("BVG location search error for %r: %s", query, ex)
        return []

    return [
        {"name": s.get("name"), "id": s.get("id"), "type": s.get("type")}
        for s in (data or [])
        if s.get("id")
    ]


def products_bitmask(enabled: dict[str, bool]) -> int:
    """Build the HAFAS product bitmask from a {product: bool} map."""
    bits = 0
    for key, on in enabled.items():
        if on and key in PRODUCT_BITS:
            bits |= PRODUCT_BITS[key]
    return bits or ALL_PRODUCTS


async def fetch_departures(
    session: aiohttp.ClientSession,
    location: str,
    *,
    max_journeys: int = 10,
    lang: str = "de",
) -> list[Departure] | None:
    """Fetch upcoming departures from a single stop.

    ``location`` is the BVG station id (the ``A=1@O=...@L=...`` string from
    the location search). The departureBoard endpoint accepts this id as the
    ``locationName`` parameter and returns departures for *any* stop — minor
    stops like "Im Rosengrund" return 0 results when queried by display name
    but work correctly when queried by id.
    Returns a list of Departure, or None when the API call failed.
    """
    params = {
        "lang": lang,
        "locationName": location,
        "maxJourneys": str(max_journeys),
    }
    url = DEPARTUREBOARD_URL + "?" + urlencode(params)
    try:
        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            resp = await session.get(url, headers=_HEADERS)
            resp.raise_for_status()
            data = await resp.json()
    except (aiohttp.ClientError, TimeoutError) as ex:
        _LOGGER.warning("BVG departureBoard error: %s", ex)
        return None
    except Exception as ex:  # pylint: disable=broad-except
        _LOGGER.error("Unexpected BVG API error: %s", ex)
        return None

    # The API returns a list with one entry per day; flatten the elements.
    elements: list[dict[str, Any]] = []
    if isinstance(data, list):
        for day in data:
            elements.extend((day or {}).get("elements") or [])
    elif isinstance(data, dict):
        elements.extend(data.get("elements") or [])

    departures = [Departure.from_api(e) for e in elements]
    departures.sort(key=lambda d: d.timestamp or datetime.max)
    return departures


async def fetch_connections(
    session: aiohttp.ClientSession,
    origin_id: str,
    destination_id: str,
    *,
    time_sel: str = "depart",
    products: int = ALL_PRODUCTS,
    lang: str = "de",
) -> list[Connection] | None:
    """Fetch the next connections from origin to destination.

    Returns a list of Connection, or None when the API call failed.
    """
    params = {
        "language": lang,
        "SID": origin_id,
        "ZID": destination_id,
        "timeSel": time_sel,
        "products": str(products),
    }
    url = CONNECTIONS_URL + "?" + urlencode(params)
    try:
        async with async_timeout.timeout(DEFAULT_TIMEOUT):
            resp = await session.get(url, headers=_HEADERS)
            resp.raise_for_status()
            data = await resp.json()
    except (aiohttp.ClientError, TimeoutError) as ex:
        _LOGGER.warning("BVG connection search error: %s", ex)
        return None
    except Exception as ex:  # pylint: disable=broad-except
        _LOGGER.error("Unexpected BVG API error: %s", ex)
        return None

    raw = data.get("connections") if isinstance(data, dict) else None
    if raw is None:
        _LOGGER.warning("BVG API returned no connections field: %s", data)
        return []
    return [Connection.from_api(c) for c in raw]
