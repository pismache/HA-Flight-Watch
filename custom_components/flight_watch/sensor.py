"""Sensors for Flight Watch: receiver totals and details of each watched flight."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import DEGREE, UnitOfLength, UnitOfSpeed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import (
    Aircraft,
    FlightWatchConfigEntry,
    FlightWatchCoordinator,
    FlightWatchData,
)
from .entity import FlightWatchFlightEntity, FlightWatchReceiverEntity
from .units import unit_for


@dataclass(frozen=True, kw_only=True)
class ReceiverSensorDescription(SensorEntityDescription):
    """Describes a receiver-level sensor."""

    value_fn: Callable[[FlightWatchData], int | None]


@dataclass(frozen=True, kw_only=True)
class FlightSensorDescription(SensorEntityDescription):
    """Describes a sensor of a watched flight (values from the nearest match)."""

    value_fn: Callable[[Aircraft], float | int | str | None]
    unit_kind: str | None = None  # altitude / distance / speed: unit follows the units option


RECEIVER_SENSORS: tuple[ReceiverSensorDescription, ...] = (
    ReceiverSensorDescription(
        key="aircraft_total",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:airplane",
        value_fn=lambda d: d.aircraft_total,
    ),
    ReceiverSensorDescription(
        key="aircraft_with_position",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:map-marker-radius",
        value_fn=lambda d: d.aircraft_with_position,
    ),
)

FLIGHT_SENSORS: tuple[FlightSensorDescription, ...] = (
    FlightSensorDescription(
        key="callsign",
        icon="mdi:card-account-details-outline",
        value_fn=lambda a: a.callsign,
    ),
    FlightSensorDescription(
        key="altitude",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.FEET,
        suggested_display_precision=0,
        icon="mdi:altimeter",
        unit_kind="altitude",
        value_fn=lambda a: 0 if a.on_ground else a.altitude_ft,
    ),
    FlightSensorDescription(
        key="distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=1,
        icon="mdi:map-marker-distance",
        unit_kind="distance",
        value_fn=lambda a: a.distance_km,
    ),
    FlightSensorDescription(
        key="ground_speed",
        device_class=SensorDeviceClass.SPEED,
        native_unit_of_measurement=UnitOfSpeed.KNOTS,
        suggested_display_precision=0,
        unit_kind="speed",
        value_fn=lambda a: a.ground_speed_kt,
    ),
    FlightSensorDescription(
        key="bearing",
        native_unit_of_measurement=DEGREE,
        suggested_display_precision=0,
        icon="mdi:compass-outline",
        entity_registry_enabled_default=False,
        value_fn=lambda a: a.bearing_deg,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FlightWatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        ReceiverSensor(coordinator, description) for description in RECEIVER_SENSORS
    ]
    entities.extend(
        FlightSensor(coordinator, pattern, description)
        for pattern in coordinator.patterns
        for description in FLIGHT_SENSORS
    )
    async_add_entities(entities)


class ReceiverSensor(FlightWatchReceiverEntity, SensorEntity):
    """Aircraft counts seen by the receiver."""

    entity_description: ReceiverSensorDescription

    def __init__(
        self, coordinator: FlightWatchCoordinator, description: ReceiverSensorDescription
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | None:
        """Return the value."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class FlightSensor(FlightWatchFlightEntity, SensorEntity):
    """A detail of the nearest aircraft matching a watched flight."""

    entity_description: FlightSensorDescription

    def __init__(
        self,
        coordinator: FlightWatchCoordinator,
        pattern: str,
        description: FlightSensorDescription,
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, pattern, description.key)
        self.entity_description = description

    @property
    def suggested_unit_of_measurement(self) -> str | None:
        """Unit chosen in the integration options (metric / aviation / imperial)."""
        if self.entity_description.unit_kind is None:
            return None
        return unit_for(self.entity_description.unit_kind, self.coordinator.units)

    @property
    def native_value(self) -> float | int | str | None:
        """Return the value, or unknown while the flight is out of range."""
        if (nearest := self.nearest) is None:
            return None
        return self.entity_description.value_fn(nearest)
