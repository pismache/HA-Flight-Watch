"""Flight Watch: get notified when given flights come into range of your ADS-B receiver."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import FlightWatchConfigEntry, FlightWatchCoordinator, watch_list
from .units import unit_for

# unique_id suffix -> kind of unit
_UNIT_SENSORS = {"_altitude": "altitude", "_distance": "distance", "_ground_speed": "speed"}

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: FlightWatchConfigEntry) -> bool:
    """Set up Flight Watch from a config entry."""
    coordinator = FlightWatchCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    _remove_stale_devices(hass, entry)
    _apply_units(hass, entry, coordinator.units)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FlightWatchConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: FlightWatchConfigEntry) -> None:
    """Reload when the options (watched flights, intervals) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: FlightWatchConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a watched-flight device that is no longer in the watch list."""
    in_use = {f"{entry.entry_id}:receiver"} | {
        f"{entry.entry_id}:{pattern}" for pattern in watch_list(entry)
    }
    return not any(
        ident[0] == DOMAIN and ident[1] in in_use for ident in device.identifiers
    )


def _remove_stale_devices(hass: HomeAssistant, entry: FlightWatchConfigEntry) -> None:
    """Remove devices of flights that were taken out of the watch list."""
    registry = dr.async_get(hass)
    valid = {f"{entry.entry_id}:receiver"} | {
        f"{entry.entry_id}:{pattern}" for pattern in watch_list(entry)
    }
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        idents = {ident[1] for ident in device.identifiers if ident[0] == DOMAIN}
        if idents and not idents & valid:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


def _apply_units(hass: HomeAssistant, entry: FlightWatchConfigEntry, units: str) -> None:
    """Make existing sensors follow the units option.

    Home Assistant stores the suggested unit in the entity registry when an entity is
    first created, so changing the option alone would not change already-created sensors.
    A unit the user forced in the entity settings still wins over this.
    """
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.domain != "sensor":
            continue
        kind = next(
            (k for suffix, k in _UNIT_SENSORS.items() if reg_entry.unique_id.endswith(suffix)), None
        )
        if kind is None:
            continue
        wanted = unit_for(kind, units)
        private = reg_entry.options.get("sensor.private", {})
        if private.get("suggested_unit_of_measurement") != wanted:
            registry.async_update_entity_options(
                reg_entry.entity_id,
                "sensor.private",
                {**private, "suggested_unit_of_measurement": wanted},
            )
