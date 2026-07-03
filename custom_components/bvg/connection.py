"""Dataclass modelling a single connection returned by the BVG API.

The BVG connection-search endpoint returns journeys with `summary` and `legs`.
Each connection is converted into this dataclass so the sensor and the Lovelace
card can consume a stable, simple structure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .const import DEFAULT_ICON, TRANSPORT_TYPE_VISUALS

# Map BVG lineTypeName -> our internal product key used by TRANSPORT_TYPE_VISUALS.
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


def _parse_iso_duration(value: str | None) -> int:
    """Parse an ISO-8601 duration like 'PT5M' / 'PT1H32M' into minutes."""
    if not value:
        return 0
    m = re.match(
        r"^P(?:T(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?)?$", value
    )
    if not m:
        return 0
    parts = {k: int(v) for k, v in m.groupdict(default="0").items()}
    return parts["h"] * 60 + parts["m"] + (1 if parts["s"] else 0)


def _delay_minutes(delay: str | None) -> int | None:
    """Parse an ISO-8601 delay like 'PT-1M' / 'PT0S' / 'PT5M' into minutes."""
    if delay is None:
        return None
    neg = delay.startswith("PT-")
    cleaned = delay.replace("PT-", "PT").replace("PT", "")
    minutes = _parse_iso_duration(f"PT{cleaned}")
    return -minutes if neg else minutes


@dataclass
class Leg:
    """A single leg of a connection (one vehicle ride or walk)."""

    line_name: str
    line_type: str
    direction: str | None
    dep_time: str  # "HH:MM"
    arr_time: str
    dep_stop: str
    arr_stop: str
    duration: int  # minutes
    icon: str
    color: str

    @classmethod
    def from_api(cls, leg: dict[str, Any]) -> "Leg":
        service = leg.get("service") or {}
        line_name = service.get("name") or "?"
        line_type_name = (service.get("lineTypeName") or "").lower()
        key = _LINE_TYPE_TO_KEY.get(line_type_name, "bus")
        visuals = TRANSPORT_TYPE_VISUALS.get(key, {})
        dep = leg.get("departure") or {}
        arr = leg.get("arrival") or {}
        return cls(
            line_name=line_name,
            line_type=key,
            direction=service.get("direction"),
            dep_time=(dep.get("time") or "")[:5],
            arr_time=(arr.get("time") or "")[:5],
            dep_stop=(leg.get("departureStop") or {}).get("name", ""),
            arr_stop=(leg.get("arrivalStop") or {}).get("name", ""),
            duration=_parse_iso_duration(leg.get("duration") or service.get("duration")),
            icon=visuals.get("icon", DEFAULT_ICON),
            color=visuals.get("color", "#4D4D4D"),
        )


@dataclass
class Connection:
    """A full connection from origin to destination."""

    connection_id: str
    date: str
    dep_time: str  # "HH:MM"
    arr_time: str
    dep_delay: int | None
    arr_delay: int | None
    duration: int  # minutes
    legs: list[Leg]
    has_warnings: bool = False
    timestamp: datetime | None = None  # actual departure datetime (for sorting)

    @classmethod
    def from_api(cls, conn: dict[str, Any]) -> "Connection":
        summary = conn.get("summary") or {}
        dep = summary.get("departure") or {}
        arr = summary.get("arrival") or {}
        dep_time = (dep.get("time") or "")[:5]
        arr_time = (arr.get("time") or "")[:5]
        date = conn.get("date") or dep.get("date") or ""
        timestamp = None
        if date and dep.get("time"):
            try:
                timestamp = datetime.fromisoformat(f"{date}T{dep['time']}")
            except ValueError:
                timestamp = None
        return cls(
            connection_id=conn.get("id") or "",
            date=date,
            dep_time=dep_time,
            arr_time=arr_time,
            dep_delay=_delay_minutes(dep.get("delay")),
            arr_delay=_delay_minutes(arr.get("delay")),
            duration=_parse_iso_duration(summary.get("totalDuration")),
            legs=[Leg.from_api(l) for l in (conn.get("legs") or [])],
            has_warnings=bool(summary.get("hasWarnings")),
            timestamp=timestamp,
        )

    @property
    def primary_line(self) -> str:
        return self.legs[0].line_name if self.legs else "—"

    @property
    def icon(self) -> str:
        return self.legs[0].icon if self.legs else DEFAULT_ICON

    @property
    def line_types(self) -> set[str]:
        return {leg.line_type for leg in self.legs}

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the sensor extra_state_attributes."""
        return {
            "id": self.connection_id,
            "date": self.date,
            "departure": self.dep_time,
            "arrival": self.arr_time,
            "departure_delay": self.dep_delay,
            "arrival_delay": self.arr_delay,
            "duration": self.duration,
            "has_warnings": self.has_warnings,
            "line": self.primary_line,
            "lines": [
                {
                    "line_name": leg.line_name,
                    "line_type": leg.line_type,
                    "direction": leg.direction,
                    "departure": leg.dep_time,
                    "arrival": leg.arr_time,
                    "from": leg.dep_stop,
                    "to": leg.arr_stop,
                    "duration": leg.duration,
                    "color": leg.color,
                    "icon": leg.icon,
                }
                for leg in self.legs
            ],
        }
