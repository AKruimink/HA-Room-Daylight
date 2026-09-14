"""Estimated daylight sensors for Room Daylight."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from homeassistant.components.cover import ATTR_CURRENT_POSITION
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    LIGHT_LUX,
    PERCENTAGE,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity import EntityCategory
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
    DEFAULT_DAYLIGHT_GAIN,
    DEFAULT_DIFFUSE_BASE,
    DEFAULT_SENSOR_BLEND,
    DEFAULT_SENSOR_MAX_RATIO,
    DEFAULT_SENSOR_MIN_RATIO,
    DEFAULT_WINDOW_TRANSMISSION,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Room Daylight sensors for one configured room."""
    primary = RoomDaylightSensor(entry)
    async_add_entities(
        [
            primary,
            RoomDaylightDiagnosticSensor(
                entry=entry,
                parent=primary,
                key="native_daylight",
                label="Native Daylight",
                value_fn=lambda estimate: estimate.base_lux,
                unit=LIGHT_LUX,
                device_class=SensorDeviceClass.ILLUMINANCE,
                precision=0,
            ),
            RoomDaylightDiagnosticSensor(
                entry=entry,
                parent=primary,
                key="indoor_sensor_median",
                label="Indoor Sensor Median",
                value_fn=lambda estimate: estimate.indoor_median_lux,
                unit=LIGHT_LUX,
                device_class=SensorDeviceClass.ILLUMINANCE,
                precision=0,
            ),
            RoomDaylightDiagnosticSensor(
                entry=entry,
                parent=primary,
                key="indoor_sensor_adjustment",
                label="Indoor Sensor Adjustment",
                value_fn=lambda estimate: estimate.sensor_adjustment_lux,
                unit=LIGHT_LUX,
                device_class=None,
                precision=1,
            ),
            RoomDaylightDiagnosticSensor(
                entry=entry,
                parent=primary,
                key="effective_daylight_ratio",
                label="Effective Daylight Ratio",
                value_fn=lambda estimate: estimate.effective_daylight_ratio_pct,
                unit=PERCENTAGE,
                device_class=None,
                precision=2,
            ),
        ]
    )


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
        self._signal = f"{DOMAIN}_{entry.entry_id}_diagnostics_update"

    @property
    def estimate(self) -> DaylightEstimate | None:
        """Return the latest calculation for diagnostic entities."""
        return self._estimate

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
        """Return detailed model diagnostics."""
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
        async_dispatcher_send(self.hass, self._signal)

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
                "sun_entity": sun_entity,
                "source_available": False,
            }
            return

        configured_windows = self._entry.data.get(CONF_WINDOWS, [])
        windows: list[dict[str, Any]] = []
        covered_entities: list[str] = []
        for configured in configured_windows:
            cover_entity = configured.get(CONF_COVER_ENTITY)
            covered = False
            if cover_entity:
                covered = _is_window_covered(self.hass.states.get(cover_entity))
                if covered:
                    covered_entities.append(cover_entity)

            window = {
                CONF_WIDTH: configured[CONF_WIDTH],
                CONF_HEIGHT: configured[CONF_HEIGHT],
                CONF_AZIMUTH: configured[CONF_AZIMUTH],
                "covered": covered,
            }
            if "transmission" in configured:
                window["transmission"] = configured["transmission"]
            windows.append(window)

        light_entities = self._entry.options.get(
            CONF_ARTIFICIAL_LIGHTS,
            self._entry.data.get(CONF_ARTIFICIAL_LIGHTS, []),
        )
        artificial_lights_on = [
            entity_id
            for entity_id in light_entities
            if (state := self.hass.states.get(entity_id)) is not None
            and state.state == STATE_ON
        ]
        artificial_light_on = bool(artificial_lights_on)

        indoor_entities = self._entry.options.get(
            CONF_INDOOR_ILLUMINANCE,
            self._entry.data.get(CONF_INDOOR_ILLUMINANCE, []),
        )
        indoor_readings: dict[str, float | None] = {}
        indoor_values: list[float] = []
        indoor_used: list[str] = []
        for entity_id in indoor_entities:
            value = _numeric_state(self.hass.states.get(entity_id))
            indoor_readings[entity_id] = round(value, 1) if value is not None else None
            if not artificial_light_on and value is not None:
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

        window_details: list[dict[str, Any]] = []
        for configured, detail in zip(
            configured_windows, estimate.window_diagnostics, strict=False
        ):
            window_details.append(
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
            )

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
                estimate.effective_daylight_ratio_pct, 2
            ),
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
            "indoor_sensor_adjustment_lux": round(
                estimate.sensor_adjustment_lux, 1
            ),
            "indoor_sensor_adjustment_pct": round(
                estimate.sensor_adjustment_pct, 2
            ),
            "indoor_sensors_configured": len(indoor_entities),
            "indoor_sensors_used_count": estimate.indoor_sensor_count,
            "indoor_sensor_min_lux": (
                round(estimate.indoor_sensor_min_lux, 1)
                if estimate.indoor_sensor_min_lux is not None
                else None
            ),
            "indoor_sensor_max_lux": (
                round(estimate.indoor_sensor_max_lux, 1)
                if estimate.indoor_sensor_max_lux is not None
                else None
            ),
            "indoor_sensor_spread_lux": (
                round(estimate.indoor_sensor_spread_lux, 1)
                if estimate.indoor_sensor_spread_lux is not None
                else None
            ),
            "indoor_sensor_readings": indoor_readings,
            "indoor_sensors_used": indoor_used,
            "indoor_sensors_suppressed_by_lights": artificial_light_on,
            "artificial_lights_on": artificial_lights_on,
            "windows_configured": len(windows),
            "windows_active": estimate.active_windows,
            "windows_covered": estimate.covered_windows,
            "covered_by": covered_entities,
            "window_contributions": window_details,
            "model_parameters": {
                "calibration": 1.0,
                "daylight_gain": DEFAULT_DAYLIGHT_GAIN,
                "diffuse_base": DEFAULT_DIFFUSE_BASE,
                "window_transmission": DEFAULT_WINDOW_TRANSMISSION,
                "sensor_blend": DEFAULT_SENSOR_BLEND,
                "sensor_min_ratio": DEFAULT_SENSOR_MIN_RATIO,
                "sensor_max_ratio": DEFAULT_SENSOR_MAX_RATIO,
            },
            "model_version": 2,
            "source_available": True,
        }


class RoomDaylightDiagnosticSensor(SensorEntity):
    """Disabled-by-default diagnostic sensor backed by the room calculation."""

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        *,
        entry: ConfigEntry,
        parent: RoomDaylightSensor,
        key: str,
        label: str,
        value_fn: Callable[[DaylightEstimate], float | None],
        unit: str,
        device_class: SensorDeviceClass | None,
        precision: int,
    ) -> None:
        """Initialise a diagnostic entity."""
        self._parent = parent
        self._value_fn = value_fn
        self._signal = f"{DOMAIN}_{entry.entry_id}_diagnostics_update"
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = f"{entry.title} {label}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_suggested_display_precision = precision

    @property
    def native_value(self) -> float | None:
        """Return the selected diagnostic value."""
        estimate = self._parent.estimate
        if estimate is None:
            return None
        value = self._value_fn(estimate)
        if value is None:
            return None
        return round(value, self._attr_suggested_display_precision)

    @property
    def available(self) -> bool:
        """Return whether the selected diagnostic has a value."""
        estimate = self._parent.estimate
        return estimate is not None and self._value_fn(estimate) is not None

    async def async_added_to_hass(self) -> None:
        """Update when the primary room calculation changes."""
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
