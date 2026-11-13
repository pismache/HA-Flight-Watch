"""Base entities for Flight Watch."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import Aircraft, FlightWatchCoordinator


class FlightWatchReceiverEntity(CoordinatorEntity[FlightWatchCoordinator]):
    """Entity attached to the receiver device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FlightWatchCoordinator, key: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_receiver_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}:receiver")},
            name=coordinator.config_entry.title,
            manufacturer="readsb / tar1090",
            model="ADS-B receiver",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=coordinator.url.rsplit("/data/", 1)[0],
        )


class FlightWatchFlightEntity(CoordinatorEntity[FlightWatchCoordinator]):
    """Entity attached to one watched flight (callsign / registration / hex pattern)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: FlightWatchCoordinator, pattern: str, key: str) -> None:
        """Initialize."""
        super().__init__(coordinator)
        entry_id = coordinator.config_entry.entry_id
        self.pattern = pattern
        self._attr_unique_id = f"{entry_id}_{pattern}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}:{pattern}")},
            name=f"Flight {pattern}",
            manufacturer="Flight Watch",
            model="Watched flight",
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, f"{entry_id}:receiver"),
        )

    @property
    def matches(self) -> list[Aircraft]:
        """Aircraft currently matching this pattern, nearest first."""
        if self.coordinator.data is None:
            return []
        return self.coordinator.data.matches.get(self.pattern, [])

    @property
    def nearest(self) -> Aircraft | None:
        """Nearest matching aircraft, if any."""
        found = self.matches
        return found[0] if found else None
