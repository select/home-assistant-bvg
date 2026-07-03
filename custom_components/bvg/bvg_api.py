"""Async client for the reverse-engineered www.bvg.de connection-search API."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import aiohttp
import async_timeout

from .const import (
    ALL_PRODUCTS,
    CONNECTIONS_URL,
    LOCATIONS_URL,
    PRODUCT_BITS,
    REFERER,
)
from .connection import Connection

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
