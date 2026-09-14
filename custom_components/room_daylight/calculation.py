"""Pure daylight calculations for Room Daylight.

This module intentionally has no Home Assistant dependencies. Keeping the model
pure makes it easy to reason about, test, and reuse as the integration grows.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math
from statistics import median
from typing import Any

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
    """Calculated contribution and diagnostics for one exterior opening."""

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
    """Final daylight estimate together with useful intermediate values."""

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


@dataclass(slots=True, frozen=True)
class _IndoorSensorSummary:
    """Internal result of blending indoor readings into the base model."""

    final_lux: float
    median_lux: float | None
    bounded_lux: float | None
    count: int
    minimum_lux: float | None
    maximum_lux: float | None
    spread_lux: float | None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a number between inclusive bounds."""
    return max(minimum, min(maximum, value))


def _angle_delta_degrees(a: float, b: float) -> float:
    """Return the shortest signed difference between two bearings."""
    return ((a - b + 180.0) % 360.0) - 180.0


def _lux_from_window_factor(
    *,
    outside_lux: float,
    window_factor: float,
    floor_area: float,
    daylight_gain: float,
    calibration: float,
) -> float:
    """Convert an effective window factor into estimated indoor lux."""
    return max(
        0.0,
        outside_lux
        * daylight_gain
        * (window_factor / floor_area)
        * calibration,
    )


def window_orientation_factor(
    *,
    window_azimuth: float,
    sun_azimuth: float,
    sun_elevation: float,
    diffuse_base: float = DEFAULT_DIFFUSE_BASE,
) -> float:
    """Return the orientation weighting for a vertical window.

    ``diffuse_base`` represents daylight that can enter even when a window is
    not facing the sun. The remaining contribution is based on the relative
    sun/window angle. Outdoor illuminance is expected to already reflect cloud
    and weather conditions.
    """
    diffuse_base = _clamp(diffuse_base, 0.0, 1.0)
    if sun_elevation <= 0:
        return diffuse_base

    angle = _angle_delta_degrees(sun_azimuth, window_azimuth)
    facing = max(0.0, math.cos(math.radians(angle)))
    elevation_factor = max(0.0, math.cos(math.radians(sun_elevation)))
    direct_facing = facing * elevation_factor

    return diffuse_base + ((1.0 - diffuse_base) * direct_facing)


def _estimate_window(
    *,
    index: int,
    window: Mapping[str, Any],
    outside_lux: float,
    sun_azimuth: float,
    sun_elevation: float,
    floor_area: float,
    calibration: float,
    daylight_gain: float,
    diffuse_base: float,
    default_transmission: float,
) -> tuple[WindowEstimate, float, bool]:
    """Calculate one window and return its weighted factor and active state."""
    width = max(0.0, float(window.get(CONF_WIDTH, 0.0)))
    height = max(0.0, float(window.get(CONF_HEIGHT, 0.0)))
    azimuth = float(window.get(CONF_AZIMUTH, 0.0))
    covered = bool(window.get("covered", False))
    transmission = _clamp(
        float(window.get("transmission", default_transmission)),
        0.0,
        1.0,
    )

    physical_area = width * height
    effective_area = physical_area * transmission
    orientation_factor = window_orientation_factor(
        window_azimuth=azimuth,
        sun_azimuth=sun_azimuth,
        sun_elevation=sun_elevation,
        diffuse_base=diffuse_base,
    )

    active = not covered and width > 0 and height > 0
    window_factor = effective_area * orientation_factor if active else 0.0
    contribution_lux = _lux_from_window_factor(
        outside_lux=outside_lux,
        window_factor=window_factor,
        floor_area=floor_area,
        daylight_gain=daylight_gain,
        calibration=calibration,
    )

    estimate = WindowEstimate(
        index=index,
        width_m=width,
        height_m=height,
        physical_area_m2=physical_area,
        effective_area_m2=effective_area,
        azimuth=azimuth,
        transmission=transmission,
        orientation_factor=orientation_factor,
        covered=covered,
        contribution_lux=contribution_lux,
    )
    return estimate, window_factor, active


def _blend_indoor_sensors(
    *,
    base_lux: float,
    active_windows: int,
    indoor_lux_values: Iterable[float],
    sensor_blend: float,
    sensor_min_ratio: float,
    sensor_max_ratio: float,
) -> _IndoorSensorSummary:
    """Blend optional indoor lux readings into a valid physical estimate."""
    values = [max(0.0, float(value)) for value in indoor_lux_values]
    if not values:
        return _IndoorSensorSummary(base_lux, None, None, 0, None, None, None)

    minimum_lux = min(values)
    maximum_lux = max(values)
    spread_lux = maximum_lux - minimum_lux

    # Indoor sensors are only supporting evidence. They must not create
    # daylight when the physical model has no meaningful daylight source.
    if base_lux <= 1.0 or active_windows <= 0:
        return _IndoorSensorSummary(
            base_lux,
            None,
            None,
            len(values),
            minimum_lux,
            maximum_lux,
            spread_lux,
        )

    median_lux = float(median(values))
    bounded_lux = _clamp(
        median_lux,
        base_lux * sensor_min_ratio,
        base_lux * sensor_max_ratio,
    )
    final_lux = (base_lux * (1.0 - sensor_blend)) + (bounded_lux * sensor_blend)

    return _IndoorSensorSummary(
        final_lux,
        median_lux,
        bounded_lux,
        len(values),
        minimum_lux,
        maximum_lux,
        spread_lux,
    )


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

    Windows provide the base physical estimate. Optional indoor lux readings
    then apply a bounded correction so individual sensors can improve the model
    without becoming the source of truth.
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

    window_estimates: list[WindowEstimate] = []
    total_window_factor = 0.0
    active_windows = 0
    covered_windows = 0

    for index, window in enumerate(windows, start=1):
        estimate, window_factor, active = _estimate_window(
            index=index,
            window=window,
            outside_lux=outside_lux,
            sun_azimuth=float(sun_azimuth),
            sun_elevation=float(sun_elevation),
            floor_area=floor_area,
            calibration=calibration,
            daylight_gain=daylight_gain,
            diffuse_base=diffuse_base,
            default_transmission=window_transmission,
        )
        window_estimates.append(estimate)
        total_window_factor += window_factor
        active_windows += int(active)
        covered_windows += int(estimate.covered)

    base_lux = _lux_from_window_factor(
        outside_lux=outside_lux,
        window_factor=total_window_factor,
        floor_area=floor_area,
        daylight_gain=daylight_gain,
        calibration=calibration,
    )
    daylight_ratio = (base_lux / outside_lux) * 100.0 if outside_lux > 0 else 0.0

    indoor = _blend_indoor_sensors(
        base_lux=base_lux,
        active_windows=active_windows,
        indoor_lux_values=indoor_lux_values,
        sensor_blend=sensor_blend,
        sensor_min_ratio=sensor_min_ratio,
        sensor_max_ratio=sensor_max_ratio,
    )
    sensor_adjustment_lux = indoor.final_lux - base_lux
    sensor_adjustment_pct = (
        (sensor_adjustment_lux / base_lux) * 100.0 if base_lux > 0 else 0.0
    )

    return DaylightEstimate(
        final_lux=max(0.0, indoor.final_lux),
        base_lux=base_lux,
        indoor_median_lux=indoor.median_lux,
        bounded_indoor_lux=indoor.bounded_lux,
        active_windows=active_windows,
        covered_windows=covered_windows,
        total_window_factor=total_window_factor,
        effective_daylight_ratio_pct=daylight_ratio,
        sensor_adjustment_lux=sensor_adjustment_lux,
        sensor_adjustment_pct=sensor_adjustment_pct,
        indoor_sensor_count=indoor.count,
        indoor_sensor_min_lux=indoor.minimum_lux,
        indoor_sensor_max_lux=indoor.maximum_lux,
        indoor_sensor_spread_lux=indoor.spread_lux,
        window_diagnostics=tuple(window_estimates),
    )
