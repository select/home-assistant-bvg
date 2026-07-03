"""Constants for the BVG Berlin Connections integration."""
from datetime import timedelta

DOMAIN = "bvg"

# Poll every 60 seconds. The BVG connection-search API has no published rate
# limit and a single request returns the next handful of connections, so this
# is plenty for a "when is the next connection" sensor.
SCAN_INTERVAL = timedelta(seconds=60)

# How long to keep showing the last good result when the API errors out.
FALLBACK_TIME = timedelta(minutes=15)

# Reverse-engineered www.bvg.de endpoints (no auth, just needs a Referer).
LOCATIONS_URL = "https://www.bvg.de/api/search/v1/locations/byName/{lang}"
CONNECTIONS_URL = "https://www.bvg.de/connection-search/v1/connections"
REFERER = "https://www.bvg.de/"

API_MAX_RESULTS = 8

DEFAULT_ICON = "mdi:train"

# HAFAS-style product bitmask used by BVG.
# The website sends products=127 when every mode is ticked on.
PRODUCT_BITS = {
    "ice": 1,        # long-distance ICE
    "ic": 2,         # long-distance IC/EC
    "regional": 4,   # RB/RE regional traffic
    "suburban": 8,   # S-Bahn
    "subway": 16,    # U-Bahn
    "tram": 32,      # Tram
    "bus": 64,       # Bus
}
ALL_PRODUCTS = sum(PRODUCT_BITS.values())  # 127

# Config entry keys
CONF_ORIGIN = "origin"
CONF_ORIGIN_ID = "origin_id"
CONF_ORIGIN_NAME = "origin_name"
CONF_DESTINATION = "destination"
CONF_DESTINATION_ID = "destination_id"
CONF_DESTINATION_NAME = "destination_name"
CONF_TIME_SEL = "time_sel"
CONF_DURATION = "duration"          # query departures for how many minutes ahead
CONF_WALKING_TIME = "walking_time"  # hide connections leaving sooner than this
CONF_MAX_CONNECTIONS = "max_connections"

CONF_TYPE_ICE = "ice"
CONF_TYPE_IC = "ic"
CONF_TYPE_REGIONAL = "regional"
CONF_TYPE_SUBURBAN = "suburban"
CONF_TYPE_SUBWAY = "subway"
CONF_TYPE_TRAM = "tram"
CONF_TYPE_BUS = "bus"

TRANSPORT_TYPE_VISUALS = {
    CONF_TYPE_SUBURBAN: {"code": "S", "icon": "mdi:subway-variant", "color": "#008D4F"},
    CONF_TYPE_SUBWAY: {"code": "U", "icon": "mdi:subway", "color": "#2864A6"},
    CONF_TYPE_TRAM: {"code": "M", "icon": "mdi:tram", "color": "#D82020"},
    CONF_TYPE_BUS: {"code": "BUS", "icon": "mdi:bus", "color": "#A5027D"},
    CONF_TYPE_REGIONAL: {"code": "RE", "icon": "mdi:train", "color": "#F01414"},
    CONF_TYPE_IC: {"code": "IC", "icon": "mdi:train", "color": "#4D4D4D"},
    CONF_TYPE_ICE: {"code": "ICE", "icon": "mdi:train", "color": "#4D4D4D"},
}
