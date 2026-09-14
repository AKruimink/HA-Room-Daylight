"""Pure daylight estimation maths for Room Daylight."""

from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import median
from typing import Any, Iterable, Mapping

from .const import (
    CONF_AZIMUTH,
    CONF_HEIGHT,
    CONF_WIDTH,
    DEFAULT_DAYLIGHT_GAIN,
    DEFAULT_DIFFUSE_BASE,
    DEFAULT_SENSOR_BLEND,
    DEFAULT_SENSOR_MAX_RATIO,
    DEFAULT_SENSOR_MIN_RATIO,
    DEFAULT_WINDOW_TRANSMISSION,
)


@dataclass(slots=True, frozen=True)
class WindowEstimate:
    """Diagnostic result for one configured exterior opening."""

    index: int
    width_m: float
    height_m: float
    physical_area_m2: float
    effective_area_m2: float
    azimuth: float
    transmission: float
    orientation_factor: float
    covered: bool
    contribution_lux: float


@dataclass(slots=True, frozen=True)
class DaylightEstimate:
    """Result and diagnostics for one daylight calculation."""

    final_lux: float
    base_lux: float
    indoor_median_lux: float | None
    bounded_indoor_lux: float | None
    active_windows: int
    covered_windows: int
    total_window_factor: float
    effective_daylight_ratio_pct: float
    sensor_adjustment_lux: float
    sensor_adjustment_pct: float
    indoor_sensor_count: int
    indoor_sensor_min_lux: float | None
    indoor_sensor_max_lux: float | None
    indoor_sensor_spread_lux: float | None
    window_diagnostics: tuple[WindowEstimate, ...]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _angle_delta_degrees(a: float, b: float) -> float:
    """Return the shortest signed difference between two bearings."""
    return ((a - b + 180.0) % 360.0) - 180.0


def window_orientation_factor(
    *,
    window_azimuth: float,
    sun_azimuth: float,
    sun_elevation: float,
    diffuse_base: float = DEFAULT_DIFFUSE_BASE,
) -> float:
    """Return orientation weighting for a vertical window.

    ``diffuse_base`` preserves skylight from windows that are not facing the
    sun. The remaining contribution models direct geometry against a vertical
    window. Outdoor lux is assumed to already contain cloud/weather effects.
    """
    diffuse_base = _clamp(diffuse_base, 0.0, 1.0)
    if sun_elevation <= 0:
        return diffuse_base

    angle = _angle_delta_degrees(sun_azimuth, window_azimuth)
    facing = max(0.0, math.cos(math.radians(angle)))
    elevation_factor = max(0.0, math.cos(math.radians(sun_elevation)))
    direct_facing = facing * elevation_factor
    return diffuse_base + ((1.0 - diffuse_base) * direct_facing)


def estimate_room_daylight(
    *,
    outside_lux: float,
    sun_azimuth: float,
    sun_elevation: float,
    floor_area: float,
    windows: Iterable[Mapping[str, Any]],
    indoor_lux_values: Iterable[float] = (),
    calibration: float = 1.0,
    daylight_gain: float = DEFAULT_DAYLIGHT_GAIN,
    diffuse_base: float = DEFAULT_DIFFUSE_BASE,
    window_transmission: float = DEFAULT_WINDOW_TRANSMISSION,
    sensor_blend: float = DEFAULT_SENSOR_BLEND,
    sensor_min_ratio: float = DEFAULT_SENSOR_MIN_RATIO,
    sensor_max_ratio: float = DEFAULT_SENSOR_MAX_RATIO,
) -> DaylightEstimate:
    """Estimate usable natural daylight inside a room.

    Each window mapping must contain width, height and azimuth. It may also
    contain ``covered`` and ``transmission``. Covered windows are excluded.

    Indoor lux readings are optional supporting evidence. Their median is
    bounded relative to the physical model and blended conservatively, so a
    local sun patch or badly placed sensor cannot dominate the result.

    The returned object intentionally contains detailed intermediate values so
    Home Assistant can expose transparent diagnostics without reimplementing
    the calculation in the entity layer.
    """
    outside_lux = max(0.0, float(outside_lux))
    floor_area = max(0.1, float(floor_area))
    calibration = max(0.0, float(calibration))
    daylight_gain = max(0.0, float(daylight_gain))
    diffuse_base = _clamp(float(diffuse_base), 0.0, 1.0)
    window_transmission = _clamp(float(window_transmission), 0.0, 1.0)
    sensor_blend = _clamp(float(sensor_blend), 0.0, 1.0)
    sensor_min_ratio = max(0.0, float(sensor_min_ratio))
    sensor_max_ratio = max(sensor_min_ratio, float(sensor_max_ratio))

    total_window_factor = 0.0
    active_windows = 0
    covered_windows = 0
    window_diagnostics: list[WindowEstimate] = []

    for index, window in enumerate(windows, start=1):
        width = max(0.0, float(window.get(CONF_WIDTH, 0.0)))
        height = max(0.0, float(window.get(CONF_HEIGHT, 0.0)))
        azimuth = float(window.get(CONF_AZIMUTH, 0.0))
        transmission = _clamp(
            float(window.get("transmission", window_transmission)), 0.0, 1.0
        )
        covered = bool(window.get("covered", False))
        physical_area = width * height
        effective_area = physical_area * transmission

        orientation = window_orientation_factor(
            window_azimuth=azimuth,
            sun_azimuth=float(sun_azimuth),
            sun_elevation=float(sun_elevation),
            diffuse_base=diffuse_base,
        )

        contribution_lux = 0.0
        if covered:
            covered_windows += 1
        elif width > 0 and height > 0:
            weighted_area = effective_area * orientation
            total_window_factor += weighted_area
            active_windows += 1
            contribution_lux = (
                outside_lux
                * daylight_gain
                * (weighted_area / floor_area)
                * calibration
            )

        window_diagnostics.append(
            WindowEstimate(
                index=index,
                width_m=width,
                height_m=height,
                physical_area_m2=physical_area,
                effective_area_m2=effective_area,
                azimuth=azimuth,
                transmission=transmission,
                orientation_factor=orientation,
                covered=covered,
                contribution_lux=max(0.0, contribution_lux),
            )
        )

    base_lux = (
        outside_lux
        * daylight_gain
        * (total_window_factor / floor_area)
        * calibration
    )
    base_lux = max(0.0, base_lux)

    effective_daylight_ratio_pct = (
        (base_lux / outside_lux) * 100.0 if outside_lux > 0 else 0.0
    )

    valid_indoor = [max(0.0, float(value)) for value in indoor_lux_values]
    indoor_median_lux: float | None = None
    bounded_indoor_lux: float | None = None
    indoor_sensor_min_lux: float | None = None
    indoor_sensor_max_lux: float | None = None
    indoor_sensor_spread_lux: float | None = None
    final_lux = base_lux

    if valid_indoor:
        indoor_sensor_min_lux = min(valid_indoor)
        indoor_sensor_max_lux = max(valid_indoor)
        indoor_sensor_spread_lux = indoor_sensor_max_lux - indoor_sensor_min_lux

    # Do not let indoor sensors manufacture daylight at night or when every
    # window has been excluded. Their purpose is to nudge a valid model.
    if valid_indoor and base_lux > 1.0 and active_windows > 0:
        indoor_median_lux = float(median(valid_indoor))
        lower = base_lux * sensor_min_ratio
        upper = base_lux * sensor_max_ratio
        bounded_indoor_lux = _clamp(indoor_median_lux, lower, upper)
        final_lux = (
            (base_lux * (1.0 - sensor_blend))
            + (bounded_indoor_lux * sensor_blend)
        )

    sensor_adjustment_lux = final_lux - base_lux
    sensor_adjustment_pct = (
        (sensor_adjustment_lux / base_lux) * 100.0 if base_lux > 0 else 0.0
    )

    return DaylightEstimate(
        final_lux=max(0.0, final_lux),
        base_lux=base_lux,
        indoor_median_lux=indoor_median_lux,
        bounded_indoor_lux=bounded_indoor_lux,
        active_windows=active_windows,
        covered_windows=covered_windows,
        total_window_factor=total_window_factor,
        effective_daylight_ratio_pct=effective_daylight_ratio_pct,
        sensor_adjustment_lux=sensor_adjustment_lux,
        sensor_adjustment_pct=sensor_adjustment_pct,
        indoor_sensor_count=len(valid_indoor),
        indoor_sensor_min_lux=indoor_sensor_min_lux,
        indoor_sensor_max_lux=indoor_sensor_max_lux,
        indoor_sensor_spread_lux=indoor_sensor_spread_lux,
        window_diagnostics=tuple(window_diagnostics),
    )
