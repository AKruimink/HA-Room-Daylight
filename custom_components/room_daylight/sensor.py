"""Estimated daylight sensor for Room Daylight."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.cover import ATTR_CURRENT_POSITION
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    LIGHT_LUX,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .calculation import DaylightEstimate, estimate_room_daylight
from .const import (
    CONF_ARTIFICIAL_LIGHTS,
    CONF_AZIMUTH,
    CONF_COVER_ENTITY,
    CONF_FLOOR_AREA,
    CONF_HEIGHT,
    CONF_INDOOR_ILLUMINANCE,
    CONF_OUTSIDE_ILLUMINANCE,
    CONF_SUN_ENTITY,
    CONF_WIDTH,
    CONF_WINDOWS,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Room Daylight sensor."""
    async_add_entities([RoomDaylightSensor(entry)])


def _numeric_state(state: State | None) -> float | None:
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _float_attr(state: State | None, attribute: str) -> float | None:
    if state is None:
        return None
    try:
        value = state.attributes.get(attribute)
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_window_covered(state: State | None) -> bool:
    """Treat a linked cover/binary helper as window coverage."""
    if state is None:
        return False

    domain = state.entity_id.split(".", 1)[0]
    if domain == "cover":
        position = _float_attr(state, ATTR_CURRENT_POSITION)
        if position is not None and position <= 0:
            return True
        return state.state in {"closed", "closing"}

    if domain in {"binary_sensor", "input_boolean"}:
        return state.state == STATE_ON

    return False


class RoomDaylightSensor(SensorEntity):
    """Estimated natural daylight in one configured room."""

    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = LIGHT_LUX
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialise the sensor."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_estimated_daylight"
        self._attr_name = f"{entry.title} Estimated Daylight"
        self._estimate: DaylightEstimate | None = None
        self._diagnostics: dict[str, Any] = {}

    @property
    def native_value(self) -> float | None:
        """Return the estimated daylight in lux."""
        if self._estimate is None:
            return None
        return round(self._estimate.final_lux)

    @property
    def available(self) -> bool:
        """Return whether source data is currently usable."""
        return self._estimate is not None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return useful model diagnostics."""
        return self._diagnostics

    async def async_added_to_hass(self) -> None:
        """Subscribe to every entity that can affect the estimate."""
        await super().async_added_to_hass()

        dependencies: set[str] = {
            self._entry.data[CONF_OUTSIDE_ILLUMINANCE],
            self._entry.data[CONF_SUN_ENTITY],
        }
        dependencies.update(
            self._entry.options.get(
                CONF_INDOOR_ILLUMINANCE,
                self._entry.data.get(CONF_INDOOR_ILLUMINANCE, []),
            )
        )
        dependencies.update(
            self._entry.options.get(
                CONF_ARTIFICIAL_LIGHTS,
                self._entry.data.get(CONF_ARTIFICIAL_LIGHTS, []),
            )
        )
        dependencies.update(
            window[CONF_COVER_ENTITY]
            for window in self._entry.data.get(CONF_WINDOWS, [])
            if window.get(CONF_COVER_ENTITY)
        )

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                sorted(dependencies),
                self._handle_source_change,
            )
        )
        self._recalculate()

    @callback
    def _handle_source_change(self, event: Event) -> None:
        """Recalculate after any source entity changes."""
        self._recalculate()
        self.async_write_ha_state()

    @callback
    def _recalculate(self) -> None:
        """Recalculate the estimate from current Home Assistant states."""
        outside_entity = self._entry.data[CONF_OUTSIDE_ILLUMINANCE]
        outside_state = self.hass.states.get(outside_entity)
        outside_lux = _numeric_state(outside_state)

        sun_entity = self._entry.data[CONF_SUN_ENTITY]
        sun_state = self.hass.states.get(sun_entity)
        sun_azimuth = _float_attr(sun_state, "azimuth")
        sun_elevation = _float_attr(sun_state, "elevation")

        if outside_lux is None or sun_azimuth is None or sun_elevation is None:
            self._estimate = None
            self._diagnostics = {
                "outside_illuminance_entity": outside_entity,
                "source_available": False,
            }
            return

        windows: list[dict[str, Any]] = []
        covered_entities: list[str] = []
        for configured in self._entry.data.get(CONF_WINDOWS, []):
            cover_entity = configured.get(CONF_COVER_ENTITY)
            covered = False
            if cover_entity:
                covered = _is_window_covered(self.hass.states.get(cover_entity))
                if covered:
                    covered_entities.append(cover_entity)

            windows.append(
                {
                    CONF_WIDTH: configured[CONF_WIDTH],
                    CONF_HEIGHT: configured[CONF_HEIGHT],
                    CONF_AZIMUTH: configured[CONF_AZIMUTH],
                    "covered": covered,
                }
            )

        light_entities = self._entry.options.get(
            CONF_ARTIFICIAL_LIGHTS,
            self._entry.data.get(CONF_ARTIFICIAL_LIGHTS, []),
        )
        artificial_light_on = any(
            (state := self.hass.states.get(entity_id)) is not None
            and state.state == STATE_ON
            for entity_id in light_entities
        )

        indoor_values: list[float] = []
        indoor_used: list[str] = []
        if not artificial_light_on:
            indoor_entities = self._entry.options.get(
                CONF_INDOOR_ILLUMINANCE,
                self._entry.data.get(CONF_INDOOR_ILLUMINANCE, []),
            )
            for entity_id in indoor_entities:
                value = _numeric_state(self.hass.states.get(entity_id))
                if value is not None:
                    indoor_values.append(value)
                    indoor_used.append(entity_id)

        estimate = estimate_room_daylight(
            outside_lux=outside_lux,
            sun_azimuth=sun_azimuth,
            sun_elevation=sun_elevation,
            floor_area=float(self._entry.data[CONF_FLOOR_AREA]),
            windows=windows,
            indoor_lux_values=indoor_values,
        )
        self._estimate = estimate

        self._diagnostics = {
            "outside_illuminance": round(outside_lux, 1),
            "outside_illuminance_entity": outside_entity,
            "sun_entity": sun_entity,
            "sun_azimuth": round(sun_azimuth, 1),
            "sun_elevation": round(sun_elevation, 1),
            "base_estimate": round(estimate.base_lux, 1),
            "indoor_sensor_median": (
                round(estimate.indoor_median_lux, 1)
                if estimate.indoor_median_lux is not None
                else None
            ),
            "bounded_indoor_estimate": (
                round(estimate.bounded_indoor_lux, 1)
                if estimate.bounded_indoor_lux is not None
                else None
            ),
            "indoor_sensors_used": indoor_used,
            "indoor_sensors_suppressed_by_lights": artificial_light_on,
            "windows_configured": len(windows),
            "windows_active": estimate.active_windows,
            "windows_covered": estimate.covered_windows,
            "covered_by": covered_entities,
            "floor_area_m2": float(self._entry.data[CONF_FLOOR_AREA]),
            "model_version": 2,
            "source_available": True,
        }
