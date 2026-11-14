"""Binary sensor: is a watched flight in range of the receiver?"""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import FlightWatchConfigEntry
from .entity import FlightWatchFlightEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlightWatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up one 'in range' binary sensor per watched flight."""
    coordinator = entry.runtime_data
    async_add_entities(
        FlightInRangeBinarySensor(coordinator, pattern) for pattern in coordinator.patterns
    )


class FlightInRangeBinarySensor(FlightWatchFlightEntity, BinarySensorEntity):
    """On while at least one aircraft matching the pattern is received."""

    def __init__(self, coordinator, pattern: str) -> None:
        """Initialize."""
        super().__init__(coordinator, pattern, "in_range")

    @property
    def is_on(self) -> bool:
        """Return True when the flight is in range."""
        return bool(self.matches)

    @property
    def icon(self) -> str:
        """Icon reflecting the state."""
        return "mdi:airplane" if self.is_on else "mdi:airplane-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Details of the nearest matching aircraft."""
        attrs: dict[str, Any] = {"watch": self.pattern, "match_count": len(self.matches)}
        if (nearest := self.nearest) is not None:
            attrs.update(nearest.as_attributes())
        if len(self.matches) > 1:
            attrs["matched"] = [a.callsign or a.registration or a.hex for a in self.matches]
        return attrs
