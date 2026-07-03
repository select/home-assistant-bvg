"""Dataclass modelling a single departure returned by the BVG departureBoard API.

The output of ``to_dict`` intentionally matches the attribute format used by
``vas3k/home-assistant-berlin-transport`` so the existing
``lovelace-berlin-transport-card`` works as a drop-in replacement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .const import DEFAULT_ICON, TRANSPORT_TYPE_VISUALS

# Map BVG lineTypeName -> our internal product key (same as in connection.py).
_LINE_TYPE_TO_KEY = {
    "bus": "bus",
    "tram": "tram",
    "suburban": "suburban",
    "subway": "subway",
    "regional": "regional",
    "regionalExp": "regional",
    "longDistance": "ice",
    "express": "ice",
}


def _delay_minutes(delay: str | None) -> int | None:
    """Parse an ISO-8601 delay like 'PT-1M' / 'PT0S' / 'PT5M' into minutes."""
    if delay is None:
        return None
    neg = delay.startswith("PT-")
    cleaned = delay.replace("PT-", "PT").replace("PT", "")
    m = re.match(r"^(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$", cleaned)
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    minutes = h * 60 + mi + (1 if s else 0)
    return -minutes if neg else minutes


@dataclass
class Departure:
    """A single departure from a stop."""

    line_name: str
    line_type: str
    time: str  # "HH:MM"
    timestamp: datetime | None
    direction: str | None
    track: str | None
    icon: str
    color: str
    delay: int | None

    @classmethod
    def from_api(cls, element: dict[str, Any]) -> "Departure":
        service = element.get("service") or {}
        dep = element.get("departure") or {}
        line_type_name = (service.get("lineTypeName") or "").lower()
        key = _LINE_TYPE_TO_KEY.get(line_type_name, "bus")
        visuals = TRANSPORT_TYPE_VISUALS.get(key, {})
        timestamp = None
        date = dep.get("date")
        t = dep.get("time")
        if date and t:
            try:
                timestamp = datetime.fromisoformat(f"{date}T{t}")
            except ValueError:
                timestamp = None
        return cls(
            line_name=service.get("name") or "?",
            line_type=key,
            time=(t or "")[:5],
            timestamp=timestamp,
            direction=service.get("direction"),
            track=element.get("track"),
            icon=visuals.get("icon", DEFAULT_ICON),
            color=visuals.get("color", "#4D4D4D"),
            delay=_delay_minutes(dep.get("delay")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise in the vas3k-compatible departures attribute format."""
        return {
            "line_name": self.line_name,
            "line_type": self.line_type,
            "time": self.time,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "direction": self.direction,
            "track": self.track,
            "color": self.color,
            "icon": self.icon,
            "cancelled": False,
            "delay": self.delay,
            "warnings": None,
        }
