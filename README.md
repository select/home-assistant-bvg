# BVG Berlin Connections — Home Assistant integration

A Home Assistant custom integration that shows **upcoming public-transport connections from A to B** in Berlin, using the connection-search API of [www.bvg.de](https://www.bvg.de).

This is a drop-in replacement for [vas3k/home-assistant-berlin-transport](https://github.com/vas3k/home-assistant-berlin-transport), which uses the third-party VBB `transport.rest` API. This integration talks **directly to the BVG website's own JSON API** — no API key, no rate-limited proxy, no third-party dependency.

> ⚠️ The BVG website API returns **connections** (origin → destination routing), so this sensor shows the next journeys from your origin to your destination. The original vas3k integration showed **departures from a single stop** — the data model is different, see [below](#differences-from-vas3khome-assistant-berlin-transport).

## Features

- 🔌 Uses the official `www.bvg.de` connection-search endpoint (reverse-engineered, no auth)
- 🚉 Config-flow setup: search origin + destination by name, pick from results
- 🕐 Shows the next N connections (departure / arrival time, duration, legs, live delay)
- 🚇 Per-product filtering (S-Bahn, U-Bahn, Tram, Bus, Regional, IC, ICE)
- 🚶 Walking-time filter (hide connections leaving sooner than you can reach them)
- 🔁 60 s polling, graceful fallback on API errors

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

1. **Origin stop** — type the name of your departure stop, pick it from the results.
2. **Destination stop** — same for where you're going.
3. **Travel options** — time selection (depart-at / arrive-by), look-ahead window, walking time, max connections, which transport types to include.

That's it. One sensor entity is created per config entry, named e.g.:

```
sensor.im_rosengrund_u_britz_sud_next_connection
```

## Entity state & attributes

**State** — a one-line summary of the next connection:

```
00:24 (+2') → 00:29 (5m) 181 → M46
```

**Attributes** (`extra_state_attributes`):

```json
{
  "origin": "Im Rosengrund (Berlin)",
  "destination": "U Britz-Süd (Berlin)",
  "from": "Im Rosengrund (Berlin)",
  "to": "U Britz-Süd (Berlin)",
  "time_selection": "depart",
  "walking_time": 0,
  "connections": [
    {
      "id": "e63d8ab2_3",
      "date": "2026-07-04",
      "departure": "00:24",
      "arrival": "00:29",
      "departure_delay": -2,
      "arrival_delay": -2,
      "duration": 5,
      "has_warnings": false,
      "line": "181",
      "lines": [
        {
          "line_name": "181",
          "line_type": "bus",
          "direction": "Britz, Kielingerstr.",
          "departure": "00:24",
          "arrival": "00:29",
          "from": "Im Rosengrund (Berlin)",
          "to": "U Britz-Süd (Berlin)",
          "duration": 5,
          "color": "#A5027D",
          "icon": "mdi:bus"
        }
      ]
    }
  ]
}
```

## Lovelace card

There is no dedicated card (yet). The attributes are plain JSON, so you can render them with a standard [custom:flex-table-card](https://github.com/custom-cards/flex-table-card), a template card, or a markdown card, e.g.:

```yaml
type: markdown
content: >
  {% set c = state_attr('sensor.im_rosengrund_u_britz_sud_next_connection', 'connections') %}
  ## Next connections
  {% for conn in c %}
  {{ conn.departure }} → {{ conn.arrival }} ({{ conn.duration }}m)
  — {{ conn.lines | map(attribute='line_name') | join(' → ') }}
  {% endfor %}
```

## Differences from vas3k/home-assistant-berlin-transport

| | vas3k (VBB `transport.rest`) | this integration (BVG) |
|---|---|---|
| API | `v6.vbb.transport.rest/stops/{id}/departures` | `www.bvg.de/connection-search/v1/connections` |
| Auth | none (third-party proxy) | none (direct, `Referer` header only) |
| Concept | departures from one stop | connections from origin → destination |
| Rate limit | 100 req/min (proxy) | none published |
| Entity state | next departure at a stop | next journey A→B |

If you previously used the [lovelace-berlin-transport-card](https://github.com/vas3k/lovelace-berlin-transport-card), note that it expects a `departures` attribute. This integration exposes `connections` instead, so that card is **not** directly compatible.

## Technical details

The BVG connection-search API was reverse-engineered from the journey planner at
`https://www.bvg.de/de/verbindungen/fahrplanauskunft`. Two endpoints are used:

```
GET https://www.bvg.de/api/search/v1/locations/byName/de?input=<query>
GET https://www.bvg.de/connection-search/v1/connections
    ?language=de
    &SID=<originId>
    &ZID=<destinationId>
    &timeSel=depart|arrive
    &products=<bitmask>   # HAFAS bitmask, 127 = all
```

Only an HTTP `Referer: https://www.bvg.de/` header is required — no tokens or
cookies. The integration polls every 60 seconds and caches nothing server-side;
station-name resolution happens once during config flow.

## License

MIT
