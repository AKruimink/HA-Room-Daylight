"""Pure data models used by Room Daylight.

This module intentionally has no Home Assistant imports.  Keeping the model layer
framework-independent makes the daylight and network algorithms easy to test.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .const import (
    AssumedState,
    CONF_AREA_ID,
    CONF_ARTIFICIAL_LIGHT_ENTITIES,
    CONF_ASSUMED_STATE,
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
    DEFAULT_DAYLIGHT_UTILISATION,
    DEFAULT_OPENING_ASSUMED_STATE,
    DEFAULT_SENSOR_CORRECTION_STRENGTH,
    DEFAULT_TRANSFER_EFFICIENCY,
    default_connection_assumed_state,
)


def _as_optional_str(value: Any) -> str | None:
    """Return a stripped string or ``None`` for an empty value."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_assumed_state(
    value: Any,
    default: AssumedState,
) -> AssumedState:
    """Return a valid assumed state, falling back defensively."""

    try:
        return AssumedState(str(value))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class ExteriorOpening:
    """An exterior glazed surface through which daylight enters a room."""

    opening_id: str
    name: str
    opening_type: str
    width_m: float
    height_m: float
    azimuth_deg: float
    tilt_deg: float
    transmission: float
    cover_entity: str | None = None
    assumed_state: AssumedState = DEFAULT_OPENING_ASSUMED_STATE

    @property
    def area_m2(self) -> float:
        """Return the glazed area in square metres."""

        return self.width_m * self.height_m

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ExteriorOpening:
        """Build an opening from config-entry data."""

        # Rooflights store their second dimension as ``length_m`` in the UI.
        height = data.get(CONF_HEIGHT, data.get(CONF_LENGTH))
        if height is None:
            raise ValueError("Exterior opening is missing its second dimension")

        return cls(
            opening_id=str(data[CONF_OPENING_ID]),
            name=str(data[CONF_OPENING_NAME]),
            opening_type=str(data[CONF_OPENING_TYPE]),
            width_m=float(data[CONF_WIDTH]),
            height_m=float(height),
            azimuth_deg=float(data[CONF_AZIMUTH]),
            tilt_deg=float(data[CONF_TILT]),
            transmission=float(data[CONF_TRANSMISSION]),
            cover_entity=_as_optional_str(data.get(CONF_COVER_ENTITY)),
            assumed_state=_as_assumed_state(
                data.get(CONF_ASSUMED_STATE),
                DEFAULT_OPENING_ASSUMED_STATE,
            ),
        )


@dataclass(frozen=True, slots=True)
class RoomDefinition:
    """Configuration for one room in the daylight network."""

    room_id: str
    name: str
    floor_area_m2: float
    openings: tuple[ExteriorOpening, ...] = ()
    indoor_lux_sensors: tuple[str, ...] = ()
    artificial_light_entities: tuple[str, ...] = ()
    area_id: str | None = None
    daylight_utilisation: float = DEFAULT_DAYLIGHT_UTILISATION
    sensor_correction_strength: float = DEFAULT_SENSOR_CORRECTION_STRENGTH

    @classmethod
    def from_mapping(
        cls,
        room_id: str,
        data: Mapping[str, Any],
        *,
        default_daylight_utilisation: float = DEFAULT_DAYLIGHT_UTILISATION,
        default_sensor_correction_strength: float = DEFAULT_SENSOR_CORRECTION_STRENGTH,
    ) -> RoomDefinition:
        """Build a room from config-subentry data."""

        room_model = data.get(CONF_ROOM_MODEL, {})
        return cls(
            room_id=room_id,
            name=str(data[CONF_ROOM_NAME]),
            floor_area_m2=float(data[CONF_FLOOR_AREA]),
            openings=tuple(
                ExteriorOpening.from_mapping(item)
                for item in data.get(CONF_OPENINGS, ())
            ),
            indoor_lux_sensors=tuple(data.get(CONF_INDOOR_LUX_SENSORS, ())),
            artificial_light_entities=tuple(
                data.get(CONF_ARTIFICIAL_LIGHT_ENTITIES, ())
            ),
            area_id=_as_optional_str(data.get(CONF_AREA_ID)),
            daylight_utilisation=float(
                room_model.get(
                    CONF_DAYLIGHT_UTILISATION, default_daylight_utilisation
                )
            ),
            sensor_correction_strength=float(
                room_model.get(
                    CONF_SENSOR_CORRECTION_STRENGTH,
                    default_sensor_correction_strength,
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ConnectionDefinition:
    """A physical opening that transfers daylight between two rooms."""

    connection_id: str
    name: str
    connection_type: str
    room_a: str
    room_b: str
    area_m2: float
    state_entity: str | None = None
    assumed_state: AssumedState = AssumedState.OPEN
    invert_state: bool = False
    closed_transmission: float = 0.0
    transfer_efficiency: float = DEFAULT_TRANSFER_EFFICIENCY

    @classmethod
    def from_mapping(
        cls,
        connection_id: str,
        data: Mapping[str, Any],
        *,
        default_transfer_efficiency: float = DEFAULT_TRANSFER_EFFICIENCY,
    ) -> ConnectionDefinition:
        """Build a connection from config-subentry data."""

        width = float(data[CONF_WIDTH])
        second_dimension = float(data.get(CONF_HEIGHT, data.get(CONF_LENGTH, 0.0)))
        connection_model = data.get(CONF_CONNECTION_MODEL, {})
        connection_type = str(data[CONF_CONNECTION_TYPE])
        return cls(
            connection_id=connection_id,
            name=str(data[CONF_CONNECTION_NAME]),
            connection_type=connection_type,
            room_a=str(data[CONF_ROOM_A]),
            room_b=str(data[CONF_ROOM_B]),
            area_m2=width * second_dimension,
            state_entity=_as_optional_str(data.get(CONF_STATE_ENTITY)),
            assumed_state=_as_assumed_state(
                data.get(CONF_ASSUMED_STATE),
                default_connection_assumed_state(connection_type),
            ),
            invert_state=bool(data.get(CONF_INVERT_STATE, False)),
            closed_transmission=float(data.get(CONF_CLOSED_TRANSMISSION, 0.0)),
            transfer_efficiency=float(
                connection_model.get(
                    CONF_TRANSFER_EFFICIENCY, default_transfer_efficiency
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class OpeningDiagnostic:
    """Runtime diagnostics for one exterior opening."""

    opening_id: str
    name: str
    area_m2: float
    incidence_factor: float
    sky_view_factor: float
    orientation_factor: float
    cover_openness: float
    effective_transmission: float
    contribution_lux: float
    cover_entity: str | None = None
    assumed_state: str | None = None
    state_description: str | None = None
    state_source: str | None = None


@dataclass(frozen=True, slots=True)
class NativeDaylightResult:
    """Result of exterior-daylight modelling for a room."""

    lux: float
    openings: tuple[OpeningDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class SensorCorrectionResult:
    """Result of applying local indoor-sensor correction."""

    estimated_lux: float
    sensor_median_lux: float | None
    adjustment_lux: float
    correction_applied: bool


@dataclass(frozen=True, slots=True)
class ConnectionDiagnostic:
    """How one connection influences a receiving room."""

    connection_id: str
    name: str
    other_room_id: str
    opening_area_m2: float
    transmission: float
    transfer_efficiency: float
    transfer_weight: float
    contribution_lux: float
    state_entity: str | None = None
    assumed_state: str | None = None
    state_description: str | None = None
    state_source: str | None = None


@dataclass(frozen=True, slots=True)
class RoomSnapshot:
    """A coherent calculated snapshot for one room."""

    room_id: str
    room_name: str
    native_lux: float
    modelled_lux: float
    estimated_lux: float
    transferred_lux: float
    sensor_median_lux: float | None
    sensor_adjustment_lux: float
    sensor_correction_applied: bool
    effective_daylight_ratio: float
    opening_diagnostics: tuple[OpeningDiagnostic, ...] = ()
    connection_diagnostics: tuple[ConnectionDiagnostic, ...] = ()
    network_iterations: int = 0
    network_converged: bool = True
    extra: Mapping[str, Any] = field(default_factory=dict)
