# BVG Berlin Connections — Home Assistant integration

A Home Assistant custom integration for Berlin public transport, using the connection-search and departure-board JSON APIs of [www.bvg.de](https://www.bvg.de) directly (no auth, no third-party proxy).

It can run in two modes:

- **Departures** — upcoming departures from a single stop. The `departures` attribute matches the format of [vas3k/home-assistant-berlin-transport](https://github.com/vas3k/home-assistant-berlin-transport), so the existing [lovelace-berlin-transport-card](https://github.com/vas3k/lovelace-berlin-transport-card) works as a **drop-in replacement**.
- **Connections** — next journeys from an origin to a destination (the routing you get on the BVG journey planner).

This is a replacement for [vas3k/home-assistant-berlin-transport](https://github.com/vas3k/home-assistant-berlin-transport), which uses the third-party VBB `transport.rest` API. This integration talks **directly to the BVG website's own JSON API** — no API key, no rate-limited proxy, no third-party dependency.

## Features

- 🔌 Uses the official `www.bvg.de` endpoints (reverse-engineered, no auth)
- 🚏 **Departures mode**: next departures from a stop, vas3k-compatible `departures` attribute
- 🚉 **Connections mode**: next journeys A→B with legs, delays and durations
- 🔎 Config-flow setup: pick a mode, search stops by name, choose from results
- 🚇 Per-product filtering (S-Bahn, U-Bahn, Tram, Bus, Regional, IC, ICE)
- 🚶 Walking-time filter (hide departures/connections leaving sooner than you can reach them)
- 🔁 5 min polling, graceful fallback on API errors

## Installation

### Via HACS

1. Add this repository as a **custom repository** in HACS (category: *Integration*).
2. Install **BVG Berlin Connections**.
3. Restart Home Assistant.
4. Add the integration via *Settings → Devices & services → Add integration* → search "BVG".

### Manual

Copy the `custom_components/bvg/` directory into your Home Assistant `custom_components/` folder, then restart.

## Setup

The config flow walks you through:

1. **Mode** — *Departures from a single stop* or *Connections from origin to destination*.
2. **Origin stop** — type the name of your departure stop, pick it from the results.
3. **Destination stop** — (connections mode only) same for where you're going.
4. **Travel options** — which transport types to include, walking time, and how many results to show (max connections / max departures). In connections mode you also pick depart-at vs arrive-by and a look-ahead window.

That's it. One sensor entity is created per config entry.

## Entity state & attributes

**State** — a one-line summary of the next departure / connection:

```
# departures mode
Next U7 at 00:42 (+1)
# connections mode
00:24 (+2') → 00:29 (5m) 181 → M46
```

**Attributes** (`extra_state_attributes`) — in **departures mode**:

```json
{
  "origin": "U Britz-Süd (Berlin)",
  "from": "U Britz-Süd (Berlin)",
  "to": null,
  "mode": "departures",
  "walking_time": 0,
  "departures": [
    {
      "line_name": "U7",
      "line_type": "subway",
      "time": "00:42",
      "timestamp": "2026-07-04T00:42:00",
      "direction": "Rathaus Spandau",
      "track": "Gl. 2",
      "color": "#2864A6",
      "icon": "mdi:subway",
      "cancelled": false,
      "delay": 1,
      "warnings": null
    }
  ]
}
```

In **connections mode** the `connections` array is exposed instead (see [Connections attributes](#connections-attributes) below).

## Lovelace card

In **departures mode** the `departures` attribute is compatible with [vas3k/lovelace-berlin-transport-card](https://github.com/vas3k/lovelace-berlin-transport-card) — install it via HACS and point it at this sensor, no changes needed.

In **connections mode** (or if you prefer not to use that card) the attributes are plain JSON and can be rendered with a markdown or [flex-table-card](https://github.com/custom-cards/flex-table-card), e.g.:

```yaml
# departures — markdown fallback
type: markdown
content: >
  {% set d = state_attr('sensor.u_britz_sud_next_departure', 'departures') %}
  {% for dep in d %}
  {{ dep.time }} {{ dep.line_name }} → {{ dep.direction }} ({{ dep.delay }}')
  {% endfor %}
```

```yaml
# connections — markdown fallback
type: markdown
content: >
  {% set c = state_attr('sensor.im_rosengrund_u_britz_sud_next_connection', 'connections') %}
  {% for conn in c %}
  {{ conn.departure }} → {{ conn.arrival }} ({{ conn.duration }}m)
  — {{ conn.lines | map(attribute='line_name') | join(' → ') }}
  {% endfor %}
```

## Differences from vas3k/home-assistant-berlin-transport

| | vas3k (VBB `transport.rest`) | this integration (BVG) |
|---|---|---|
| API | `v6.vbb.transport.rest/stops/{id}/departures` | `www.bvg.de` (connection-search + departureBoard) |
| Auth | none (third-party proxy) | none (direct, `Referer` header only) |
| Concept | departures from one stop | departures from a stop **or** connections A→B |
| Rate limit | 100 req/min (proxy) | none published |
| Entity state | next departure at a stop | next departure **or** next journey A→B |

In departures mode this integration is a true drop-in: same `departures` attribute
shape, so the existing Lovelace card works unchanged.

## Technical details

Two reverse-engineered `www.bvg.de` endpoints are used (only an HTTP
`Referer: https://www.bvg.de/` header is required — no tokens or cookies):

```
# station name -> id (used during config flow)
GET https://www.bvg.de/api/search/v1/locations/byName/de?input=<query>

# departures from a single stop (departures mode)
GET https://www.bvg.de/connection-search/v1/departureBoard
    ?lang=de&locationName=<stop name>&maxJourneys=10

# connections from origin to destination (connections mode)
GET https://www.bvg.de/connection-search/v1/connections
    ?language=de
    &SID=<originId>
    &ZID=<destinationId>
    &timeSel=depart|arrive
    &products=<bitmask>   # HAFAS bitmask, 127 = all
```

The integration polls every 5 minutes (configurable via `SCAN_INTERVAL` in `custom_components/bvg/const.py`). Station-name resolution happens once
during config flow; the departureBoard endpoint takes the stop *name* directly.

## License

MIT
