"""End-to-end tests: config flow, entities and events."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.flight_watch.const import (
    CONF_CALLSIGNS,
    CONF_MAX_SEEN,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    DOMAIN,
    EVENT_FLIGHT_DETECTED,
    EVENT_FLIGHT_LOST,
)

URL = "http://receiver.local/tar1090/data/aircraft.json"

EMPTY = {"now": 1, "messages": 10, "aircraft": [{"hex": "3c1234", "flight": "AFR123  ", "seen": 1}]}
WITH_FLIGHT = {
    "now": 2,
    "messages": 20,
    "aircraft": [
        {"hex": "3c1234", "flight": "AFR123  ", "seen": 1},
        {
            "hex": "39a4b2",
            "flight": "FBU711  ",
            "r": "F-HREU",
            "t": "A359",
            "alt_baro": 37000,
            "gs": 480.2,
            "track": 95.1,
            "lat": 48.2,
            "lon": -1.5,
            "r_dst": 20.0,
            "r_dir": 270.0,
            "seen": 0.5,
        },
        {"hex": "39a4b3", "flight": "FBU720", "seen": 500},
    ],
}


async def _setup(hass: HomeAssistant, aioclient_mock, payload, callsigns=("FBU711",)):
    aioclient_mock.get(URL, json=payload)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="receiver.local",
        data={CONF_URL: URL},
        options={CONF_CALLSIGNS: list(callsigns), CONF_SCAN_INTERVAL: 15, CONF_MAX_SEEN: 60},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL, json=EMPTY)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_URL: URL,
            CONF_CALLSIGNS: ["fbu711", "FBU711", "f-hreu, FBU*"],
            CONF_SCAN_INTERVAL: 20,
            CONF_MAX_SEEN: 60,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_URL: URL}
    assert result["options"][CONF_CALLSIGNS] == ["FBU711", "F-HREU", "FBU*"]


async def test_config_flow_invalid(hass: HomeAssistant, aioclient_mock) -> None:
    aioclient_mock.get(URL, json={"hello": "world"})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL, CONF_SCAN_INTERVAL: 15, CONF_MAX_SEEN: 60}
    )
    assert result["errors"] == {"base": "invalid_data"}


async def test_entities_and_events(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock, EMPTY, callsigns=("FBU711", "FBU*"))
    detected = async_capture_events(hass, EVENT_FLIGHT_DETECTED)
    lost = async_capture_events(hass, EVENT_FLIGHT_LOST)

    assert hass.states.get("binary_sensor.flight_fbu711_in_range").state == "off"
    assert hass.states.get("sensor.receiver_local_aircraft_tracked").state == "1"

    coordinator = entry.runtime_data
    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=WITH_FLIGHT)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get("binary_sensor.flight_fbu711_in_range")
    assert state.state == "on"
    assert state.attributes["registration"] == "F-HREU"
    assert hass.states.get("sensor.flight_fbu711_distance").state == "37.0"
    assert hass.states.get("sensor.flight_fbu711_altitude").state == "37000"
    assert hass.states.get("sensor.flight_fbu711_ground_speed").state == "480.2"
    # FBU720 is too old (seen 500 s) and must not match the prefix
    assert hass.states.get("binary_sensor.flight_fbu_in_range").attributes["match_count"] == 1
    assert {e.data["watch"] for e in detected} == {"FBU711", "FBU*"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=EMPTY)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.flight_fbu711_in_range").state == "off"
    assert hass.states.get("sensor.flight_fbu711_distance").state == "unknown"
    assert len(lost) == 2 and lost[0].data["callsign"] == "FBU711"


async def test_no_event_on_startup(hass: HomeAssistant, aioclient_mock) -> None:
    detected = async_capture_events(hass, EVENT_FLIGHT_DETECTED)
    await _setup(hass, aioclient_mock, WITH_FLIGHT)
    assert hass.states.get("binary_sensor.flight_fbu711_in_range").state == "on"
    assert detected == []


async def test_options_remove_flight(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock, EMPTY, callsigns=("FBU711", "AFR123"))
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_CALLSIGNS: ["AFR123"], CONF_SCAN_INTERVAL: 15, CONF_MAX_SEEN: 60}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.flight_afr123_in_range").state == "on"
    assert hass.states.get("binary_sensor.flight_fbu711_in_range") is None


async def test_notifications(hass: HomeAssistant, aioclient_mock) -> None:
    from pytest_homeassistant_custom_component.common import async_mock_service

    from custom_components.flight_watch.const import CONF_NOTIFY, CONF_NOTIFY_LOST

    calls = async_mock_service(hass, "notify", "mobile_app_iphone_test")
    aioclient_mock.get(URL, json=EMPTY)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="receiver.local",
        data={CONF_URL: URL},
        options={
            CONF_CALLSIGNS: ["FBU711", "FBU*"],
            CONF_NOTIFY: ["mobile_app_iphone_test"],
            CONF_NOTIFY_LOST: True,
            CONF_SCAN_INTERVAL: 15,
            CONF_MAX_SEEN: 60,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data

    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=WITH_FLIGHT)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    # One notification even though the aircraft matches two patterns
    assert len(calls) == 1
    assert "FBU711" in calls[0].data["title"]
    assert "F-HREU" in calls[0].data["message"]
    assert calls[0].data["data"]["url"] == "http://receiver.local/tar1090"

    aioclient_mock.clear_requests()
    aioclient_mock.get(URL, json=EMPTY)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(calls) == 2
    assert "FBU711" in calls[1].data["title"]


async def test_notify_options_list(hass: HomeAssistant, aioclient_mock) -> None:
    from pytest_homeassistant_custom_component.common import async_mock_service

    async_mock_service(hass, "notify", "mobile_app_iphone_test")
    async_mock_service(hass, "notify", "send_message")
    entry = await _setup(hass, aioclient_mock, EMPTY)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    notify_key = next(k for k in schema if k == "notify")
    values = [o["value"] for o in schema[notify_key].config["options"]]
    assert values == ["mobile_app_iphone_test"]
