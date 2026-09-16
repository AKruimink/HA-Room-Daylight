"""Central event-driven coordinator for Room Daylight."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from typing import Any

from homeassistant.components.cover import ATTR_CURRENT_POSITION
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .calculation import apply_sensor_correction, clamp, estimate_native_daylight
from .const import (
    CONF_DAYLIGHT_UTILISATION,
    CONF_DIFFUSE_FRACTION,
    CONF_MODEL_DEFAULTS,
    CONF_OUTDOOR_ILLUMINANCE_ENTITY,
    CONF_SENSOR_CORRECTION_STRENGTH,
    CONF_SUN_ENTITY,
    CONF_TRANSFER_EFFICIENCY,
    DEFAULT_DAYLIGHT_UTILISATION,
    DEFAULT_DIFFUSE_FRACTION,
    DEFAULT_SENSOR_CORRECTION_STRENGTH,
    DEFAULT_SUN_ENTITY,
    DEFAULT_TRANSFER_EFFICIENCY,
    DOMAIN,
    SUBENTRY_TYPE_CONNECTION,
    SUBENTRY_TYPE_ROOM,
)
from .models import (
    ConnectionDefinition,
    ExteriorOpening,
    RoomDefinition,
    RoomSnapshot,
)
from .network import NetworkConnection, solve_room_network
from .openness import (
    ResolvedOpenness,
    assumed_openness,
    resolve_binary_openness,
    resolve_cover_openness,
)

_LOGGER = logging.getLogger(__name__)

SUN_ATTR_AZIMUTH = "azimuth"
SUN_ATTR_ELEVATION = "elevation"


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Parse a finite float, falling back safely for unavailable state data."""

    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _state_lux(state: State | None) -> float | None:
    """Return a non-negative numeric entity state, or ``None`` if unusable."""

    if state is None:
        return None
    value = _safe_float(state.state, default=math.nan)
    if not math.isfinite(value) or value < 0.0:
        return None
    return value


class RoomDaylightCoordinator(DataUpdateCoordinator[dict[str, RoomSnapshot]]):
    """Calculate one coherent whole-house daylight snapshot on state changes."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise coordinator and parse immutable config-entry data."""

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
        )
        self.entry = entry
        self.rooms: dict[str, RoomDefinition] = {}
        self.connections: tuple[ConnectionDefinition, ...] = ()
        self._unsub_state_listener: Callable[[], None] | None = None
        self._diffuse_fraction = DEFAULT_DIFFUSE_FRACTION
        self._parse_configuration()

    def _parse_configuration(self) -> None:
        """Build framework-independent room/connection definitions."""

        model = self.entry.data.get(CONF_MODEL_DEFAULTS, {})
        self._diffuse_fraction = float(
            model.get(CONF_DIFFUSE_FRACTION, DEFAULT_DIFFUSE_FRACTION)
        )
        default_daylight_utilisation = float(
            model.get(CONF_DAYLIGHT_UTILISATION, DEFAULT_DAYLIGHT_UTILISATION)
        )
        default_sensor_correction = float(
            model.get(
                CONF_SENSOR_CORRECTION_STRENGTH,
                DEFAULT_SENSOR_CORRECTION_STRENGTH,
            )
        )
        default_transfer_efficiency = float(
            model.get(CONF_TRANSFER_EFFICIENCY, DEFAULT_TRANSFER_EFFICIENCY)
        )

        rooms: dict[str, RoomDefinition] = {}
        for subentry in self.entry.subentries.values():
            if subentry.subentry_type != SUBENTRY_TYPE_ROOM:
                continue
            room = RoomDefinition.from_mapping(
                subentry.subentry_id,
                subentry.data,
                default_daylight_utilisation=default_daylight_utilisation,
                default_sensor_correction_strength=default_sensor_correction,
            )
            rooms[room.room_id] = room
        self.rooms = rooms

        connections: list[ConnectionDefinition] = []
        for subentry in self.entry.subentries.values():
            if subentry.subentry_type != SUBENTRY_TYPE_CONNECTION:
                continue
            connection = ConnectionDefinition.from_mapping(
                subentry.subentry_id,
                subentry.data,
                default_transfer_efficiency=default_transfer_efficiency,
            )
            if connection.room_a not in rooms or connection.room_b not in rooms:
                _LOGGER.warning(
                    "Ignoring connection %s because one of its rooms no longer exists",
                    connection.name,
                )
                continue
            connections.append(connection)
        self.connections = tuple(connections)

    @property
    def outdoor_entity_id(self) -> str:
        """Return the configured global outdoor illuminance entity ID."""

        return str(self.entry.data[CONF_OUTDOOR_ILLUMINANCE_ENTITY])

    @property
    def sun_entity_id(self) -> str:
        """Return the configured sun entity ID."""

        return str(self.entry.data.get(CONF_SUN_ENTITY, DEFAULT_SUN_ENTITY))

    @property
    def dependency_entity_ids(self) -> set[str]:
        """Return all Home Assistant entities that can change a calculation."""

        entities = {self.outdoor_entity_id, self.sun_entity_id}
        for room in self.rooms.values():
            entities.update(room.indoor_lux_sensors)
            entities.update(room.artificial_light_entities)
            entities.update(
                opening.cover_entity
                for opening in room.openings
                if opening.cover_entity is not None
            )
        entities.update(
            connection.state_entity
            for connection in self.connections
            if connection.state_entity is not None
        )
        return entities

    async def async_start(self) -> None:
        """Subscribe to dependencies and publish the initial snapshot."""

        entity_ids = self.dependency_entity_ids
        if entity_ids:
            self._unsub_state_listener = async_track_state_change_event(
                self.hass,
                entity_ids,
                self._async_state_changed,
            )
        self._async_recalculate()

    async def async_shutdown(self) -> None:
        """Remove push subscriptions and shut down coordinator internals."""

        if self._unsub_state_listener is not None:
            self._unsub_state_listener()
            self._unsub_state_listener = None
        await super().async_shutdown()

    @callback
    def _async_state_changed(self, _event: Event) -> None:
        """Recalculate immediately when any dependency changes."""

        self._async_recalculate()

    @callback
    def _async_recalculate(self) -> None:
        """Calculate and publish one coherent whole-network snapshot."""

        self.async_set_updated_data(self._calculate_snapshot())

    async def _async_update_data(self) -> dict[str, RoomSnapshot]:
        """Return a fresh snapshot for explicit coordinator refresh requests."""

        return self._calculate_snapshot()

    def _calculate_snapshot(self) -> dict[str, RoomSnapshot]:
        """Calculate one coherent whole-network snapshot from current states."""

        outdoor_value = _state_lux(self.hass.states.get(self.outdoor_entity_id))
        outdoor_available = outdoor_value is not None
        outdoor_lux = outdoor_value or 0.0
        sun_state = self.hass.states.get(self.sun_entity_id)
        sun_available = (
            sun_state is not None
            and sun_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE)
        )
        sun_azimuth = (
            _safe_float(sun_state.attributes.get(SUN_ATTR_AZIMUTH), 180.0)
            if sun_available
            else 180.0
        )
        sun_elevation = (
            _safe_float(sun_state.attributes.get(SUN_ATTR_ELEVATION), -90.0)
            if sun_available
            else -90.0
        )

        native_results = {}
        native_lux = {}
        floor_areas = {}
        for room_id, room in self.rooms.items():
            cover_states = {
                opening.opening_id: self._opening_openness(opening)
                for opening in room.openings
            }
            result = estimate_native_daylight(
                room,
                outdoor_lux=outdoor_lux,
                sun_azimuth_deg=sun_azimuth,
                sun_elevation_deg=sun_elevation,
                diffuse_fraction=self._diffuse_fraction,
                cover_openness={
                    opening_id: state.openness
                    for opening_id, state in cover_states.items()
                },
                cover_state_descriptions={
                    opening_id: state.description
                    for opening_id, state in cover_states.items()
                },
                cover_state_sources={
                    opening_id: state.source
                    for opening_id, state in cover_states.items()
                },
            )
            native_results[room_id] = result
            native_lux[room_id] = result.lux
            floor_areas[room_id] = room.floor_area_m2

        runtime_connections = tuple(
            self._runtime_connection(connection) for connection in self.connections
        )
        network = solve_room_network(native_lux, floor_areas, runtime_connections)

        snapshots: dict[str, RoomSnapshot] = {}
        for room_id, room in self.rooms.items():
            modelled_lux = network.room_lux.get(room_id, native_lux[room_id])
            sensor_values = (
                _state_lux(self.hass.states.get(entity_id))
                for entity_id in room.indoor_lux_sensors
            )
            sensor_correction_blocked = self._sensor_correction_blocked(room)
            correction = apply_sensor_correction(
                modelled_lux,
                outdoor_lux=outdoor_lux,
                sensor_values=sensor_values,
                correction_strength=room.sensor_correction_strength,
                artificial_lights_active=sensor_correction_blocked,
            )
            effective_ratio = (
                correction.estimated_lux / outdoor_lux if outdoor_lux > 0.0 else 0.0
            )
            snapshots[room_id] = RoomSnapshot(
                room_id=room_id,
                room_name=room.name,
                native_lux=native_lux[room_id],
                modelled_lux=modelled_lux,
                estimated_lux=correction.estimated_lux,
                transferred_lux=max(0.0, modelled_lux - native_lux[room_id]),
                sensor_median_lux=correction.sensor_median_lux,
                sensor_adjustment_lux=correction.adjustment_lux,
                sensor_correction_applied=correction.correction_applied,
                effective_daylight_ratio=effective_ratio,
                opening_diagnostics=native_results[room_id].openings,
                connection_diagnostics=network.diagnostics.get(room_id, ()),
                network_iterations=network.iterations,
                network_converged=network.converged,
                extra={
                    "outdoor_lux": outdoor_lux,
                    "outdoor_illuminance_available": outdoor_available,
                    "sun_available": sun_available,
                    "sun_azimuth_deg": sun_azimuth,
                    "sun_elevation_deg": sun_elevation,
                    "sensor_correction_blocked": sensor_correction_blocked,
                },
            )

        return snapshots

    def _opening_openness(self, opening: ExteriorOpening) -> ResolvedOpenness:
        """Resolve an exterior opening's blind/curtain openness."""

        if opening.cover_entity is None:
            return assumed_openness(opening.assumed_state)

        state = self.hass.states.get(opening.cover_entity)
        return resolve_cover_openness(
            state.state if state is not None else None,
            position=(
                state.attributes.get(ATTR_CURRENT_POSITION)
                if state is not None
                else None
            ),
            assumed_state=opening.assumed_state,
        )

    def _runtime_connection(
        self, connection: ConnectionDefinition
    ) -> NetworkConnection:
        """Resolve a connection's current openness and effective transmission."""

        if connection.state_entity is None:
            resolved = assumed_openness(connection.assumed_state)
        else:
            state = self.hass.states.get(connection.state_entity)
            if state is not None and state.domain == "cover":
                resolved = resolve_cover_openness(
                    state.state,
                    position=state.attributes.get(ATTR_CURRENT_POSITION),
                    assumed_state=connection.assumed_state,
                    invert=connection.invert_state,
                )
            else:
                resolved = resolve_binary_openness(
                    state.state if state is not None else None,
                    assumed_state=connection.assumed_state,
                    invert=connection.invert_state,
                )

        closed = clamp(connection.closed_transmission, 0.0, 1.0)
        transmission = closed + (resolved.openness * (1.0 - closed))
        return NetworkConnection(
            connection_id=connection.connection_id,
            name=connection.name,
            room_a=connection.room_a,
            room_b=connection.room_b,
            opening_area_m2=connection.area_m2,
            transmission=transmission,
            transfer_efficiency=connection.transfer_efficiency,
            state_entity=connection.state_entity,
            assumed_state=connection.assumed_state.value,
            state_description=resolved.description,
            state_source=resolved.source,
        )

    def _sensor_correction_blocked(self, room: RoomDefinition) -> bool:
        """Return whether artificial-light state makes sensor correction unsafe."""

        for entity_id in room.artificial_light_entities:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                return True
            if state.state == STATE_ON:
                return True
        return False
