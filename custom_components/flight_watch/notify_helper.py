"""Send push / persistent notifications when a watched flight is detected or lost."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import slugify

if TYPE_CHECKING:
    from .coordinator import Aircraft

_LOGGER = logging.getLogger(__name__)

NOTIFY_DOMAIN = "notify"
# Legacy notify services that cannot be used as a plain target
_EXCLUDED_SERVICES = {"send_message"}


def notify_service_options(hass: HomeAssistant, selected: list[str] | None = None) -> list[dict[str, str]]:
    """List the notify services as selector options, with readable labels.

    Mobile App services (``notify.mobile_app_<device>``) are labelled with the
    device name as shown in the companion app ("iPhone Cédric").
    """
    labels: dict[str, str] = {}
    for entry in hass.config_entries.async_entries("mobile_app"):
        name = entry.data.get("device_name") or entry.title
        if name:
            labels[f"mobile_app_{slugify(name)}"] = name

    services = set(hass.services.async_services_for_domain(NOTIFY_DOMAIN)) - _EXCLUDED_SERVICES
    services |= set(selected or [])  # keep a saved choice visible even if the service is gone

    options = [
        {"value": svc, "label": labels.get(svc) or _pretty(svc)} for svc in services
    ]
    # Phones / tablets first, then the rest, alphabetically
    options.sort(key=lambda o: (not o["value"].startswith("mobile_app_"), o["label"].lower()))
    return options


def _pretty(service: str) -> str:
    if service == "persistent_notification":
        return "Persistent notification (Home Assistant UI)"
    return service.removeprefix("mobile_app_").replace("_", " ").capitalize()


def _fmt(value: float | int | None, unit: str) -> str | None:
    if value is None:
        return None
    return f"{round(value):,}".replace(",", " ") + f" {unit}"


def build_message(
    hass: HomeAssistant, aircraft: Aircraft, *, lost: bool
) -> tuple[str, str]:
    """Return (title, message) in French or English depending on the HA language."""
    french = (hass.config.language or "en").lower().startswith("fr")
    name = aircraft.callsign or aircraft.registration or aircraft.hex

    model = aircraft.description or aircraft.aircraft_type
    altitude = (
        ("au sol" if french else "on ground")
        if aircraft.on_ground
        else _fmt(aircraft.altitude_ft, "ft")
    )
    distance = _fmt(aircraft.distance_km, "km")
    speed = _fmt(aircraft.ground_speed_kt, "kt")

    if lost:
        title = f"🛬 {name} " + ("hors de portée" if french else "out of range")
        prefix = "Dernier contact" if french else "Last seen"
        parts = [p for p in (distance, altitude) if p]
        message = f"{prefix} : {', '.join(parts)}" if parts else prefix
        if not french:
            message = message.replace(" : ", ": ")
        return title, message

    title = f"✈️ {name} " + ("à portée du radar" if french else "in range of the receiver")
    first = " – ".join(p for p in (model, aircraft.registration) if p)
    second = " · ".join(p for p in (altitude, distance, speed) if p)
    message = "\n".join(p for p in (first, second) if p) or name
    return title, message


async def async_send(
    hass: HomeAssistant,
    services: list[str],
    aircraft: Aircraft,
    *,
    lost: bool,
    url: str | None,
) -> None:
    """Send the notification to every selected notify service."""
    title, message = build_message(hass, aircraft, lost=lost)
    for service in services:
        if not hass.services.has_service(NOTIFY_DOMAIN, service):
            _LOGGER.warning("Notify service notify.%s no longer exists, skipping", service)
            continue
        data: dict = {"title": title, "message": message}
        if service.startswith("mobile_app_"):
            extra: dict = {"group": "flight_watch"}
            if url:
                extra["url"] = url
                extra["clickAction"] = url  # Android
            data["data"] = extra
        try:
            await hass.services.async_call(NOTIFY_DOMAIN, service, data, blocking=True)
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning("Could not send notification with notify.%s: %s", service, err)
