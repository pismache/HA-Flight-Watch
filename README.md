# Flight Watch

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![Validate](https://github.com/pismache/ha-flight-watch/actions/workflows/validate.yml/badge.svg)](https://github.com/pismache/ha-flight-watch/actions/workflows/validate.yml)

Home Assistant integration that watches **specific flights on your own ADS-B receiver**
(readsb / tar1090 / ultrafeeder) and tells you when they come into range.

Everything is local: the integration only reads the `aircraft.json` file your receiver
already publishes. No cloud service, no API key.

## Features

- Watch any number of flights by **callsign** (`FBU711`), **registration** (`F-HREU`)
  or **ICAO hex** (`39a4b2`).
- **Prefix match** with a trailing `*`: `FBU*` watches every French Bee flight.
- For each watched flight, a device with:
  - `binary_sensor.flight_<x>_in_range` – on while the aircraft is received, with all
    its details as attributes (callsign, registration, type, altitude, speed, position…)
  - sensors for callsign, altitude, distance, ground speed and bearing
    (bearing is disabled by default)
- **Units of your choice**: metric (m, km, km/h), aviation (ft, NM, kt), or automatic
  (follows the Home Assistant unit system), for sensors and notifications.
- Receiver device with the number of aircraft tracked and with a position.
- **Built-in notifications**: pick your phone(s) in the options and get an alert when a
  watched flight comes into range (optionally also when it leaves), no automation needed.
- Events `flight_watch_flight_detected` and `flight_watch_flight_lost` for automations.
- Watched flights are edited from the UI (**Configure** on the integration), no YAML.

## Installation

### HACS

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/pismache/ha-flight-watch`,
   category **Integration**.
2. Install **Flight Watch** and restart Home Assistant.

### Manual

Copy `custom_components/flight_watch` into your `config/custom_components` folder and restart.

## Configuration

**Settings → Devices & services → Add integration → Flight Watch**

| Field | Description |
|---|---|
| aircraft.json URL | `http://<receiver>/tar1090/data/aircraft.json` (tar1090), or `http://<host>:<port>/data/aircraft.json` (ultrafeeder) |
| Flights to watch | Callsigns, registrations or hex codes. Optional, can be added later |
| Send a notification to | Phones / tablets (Mobile App) or any other notify service |
| Also notify when the flight leaves range | Off by default |
| Units | Automatic (default), Metric or Aviation |
| Polling interval | Default 15 s |
| Consider an aircraft gone after | Seconds without any message before the flight is no longer in range (default 60 s) |

### Which callsign?

ADS-B carries the **ICAO** callsign, not the airline flight number you see on your ticket:
French Bee `BF711` is transmitted as `FBU711`, Air France `AF123` as `AFR123`, etc.
If you are not sure, use the airline prefix with `*` (`FBU*`) or the aircraft registration.

### Distance

The distance comes from readsb (`r_dst`) when the receiver location is set; otherwise it is
computed from the Home Assistant home location.

## Notifications

Choose the devices in **Configure**. The notification looks like:

> **✈️ FBU711 in range of the receiver**
> AIRBUS A-350-900 – F-HREU
> 11 278 m · 42 km · 891 km/h

On a phone, tapping it opens the receiver's tar1090 page. An aircraft matching several
watched patterns (`FBU711` and `FBU*`) is notified once. Texts are in French when Home
Assistant is set to French, English otherwise.

## Automation example

For anything more custom, use the events:

```yaml
alias: Flight in range of the radar
triggers:
  - trigger: event
    event_type: flight_watch_flight_detected
actions:
  - action: notify.mobile_app_my_phone
    data:
      title: "✈️ {{ trigger.event.data.callsign }} in range"
      message: >
        {{ trigger.event.data.description | default(trigger.event.data.aircraft_type) }}
        at {{ trigger.event.data.altitude_ft }} ft,
        {{ trigger.event.data.distance_km }} km away.
```

Event data: `entry_id`, `watch` (the matching pattern), `hex`, `callsign`, `registration`,
`aircraft_type`, `description`, `operator`, `altitude_ft`, `on_ground`, `ground_speed_kt`,
`track_deg`, `vertical_rate_fpm`, `squawk`, `latitude`, `longitude`, `distance_km`,
`bearing_deg`, `seen_s` (fields the receiver does not know are left out).

No event is fired for aircraft already in range when Home Assistant starts.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

## License

MIT
