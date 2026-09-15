"""Tests for framework-independent configuration models."""

import pytest

from custom_components.room_daylight.const import (
    CONF_AREA_ID,
    CONF_ARTIFICIAL_LIGHT_ENTITIES,
    CONF_AZIMUTH,
    CONF_CLOSED_TRANSMISSION,
    CONF_CONNECTION_MODEL,
    CONF_CONNECTION_NAME,
    CONF_CONNECTION_TYPE,
    CONF_COVER_ENTITY,
    CONF_DAYLIGHT_UTILISATION,
    CONF_FLOOR_AREA,
    CONF_HEIGHT,
    CONF_INDOOR_LUX_SENSORS,
    CONF_INVERT_STATE,
    CONF_LENGTH,
    CONF_OPENING_ID,
    CONF_OPENING_NAME,
    CONF_OPENING_TYPE,
    CONF_OPENINGS,
    CONF_ROOM_A,
    CONF_ROOM_B,
    CONF_ROOM_MODEL,
    CONF_ROOM_NAME,
    CONF_SENSOR_CORRECTION_STRENGTH,
    CONF_STATE_ENTITY,
    CONF_TILT,
    CONF_TRANSFER_EFFICIENCY,
    CONF_TRANSMISSION,
    CONF_WIDTH,
)
from custom_components.room_daylight.models import (
    ConnectionDefinition,
    ExteriorOpening,
    RoomDefinition,
)


def _opening_data(**updates: object) -> dict[str, object]:
    data: dict[str, object] = {
        CONF_OPENING_ID: "opening-1",
        CONF_OPENING_NAME: "Patio doors",
        CONF_OPENING_TYPE: "wall",
        CONF_WIDTH: 2.4,
        CONF_HEIGHT: 2.0,
        CONF_AZIMUTH: 180.0,
        CONF_TILT: 90.0,
        CONF_TRANSMISSION: 0.7,
        CONF_COVER_ENTITY: " cover.patio ",
    }
    data.update(updates)
    return data


def test_exterior_opening_parses_area_and_optional_entity() -> None:
    """Opening mappings are normalised into a stable pure model."""

    opening = ExteriorOpening.from_mapping(_opening_data())

    assert opening.area_m2 == pytest.approx(4.8)
    assert opening.cover_entity == "cover.patio"
    assert opening.azimuth_deg == 180.0
    assert opening.tilt_deg == 90.0


def test_rooflight_uses_length_as_second_dimension() -> None:
    """Rooflight UI data maps length to the common opening height field."""

    data = _opening_data(**{CONF_OPENING_TYPE: "rooflight", CONF_LENGTH: 1.8})
    data.pop(CONF_HEIGHT)
    opening = ExteriorOpening.from_mapping(data)

    assert opening.height_m == pytest.approx(1.8)
    assert opening.area_m2 == pytest.approx(4.32)


def test_opening_requires_a_second_dimension() -> None:
    """Malformed persisted opening data fails clearly rather than silently."""

    data = _opening_data()
    data.pop(CONF_HEIGHT)
    with pytest.raises(ValueError, match="second dimension"):
        ExteriorOpening.from_mapping(data)


def test_room_mapping_parses_nested_model_and_entity_lists() -> None:
    """Room subentry data is converted to immutable runtime values."""

    room = RoomDefinition.from_mapping(
        "room-id",
        {
            CONF_ROOM_NAME: "Living room",
            CONF_FLOOR_AREA: 24.5,
            CONF_AREA_ID: " living_room ",
            CONF_OPENINGS: [_opening_data()],
            CONF_INDOOR_LUX_SENSORS: ["sensor.one", "sensor.two"],
            CONF_ARTIFICIAL_LIGHT_ENTITIES: ["light.ceiling"],
            CONF_ROOM_MODEL: {
                CONF_DAYLIGHT_UTILISATION: 0.42,
                CONF_SENSOR_CORRECTION_STRENGTH: 0.25,
            },
        },
    )

    assert room.room_id == "room-id"
    assert room.area_id == "living_room"
    assert room.openings[0].opening_id == "opening-1"
    assert room.indoor_lux_sensors == ("sensor.one", "sensor.two")
    assert room.artificial_light_entities == ("light.ceiling",)
    assert room.daylight_utilisation == pytest.approx(0.42)
    assert room.sensor_correction_strength == pytest.approx(0.25)


def test_room_mapping_uses_supplied_defaults_and_normalises_empty_area() -> None:
    """Parent defaults are used only when room-specific values are absent."""

    room = RoomDefinition.from_mapping(
        "internal-room",
        {
            CONF_ROOM_NAME: "Hall",
            CONF_FLOOR_AREA: 6.0,
            CONF_AREA_ID: "   ",
        },
        default_daylight_utilisation=0.31,
        default_sensor_correction_strength=0.18,
    )

    assert room.area_id is None
    assert room.openings == ()
    assert room.daylight_utilisation == pytest.approx(0.31)
    assert room.sensor_correction_strength == pytest.approx(0.18)


def test_connection_mapping_supports_height_and_nested_efficiency() -> None:
    """Door-style connection data produces the expected physical model."""

    connection = ConnectionDefinition.from_mapping(
        "connection-id",
        {
            CONF_CONNECTION_NAME: "Living room ↔ Hall",
            CONF_CONNECTION_TYPE: "door",
            CONF_ROOM_A: "living",
            CONF_ROOM_B: "hall",
            CONF_WIDTH: 0.85,
            CONF_HEIGHT: 2.0,
            CONF_STATE_ENTITY: " binary_sensor.door ",
            CONF_INVERT_STATE: True,
            CONF_CLOSED_TRANSMISSION: 0.15,
            CONF_CONNECTION_MODEL: {CONF_TRANSFER_EFFICIENCY: 0.6},
        },
    )

    assert connection.area_m2 == pytest.approx(1.7)
    assert connection.state_entity == "binary_sensor.door"
    assert connection.invert_state is True
    assert connection.closed_transmission == pytest.approx(0.15)
    assert connection.transfer_efficiency == pytest.approx(0.6)


def test_stairwell_connection_uses_length_and_default_efficiency() -> None:
    """Stairwell floor openings use width by length rather than door height."""

    connection = ConnectionDefinition.from_mapping(
        "stairs",
        {
            CONF_CONNECTION_NAME: "Landing ↔ Hall",
            CONF_CONNECTION_TYPE: "stairwell",
            CONF_ROOM_A: "landing",
            CONF_ROOM_B: "hall",
            CONF_WIDTH: 1.1,
            CONF_LENGTH: 2.4,
            CONF_STATE_ENTITY: "",
        },
        default_transfer_efficiency=0.72,
    )

    assert connection.area_m2 == pytest.approx(2.64)
    assert connection.state_entity is None
    assert connection.transfer_efficiency == pytest.approx(0.72)


def test_absent_optional_entities_normalise_to_none() -> None:
    """Omitted optional entity IDs stay absent in the runtime model."""

    data = _opening_data()
    data.pop(CONF_COVER_ENTITY)
    opening = ExteriorOpening.from_mapping(data)
    assert opening.cover_entity is None
