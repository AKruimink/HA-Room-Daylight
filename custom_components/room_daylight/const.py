"""Constants for the Room Daylight integration."""

from __future__ import annotations

from enum import StrEnum

DOMAIN = "room_daylight"
NAME = "Room Daylight"

SUBENTRY_TYPE_ROOM = "room"
SUBENTRY_TYPE_CONNECTION = "connection"

CONF_OUTDOOR_ILLUMINANCE_ENTITY = "outdoor_illuminance_entity"
CONF_SUN_ENTITY = "sun_entity"
CONF_MODEL_DEFAULTS = "model_defaults"
CONF_DIFFUSE_FRACTION = "diffuse_fraction"
CONF_GLAZING_TRANSMISSION = "glazing_transmission"
CONF_DAYLIGHT_UTILISATION = "daylight_utilisation"
CONF_TRANSFER_EFFICIENCY = "transfer_efficiency"
CONF_SENSOR_CORRECTION_STRENGTH = "sensor_correction_strength"

CONF_ROOM_NAME = "room_name"
CONF_FLOOR_AREA = "floor_area_m2"
CONF_AREA_ID = "area_id"
CONF_OPENING_COUNT = "opening_count"
CONF_OPENINGS = "openings"
CONF_INDOOR_LUX_SENSORS = "indoor_lux_sensors"
CONF_ARTIFICIAL_LIGHT_ENTITIES = "artificial_light_entities"
CONF_ROOM_MODEL = "room_model"

CONF_OPENING_ID = "id"
CONF_OPENING_NAME = "name"
CONF_OPENING_TYPE = "type"
CONF_WIDTH = "width_m"
CONF_HEIGHT = "height_m"
CONF_LENGTH = "length_m"
CONF_AZIMUTH = "azimuth_deg"
CONF_TILT = "tilt_deg"
CONF_ROOF_PITCH = "roof_pitch_deg"
CONF_COVER_ENTITY = "cover_entity"
CONF_TRANSMISSION = "transmission"
CONF_ASSUMED_STATE = "assumed_state"

OPENING_TYPE_WALL = "wall"
OPENING_TYPE_ROOFLIGHT = "rooflight"
OPENING_TYPE_CUSTOM = "custom"
OPENING_TYPES = (
    OPENING_TYPE_WALL,
    OPENING_TYPE_ROOFLIGHT,
    OPENING_TYPE_CUSTOM,
)

CONF_CONNECTION_NAME = "connection_name"
CONF_ROOM_A = "room_a"
CONF_ROOM_B = "room_b"
CONF_CONNECTION_TYPE = "connection_type"
CONF_STATE_ENTITY = "state_entity"
CONF_INVERT_STATE = "invert_state"
CONF_CLOSED_TRANSMISSION = "closed_transmission"
CONF_CONNECTION_MODEL = "connection_model"

CONNECTION_TYPE_DOOR = "door"
CONNECTION_TYPE_ARCHWAY = "archway"
CONNECTION_TYPE_STAIRWELL = "stairwell"
CONNECTION_TYPE_CUSTOM = "custom"
CONNECTION_TYPES = (
    CONNECTION_TYPE_DOOR,
    CONNECTION_TYPE_ARCHWAY,
    CONNECTION_TYPE_STAIRWELL,
    CONNECTION_TYPE_CUSTOM,
)


class AssumedState(StrEnum):
    """Fallback state used when an opening has no usable state entity."""

    OPEN = "open"
    CLOSED = "closed"


ASSUMED_STATES = tuple(state.value for state in AssumedState)
DEFAULT_OPENING_ASSUMED_STATE = AssumedState.OPEN
DEFAULT_CONNECTION_ASSUMED_STATES = {
    CONNECTION_TYPE_DOOR: AssumedState.CLOSED,
    CONNECTION_TYPE_ARCHWAY: AssumedState.OPEN,
    CONNECTION_TYPE_STAIRWELL: AssumedState.OPEN,
    CONNECTION_TYPE_CUSTOM: AssumedState.OPEN,
}


def default_connection_assumed_state(connection_type: str) -> AssumedState:
    """Return the initial assumed state for a connection type."""

    return DEFAULT_CONNECTION_ASSUMED_STATES.get(
        connection_type,
        AssumedState.OPEN,
    )


DEFAULT_SUN_ENTITY = "sun.sun"
DEFAULT_DIFFUSE_FRACTION = 0.35
DEFAULT_GLAZING_TRANSMISSION = 0.70
DEFAULT_DAYLIGHT_UTILISATION = 0.35
DEFAULT_TRANSFER_EFFICIENCY = 0.65
DEFAULT_SENSOR_CORRECTION_STRENGTH = 0.35

MIN_FLOOR_AREA_M2 = 0.5
MAX_FLOOR_AREA_M2 = 1000.0
MIN_OPENING_DIMENSION_M = 0.05
MAX_OPENING_DIMENSION_M = 30.0
MAX_EXTERIOR_OPENINGS = 20
MAX_NETWORK_ITERATIONS = 50
NETWORK_CONVERGENCE_LUX = 0.1
