"""Constants for the Flight Watch integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "flight_watch"

CONF_URL: Final = "url"
CONF_CALLSIGNS: Final = "callsigns"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_MAX_SEEN: Final = "max_seen"
CONF_NOTIFY: Final = "notify"
CONF_NOTIFY_LOST: Final = "notify_lost"
CONF_UNITS: Final = "units"

# Unit choices
UNITS_AUTO: Final = "auto"  # follow the Home Assistant unit system
UNITS_METRIC: Final = "metric"  # m, km, km/h
UNITS_AVIATION: Final = "aviation"  # ft, NM, kn
UNITS_IMPERIAL: Final = "imperial"  # ft, mi, mph
UNIT_CHOICES: Final = [UNITS_AUTO, UNITS_METRIC, UNITS_AVIATION]

DEFAULT_SCAN_INTERVAL: Final = 15  # seconds
DEFAULT_MAX_SEEN: Final = 60  # seconds without a message before an aircraft is considered gone
REQUEST_TIMEOUT: Final = 10  # seconds

# Events fired on the Home Assistant bus
EVENT_FLIGHT_DETECTED: Final = "flight_watch_flight_detected"
EVENT_FLIGHT_LOST: Final = "flight_watch_flight_lost"

NM_TO_KM: Final = 1.852
