"""Data coordinator for Flight Watch: polls a readsb / tar1090 aircraft.json."""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_CALLSIGNS,
    CONF_MAX_SEEN,
    CONF_NOTIFY,
    CONF_NOTIFY_LOST,
    CONF_SCAN_INTERVAL,
    CONF_UNITS,
    CONF_URL,
    DEFAULT_MAX_SEEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_FLIGHT_DETECTED,
    EVENT_FLIGHT_LOST,
    NM_TO_KM,
    REQUEST_TIMEOUT,
)
from .notify_helper import async_send
from .units import resolve_units

_LOGGER = logging.getLogger(__name__)

type FlightWatchConfigEntry = ConfigEntry[FlightWatchCoordinator]


class CannotConnect(Exception):
    """The aircraft.json URL could not be reached."""


class InvalidData(Exception):
    """The URL answered but did not return a readsb aircraft.json document."""


def normalize(value: str | None) -> str:
    """Normalize a callsign / registration / hex for comparison."""
    return (value or "").strip().upper().replace(" ", "")


def pattern_matches(pattern: str, value: str | None) -> bool:
    """Return True when a watch pattern matches a value.

    A pattern ending with ``*`` is a prefix match (``FBU*`` matches every
    French Bee flight); otherwise the match is exact.
    """
    value = normalize(value)
    if not value:
        return False
    if pattern.endswith("*"):
        return value.startswith(pattern[:-1])
    return value == pattern


def parse_watch_items(raw: list[str] | str | None) -> dict[str, str | None]:
    """Parse the watch list into {pattern: alias}.

    Each item is ``PATTERN`` or ``PATTERN = Alias`` (``:`` also accepted), e.g.
    ``FBU85A = Retour maman``. Items without an alias may be comma-separated.
    """
    if not raw:
        return {}
    if isinstance(raw, str):
        raw = [raw]
    result: dict[str, str | None] = {}
    for item in raw:
        item = str(item)
        sep = next((c for c in ("=", ":") if c in item), None)
        if sep is None:
            parts = [(p, None) for p in item.split(",")]
        else:
            pattern, alias = item.split(sep, 1)
            parts = [(pattern, alias.strip() or None)]
        for pattern, alias in parts:
            norm = normalize(pattern)
            if norm and norm != "*":
                # a later alias for the same pattern wins; keep an earlier one otherwise
                result[norm] = alias or result.get(norm)
    return result


def format_watch_items(items: dict[str, str | None]) -> list[str]:
    """Inverse of parse_watch_items, used to store the options."""
    return [f"{p} = {a}" if a else p for p, a in items.items()]


def watch_items(entry: ConfigEntry) -> dict[str, str | None]:
    """Watched {pattern: alias} of a config entry."""
    return parse_watch_items(entry.options.get(CONF_CALLSIGNS, entry.data.get(CONF_CALLSIGNS, [])))


def watch_list(entry: ConfigEntry) -> list[str]:
    """Return the normalized, de-duplicated list of watched patterns."""
    return list(watch_items(entry))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass(slots=True)
class Aircraft:
    """One aircraft as seen by the receiver (subset of the aircraft.json fields)."""

    hex: str
    callsign: str | None = None
    registration: str | None = None
    aircraft_type: str | None = None
    description: str | None = None
    operator: str | None = None
    altitude_ft: int | None = None
    on_ground: bool = False
    ground_speed_kt: float | None = None
    track_deg: float | None = None
    vertical_rate_fpm: int | None = None
    squawk: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    bearing_deg: float | None = None
    seen_s: float | None = None

    def as_attributes(self) -> dict[str, Any]:
        """Attributes exposed on entities (None values dropped)."""
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(slots=True)
class FlightWatchData:
    """Snapshot returned by the coordinator."""

    aircraft_total: int = 0
    aircraft_with_position: int = 0
    # pattern -> matching aircraft, nearest first
    matches: dict[str, list[Aircraft]] = field(default_factory=dict)


def _parse_aircraft(
    raw: dict[str, Any], home: tuple[float, float] | None
) -> Aircraft | None:
    hex_code = raw.get("hex")
    if not hex_code:
        return None

    alt = raw.get("alt_baro")
    on_ground = alt == "ground"
    altitude = None if on_ground or not isinstance(alt, (int, float)) else int(alt)
    if altitude is None and isinstance(raw.get("alt_geom"), (int, float)):
        altitude = int(raw["alt_geom"])

    lat, lon = raw.get("lat"), raw.get("lon")
    distance = None
    if isinstance(raw.get("r_dst"), (int, float)):
        distance = round(raw["r_dst"] * NM_TO_KM, 1)
    elif home and isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        distance = round(_haversine_km(home[0], home[1], lat, lon), 1)

    callsign = (raw.get("flight") or "").strip() or None

    return Aircraft(
        hex=normalize(hex_code).lstrip("~") or hex_code,
        callsign=callsign,
        registration=raw.get("r"),
        aircraft_type=raw.get("t"),
        description=raw.get("desc"),
        operator=raw.get("ownOp"),
        altitude_ft=altitude,
        on_ground=on_ground,
        ground_speed_kt=raw.get("gs"),
        track_deg=raw.get("track"),
        vertical_rate_fpm=raw.get("baro_rate", raw.get("geom_rate")),
        squawk=raw.get("squawk"),
        latitude=lat,
        longitude=lon,
        distance_km=distance,
        bearing_deg=raw.get("r_dir"),
        seen_s=raw.get("seen"),
    )


class FlightWatchCoordinator(DataUpdateCoordinator[FlightWatchData]):
    """Poll aircraft.json and match the watched flights."""

    config_entry: FlightWatchConfigEntry

    def __init__(self, hass: HomeAssistant, entry: FlightWatchConfigEntry) -> None:
        """Initialize."""
        interval = entry.options.get(
            CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.url: str = entry.data[CONF_URL]
        self.max_seen: int = entry.options.get(
            CONF_MAX_SEEN, entry.data.get(CONF_MAX_SEEN, DEFAULT_MAX_SEEN)
        )
        self.aliases: dict[str, str | None] = watch_items(entry)
        self.patterns: list[str] = list(self.aliases)
        self.notify_services: list[str] = list(entry.options.get(CONF_NOTIFY, []))
        self.notify_lost: bool = entry.options.get(CONF_NOTIFY_LOST, False)
        self.units: str = resolve_units(hass, entry.options.get(CONF_UNITS))
        self._session = async_get_clientsession(hass)
        # (pattern, hex) pairs currently in range, for detected/lost events
        self._present: set[tuple[str, str]] | None = None
        self._last_seen: dict[tuple[str, str], Aircraft] = {}

    async def _async_update_data(self) -> FlightWatchData:
        try:
            payload = await fetch_aircraft_json(self._session, self.url)
        except (CannotConnect, InvalidData) as err:
            raise UpdateFailed(str(err)) from err

        home = None
        if self.hass.config.latitude is not None and self.hass.config.longitude is not None:
            home = (self.hass.config.latitude, self.hass.config.longitude)

        data = FlightWatchData(matches={p: [] for p in self.patterns})
        for raw in payload.get("aircraft", []):
            if not isinstance(raw, dict):
                continue
            seen = raw.get("seen")
            if isinstance(seen, (int, float)) and seen > self.max_seen:
                continue
            aircraft = _parse_aircraft(raw, home)
            if aircraft is None:
                continue
            data.aircraft_total += 1
            if aircraft.latitude is not None:
                data.aircraft_with_position += 1
            for pattern in self.patterns:
                if (
                    pattern_matches(pattern, aircraft.callsign)
                    or pattern_matches(pattern, aircraft.registration)
                    or pattern_matches(pattern, aircraft.hex)
                ):
                    data.matches[pattern].append(aircraft)

        for found in data.matches.values():
            found.sort(key=lambda a: a.distance_km if a.distance_km is not None else math.inf)

        self._fire_events(data)
        return data

    def _fire_events(self, data: FlightWatchData) -> None:
        current: dict[tuple[str, str], Aircraft] = {
            (pattern, a.hex): a for pattern, found in data.matches.items() for a in found
        }
        if self._present is None:
            # First refresh after a (re)start: take a baseline without firing events,
            # so a restart of Home Assistant does not re-announce aircraft already in range.
            self._present = set(current)
            self._last_seen = current
            return
        previous = self._present

        # One notification per aircraft, even when it matches several patterns (FBU711 and FBU*)
        to_notify_detected: dict[str, tuple[Aircraft, str | None]] = {}
        to_notify_lost: dict[str, tuple[Aircraft, str | None]] = {}

        for key in current.keys() - previous:
            pattern, hex_code = key
            self.hass.bus.async_fire(
                EVENT_FLIGHT_DETECTED,
                {
                    "entry_id": self.config_entry.entry_id,
                    "watch": pattern,
                    "alias": self.aliases.get(pattern),
                    **current[key].as_attributes(),
                },
            )
            if not any(k[1] == hex_code for k in previous):
                alias = self.aliases.get(pattern)
                if hex_code not in to_notify_detected or (alias and not to_notify_detected[hex_code][1]):
                    to_notify_detected[hex_code] = (current[key], alias)
        for key in previous - current.keys():
            pattern, hex_code = key
            last = self._last_seen.get(key)
            self.hass.bus.async_fire(
                EVENT_FLIGHT_LOST,
                {
                    "entry_id": self.config_entry.entry_id,
                    "watch": pattern,
                    "alias": self.aliases.get(pattern),
                    **(last.as_attributes() if last else {"hex": hex_code}),
                },
            )
            if last and not any(k[1] == hex_code for k in current):
                alias = self.aliases.get(pattern)
                if hex_code not in to_notify_lost or (alias and not to_notify_lost[hex_code][1]):
                    to_notify_lost[hex_code] = (last, alias)

        if self.notify_services:
            for aircraft, alias in to_notify_detected.values():
                self._notify(aircraft, alias, lost=False)
            if self.notify_lost:
                for aircraft, alias in to_notify_lost.values():
                    self._notify(aircraft, alias, lost=True)

        self._present = set(current)
        self._last_seen = current

    @property
    def receiver_url(self) -> str:
        """Web interface of the receiver (tar1090), derived from the aircraft.json URL."""
        return self.url.rsplit("/data/", 1)[0]

    def _notify(self, aircraft: Aircraft, alias: str | None, *, lost: bool) -> None:
        self.config_entry.async_create_background_task(
            self.hass,
            async_send(
                self.hass,
                self.notify_services,
                aircraft,
                alias=alias,
                lost=lost,
                url=self.receiver_url,
                units=self.units,
            ),
            f"{DOMAIN} notification {aircraft.hex}",
        )


async def fetch_aircraft_json(session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
    """Fetch and minimally validate a readsb / tar1090 aircraft.json."""
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            resp = await session.get(url)
            resp.raise_for_status()
            payload = await resp.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError) as err:
        raise CannotConnect(f"Error fetching {url}: {err}") from err
    except ValueError as err:
        raise InvalidData(f"{url} did not return JSON") from err

    if not isinstance(payload, dict) or not isinstance(payload.get("aircraft"), list):
        raise InvalidData(f"{url} is not a readsb/tar1090 aircraft.json (no 'aircraft' list)")
    return payload
