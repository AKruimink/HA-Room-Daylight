"""Sensor platform for Room Daylight."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from homeassistant.components.cover import ATTR_CURRENT_POSITION
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    LIGHT_LUX,
    PERCENTAGE,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .calculation import DaylightEstimate, estimate_room_daylight
from .const import (
    CONF_ARTIFICIAL_LIGHTS,
    CONF_AZIMUTH,
    CONF_CALIBRATION,
    CONF_COVER_ENTITY,
    CONF_DAYLIGHT_GAIN,
    CONF_DIFFUSE_BASE,
    CONF_FLOOR_AREA,
    CONF_HEIGHT,
    CONF_INDOOR_ILLUMINANCE,
    CONF_OUTSIDE_ILLUMINANCE,
    CONF_SENSOR_BLEND,
    CONF_SENSOR_MAX_RATIO,
    CONF_SENSOR_MIN_RATIO,
    CONF_SUN_ENTITY,
    CONF_TRANSMISSION,
    CONF_WIDTH,
    CONF_WINDOWS,
    DEFAULT_CALIBRATION,
    DEFAULT_DAYLIGHT_GAIN,
    DEFAULT_DIFFUSE_BASE,
    DEFAULT_SENSOR_BLEND,
    DEFAULT_SENSOR_MAX_RATIO,
    DEFAULT_SENSOR_MIN_RATIO,
    DEFAULT_SUN_ENTITY,
    DOMAIN,
)


@dataclass(slots=True, frozen=True)
class _DiagnosticSensorDefinition:
    """Description of one disabled-by-default diagnostic sensor."""

    key: str
    label: str
    value_fn: Callable[[DaylightEstimate], float | None]
    unit: str
    device_class: SensorDeviceClass | None = None
    precision: int = 0


DIAGNOSTIC_SENSORS = (
    _DiagnosticSensorDefinition(
        key="native_daylight",
        label="Native Daylight",
        value_fn=lambda estimate: estimate.base_lux,
        unit=LIGHT_LUX,
        device_class=SensorDeviceClass.ILLUMINANCE,
    ),
    _DiagnosticSensorDefinition(
        key="indoor_sensor_median",
        label="Indoor Sensor Median",
        value_fn=lambda estimate: estimate.indoor_median_lux,
        unit=LIGHT_LUX,
        device_class=SensorDeviceClass.ILLUMINANCE,
    ),
    _DiagnosticSensorDefinition(
        key="indoor_sensor_adjustment",
        label="Indoor Sensor Adjustment",
        value_fn=lambda estimate: estimate.sensor_adjustment_lux,
        unit=LIGHT_LUX,
        precision=1,
    ),
    _DiagnosticSensorDefinition(
        key="effective_daylight_ratio",
        label="Effective Daylight Ratio",
        value_fn=lambda estimate: estimate.effective_daylight_ratio_pct,
        unit=PERCENTAGE,
        precision=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Room Daylight sensors for one configured room."""
    primary = RoomDaylightSensor(entry)
    diagnostics = [
        RoomDaylightDiagnosticSensor(entry, primary, description)
        for description in DIAGNOSTIC_SENSORS
    ]
    async_add_entities([primary, *diagnostics])


def _numeric_state(state: State | None) -> float | None:
    """Return a state's numeric value, or ``None`` when it is unavailable."""
    if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        return None

    try:
        return float(state.state)
    except (TypeError, ValueError):
        return None


def _float_attribute(state: State | None, attribute: str) -> float | None:
    """Return a numeric state attribute when available."""
    if state is None:
        return None

    value = state.attributes.get(attribute)
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_window_covered(state: State | None) -> bool:
    """Return whether a linked cover or helper currently blocks the window."""
    if state is None:
        return False

    domain = state.entity_id.partition(".")[0]
    if domain == "cover":
        position = _float_attribute(state, ATTR_CURRENT_POSITION)
        if position is not None and position <= 0:
            return True
        return state.state in {"closed", "closing"}

    if domain in {"binary_sensor", "input_boolean"}:
        return state.state == STATE_ON

    return False


def _configured_entities(entry: ConfigEntry, key: str) -> list[str]:
    """Return an entity list from options, falling back to config-entry data."""
    return list(entry.options.get(key, entry.data.get(key, [])))


def _dependencies(entry: ConfigEntry) -> set[str]:
    """Return all Home Assistant entities that can change the room estimate."""
    entities: set[str] = set()

    if outside_entity := entry.data.get(CONF_OUTSIDE_ILLUMINANCE):
        entities.add(str(outside_entity))

    sun_entity = entry.data.get(CONF_SUN_ENTITY) or DEFAULT_SUN_ENTITY
    entities.add(str(sun_entity))

    entities.update(_configured_entities(entry, CONF_INDOOR_ILLUMINANCE))
    entities.update(_configured_entities(entry, CONF_ARTIFICIAL_LIGHTS))
    entities.update(
        str(window[CONF_COVER_ENTITY])
        for window in entry.data.get(CONF_WINDOWS, [])
        if window.get(CONF_COVER_ENTITY)
    )
    return entities


def _runtime_windows(
    hass: HomeAssistant,
    configured_windows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve configured windows against their current covering states."""
    windows: list[dict[str, Any]] = []
    covered_entities: list[str] = []

    for configured in configured_windows:
        cover_entity = configured.get(CONF_COVER_ENTITY)
        covered = bool(
            cover_entity
            and _is_window_covered(hass.states.get(str(cover_entity)))
        )
        if covered and cover_entity:
            covered_entities.append(str(cover_entity))

        window = {
            CONF_WIDTH: configured[CONF_WIDTH],
            CONF_HEIGHT: configured[CONF_HEIGHT],
            CONF_AZIMUTH: configured[CONF_AZIMUTH],
            "covered": covered,
        }
        if CONF_TRANSMISSION in configured:
            window[CONF_TRANSMISSION] = configured[CONF_TRANSMISSION]
        windows.append(window)

    return windows, covered_entities


def _active_lights(hass: HomeAssistant, entity_ids: list[str]) -> list[str]:
    """Return configured artificial lights that are currently on."""
    return [
        entity_id
        for entity_id in entity_ids
        if (state := hass.states.get(entity_id)) is not None
        and state.state == STATE_ON
    ]


def _indoor_sensor_values(
    hass: HomeAssistant,
    entity_ids: list[str],
    *,
    suppressed: bool,
) -> tuple[dict[str, float | None], list[float], list[str]]:
    """Collect indoor readings and the subset eligible for model correction."""
    readings: dict[str, float | None] = {}
    values: list[float] = []
    used_entities: list[str] = []

    for entity_id in entity_ids:
        value = _numeric_state(hass.states.get(entity_id))
        readings[entity_id] = round(value, 1) if value is not None else None
        if value is not None and not suppressed:
            values.append(value)
            used_entities.append(entity_id)

    return readings, values, used_entities


def _round_optional(value: float | None, digits: int = 1) -> float | None:
    """Round an optional diagnostic value."""
    return round(value, digits) if value is not None else None


def _window_diagnostics(
    configured_windows: list[dict[str, Any]],
    estimate: DaylightEstimate,
) -> list[dict[str, Any]]:
    """Return Home Assistant-friendly diagnostics for each configured window."""
    return [
        {
            "index": detail.index,
            "width_m": round(detail.width_m, 3),
            "height_m": round(detail.height_m, 3),
            "physical_area_m2": round(detail.physical_area_m2, 3),
            "effective_area_m2": round(detail.effective_area_m2, 3),
            "azimuth": round(detail.azimuth, 1),
            "transmission": round(detail.transmission, 3),
            "orientation_factor": round(detail.orientation_factor, 3),
            "covered": detail.covered,
            "cover_entity": configured.get(CONF_COVER_ENTITY),
            "contribution_lux": round(detail.contribution_lux, 1),
        }
        for configured, detail in zip(
            configured_windows,
            estimate.window_diagnostics,
            strict=False,
        )
    ]


def _model_parameters(entry: ConfigEntry) -> dict[str, float]:
    """Return the model parameters configured for this room."""
    return {
        "calibration": float(
            entry.data.get(CONF_CALIBRATION, DEFAULT_CALIBRATION)
        ),
        "daylight_gain": float(
            entry.data.get(CONF_DAYLIGHT_GAIN, DEFAULT_DAYLIGHT_GAIN)
        ),
        "diffuse_base": float(
            entry.data.get(CONF_DIFFUSE_BASE, DEFAULT_DIFFUSE_BASE)
        ),
        "sensor_blend": float(
            entry.data.get(CONF_SENSOR_BLEND, DEFAULT_SENSOR_BLEND)
        ),
        "sensor_min_ratio": float(
            entry.data.get(CONF_SENSOR_MIN_RATIO, DEFAULT_SENSOR_MIN_RATIO)
        ),
        "sensor_max_ratio": float(
            entry.data.get(CONF_SENSOR_MAX_RATIO, DEFAULT_SENSOR_MAX_RATIO)
        ),
    }



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
        self._signal = f"{DOMAIN}_{entry.entry_id}_diagnostics_update"

    @property
    def estimate(self) -> DaylightEstimate | None:
        """Return the latest calculation for diagnostic entities."""
        return self._estimate

    @property
    def native_value(self) -> float | None:
        """Return the estimated daylight in lux."""
        return round(self._estimate.final_lux) if self._estimate else None

    @property
    def available(self) -> bool:
        """Return whether the required source data is available."""
        return self._estimate is not None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return detailed model diagnostics."""
        return self._diagnostics

    async def async_added_to_hass(self) -> None:
        """Subscribe to every entity that can affect this room."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                sorted(_dependencies(self._entry)),
                self._handle_source_change,
            )
        )
        self._recalculate()

    @callback
    def _handle_source_change(self, _event: Event) -> None:
        """Recalculate after a source entity changes."""
        self._recalculate()
        self.async_write_ha_state()
        async_dispatcher_send(self.hass, self._signal)

    @callback
    def _recalculate(self) -> None:
        """Recalculate the estimate from current Home Assistant states."""
        outside_entity = self._entry.data.get(CONF_OUTSIDE_ILLUMINANCE)
        sun_entity = self._entry.data.get(CONF_SUN_ENTITY) or DEFAULT_SUN_ENTITY

        outside_state = (
            self.hass.states.get(str(outside_entity)) if outside_entity else None
        )
        outside_lux = _numeric_state(outside_state)

        sun_state = self.hass.states.get(str(sun_entity))
        sun_azimuth = _float_attribute(sun_state, "azimuth")
        sun_elevation = _float_attribute(sun_state, "elevation")

        unavailable_reason: str | None = None
        if not outside_entity:
            unavailable_reason = "outside_illuminance_not_configured"
        elif outside_lux is None:
            unavailable_reason = "outside_illuminance_unavailable"
        elif sun_state is None:
            unavailable_reason = "sun_entity_unavailable"
        elif sun_azimuth is None:
            unavailable_reason = "sun_azimuth_unavailable"
        elif sun_elevation is None:
            unavailable_reason = "sun_elevation_unavailable"

        if unavailable_reason is not None:
            self._estimate = None
            self._diagnostics = {
                "outside_illuminance_entity": outside_entity,
                "outside_illuminance_state": (
                    outside_state.state if outside_state is not None else None
                ),
                "sun_entity": sun_entity,
                "sun_state": sun_state.state if sun_state is not None else None,
                "source_available": False,
                "unavailable_reason": unavailable_reason,
            }
            return

        configured_windows = list(self._entry.data.get(CONF_WINDOWS, []))
        windows, covered_entities = _runtime_windows(self.hass, configured_windows)

        light_entities = _configured_entities(self._entry, CONF_ARTIFICIAL_LIGHTS)
        artificial_lights_on = _active_lights(self.hass, light_entities)
        indoor_sensors_suppressed = bool(artificial_lights_on)

        indoor_entities = _configured_entities(self._entry, CONF_INDOOR_ILLUMINANCE)
        indoor_readings, indoor_values, indoor_used = _indoor_sensor_values(
            self.hass,
            indoor_entities,
            suppressed=indoor_sensors_suppressed,
        )

        model_parameters = _model_parameters(self._entry)
        estimate = estimate_room_daylight(
            outside_lux=outside_lux,
            sun_azimuth=sun_azimuth,
            sun_elevation=sun_elevation,
            floor_area=float(self._entry.data[CONF_FLOOR_AREA]),
            windows=windows,
            indoor_lux_values=indoor_values,
            **model_parameters,
        )
        self._estimate = estimate
        self._diagnostics = {
            "outside_illuminance": round(outside_lux, 1),
            "outside_illuminance_entity": outside_entity,
            "sun_entity": sun_entity,
            "sun_azimuth": round(sun_azimuth, 1),
            "sun_elevation": round(sun_elevation, 1),
            "floor_area_m2": float(self._entry.data[CONF_FLOOR_AREA]),
            "base_estimate": round(estimate.base_lux, 1),
            "final_estimate": round(estimate.final_lux, 1),
            "effective_daylight_ratio_pct": round(
                estimate.effective_daylight_ratio_pct,
                2,
            ),
            "indoor_sensor_median": _round_optional(estimate.indoor_median_lux),
            "bounded_indoor_estimate": _round_optional(estimate.bounded_indoor_lux),
            "indoor_sensor_adjustment_lux": round(
                estimate.sensor_adjustment_lux,
                1,
            ),
            "indoor_sensor_adjustment_pct": round(
                estimate.sensor_adjustment_pct,
                2,
            ),
            "indoor_sensors_configured": len(indoor_entities),
            "indoor_sensors_used_count": estimate.indoor_sensor_count,
            "indoor_sensor_min_lux": _round_optional(estimate.indoor_sensor_min_lux),
            "indoor_sensor_max_lux": _round_optional(estimate.indoor_sensor_max_lux),
            "indoor_sensor_spread_lux": _round_optional(
                estimate.indoor_sensor_spread_lux
            ),
            "indoor_sensor_readings": indoor_readings,
            "indoor_sensors_used": indoor_used,
            "indoor_sensors_suppressed_by_lights": indoor_sensors_suppressed,
            "artificial_lights_on": artificial_lights_on,
            "windows_configured": len(windows),
            "windows_active": estimate.active_windows,
            "windows_covered": estimate.covered_windows,
            "covered_by": covered_entities,
            "window_contributions": _window_diagnostics(
                configured_windows,
                estimate,
            ),
            "model_parameters": model_parameters,
            "model_version": 3,
            "source_available": True,
        }


class RoomDaylightDiagnosticSensor(SensorEntity):
    """Disabled-by-default diagnostic value from the room calculation."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        entry: ConfigEntry,
        parent: RoomDaylightSensor,
        description: _DiagnosticSensorDefinition,
    ) -> None:
        """Initialise a diagnostic entity."""
        self._parent = parent
        self._description = description
        self._signal = f"{DOMAIN}_{entry.entry_id}_diagnostics_update"
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_name = f"{entry.title} {description.label}"
        self._attr_native_unit_of_measurement = description.unit
        self._attr_device_class = description.device_class
        self._attr_suggested_display_precision = description.precision

    @property
    def native_value(self) -> float | None:
        """Return the selected diagnostic value."""
        estimate = self._parent.estimate
        if estimate is None:
            return None

        value = self._description.value_fn(estimate)
        if value is None:
            return None

        return round(value, self._description.precision)

    @property
    def available(self) -> bool:
        """Return whether the selected diagnostic has a value."""
        estimate = self._parent.estimate
        return estimate is not None and self._description.value_fn(estimate) is not None

    async def async_added_to_hass(self) -> None:
        """Update whenever the primary room calculation changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                self._signal,
                self._handle_parent_update,
            )
        )

    @callback
    def _handle_parent_update(self) -> None:
        """Write a new state after the parent sensor recalculates."""
        self.async_write_ha_state()
