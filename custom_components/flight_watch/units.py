"""Display units: metric (m, km, km/h), aviation (ft, NM, kn) or imperial (ft, mi, mph).

Values are always produced in aviation units by the receiver (feet, knots) and in km for
the distance; Home Assistant converts them to the selected units through the sensors'
suggested unit of measurement.
"""

from __future__ import annotations

from homeassistant.const import UnitOfLength, UnitOfSpeed
from homeassistant.core import HomeAssistant
from homeassistant.util.unit_conversion import DistanceConverter, SpeedConverter
from homeassistant.util.unit_system import METRIC_SYSTEM

from .const import UNITS_AUTO, UNITS_AVIATION, UNITS_IMPERIAL, UNITS_METRIC

# kind -> units system -> unit
UNITS: dict[str, dict[str, str]] = {
    "altitude": {
        UNITS_METRIC: UnitOfLength.METERS,
        UNITS_AVIATION: UnitOfLength.FEET,
        UNITS_IMPERIAL: UnitOfLength.FEET,
    },
    "distance": {
        UNITS_METRIC: UnitOfLength.KILOMETERS,
        UNITS_AVIATION: UnitOfLength.NAUTICAL_MILES,
        UNITS_IMPERIAL: UnitOfLength.MILES,
    },
    "speed": {
        UNITS_METRIC: UnitOfSpeed.KILOMETERS_PER_HOUR,
        UNITS_AVIATION: UnitOfSpeed.KNOTS,
        UNITS_IMPERIAL: UnitOfSpeed.MILES_PER_HOUR,
    },
}

NATIVE: dict[str, str] = {
    "altitude": UnitOfLength.FEET,
    "distance": UnitOfLength.KILOMETERS,
    "speed": UnitOfSpeed.KNOTS,
}

# Short labels used in notifications
LABELS: dict[str, str] = {"nmi": "NM", "kn": "kt"}


def resolve_units(hass: HomeAssistant, choice: str | None) -> str:
    """Turn the user's choice into metric / aviation / imperial."""
    if choice in (UNITS_METRIC, UNITS_AVIATION):
        return choice
    if choice in (None, UNITS_AUTO):
        return UNITS_METRIC if hass.config.units is METRIC_SYSTEM else UNITS_IMPERIAL
    return UNITS_METRIC


def unit_for(kind: str, system: str) -> str:
    """Unit to display for a kind of value."""
    return UNITS[kind][system]


def convert(kind: str, value: float | None, system: str) -> float | None:
    """Convert a native value (ft, km, kn) to the selected system."""
    if value is None:
        return None
    target = unit_for(kind, system)
    converter = SpeedConverter if kind == "speed" else DistanceConverter
    return converter.convert(value, NATIVE[kind], target)


def label(unit: str) -> str:
    """Short unit label for texts."""
    return LABELS.get(unit, unit)
