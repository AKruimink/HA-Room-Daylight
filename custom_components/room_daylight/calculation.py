"""Daylight calculations for Room Daylight.

The model is deliberately heuristic: it is intended to produce stable,
explainable values for Home Assistant automations, not to replace an
architectural daylight simulation package.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from statistics import median

from .const import AssumedState
from .models import (
    ExteriorOpening,
    NativeDaylightResult,
    OpeningDiagnostic,
    RoomDefinition,
    SensorCorrectionResult,
)


def clamp(value: float, lower: float, upper: float) -> float:
    """Clamp ``value`` to an inclusive interval."""

    return max(lower, min(upper, value))


def _unit_sun_vector(
    azimuth_deg: float,
    elevation_deg: float,
) -> tuple[float, float, float]:
    """Return a sun-direction unit vector in an ENU-style coordinate system.

    Home Assistant reports azimuth clockwise from north: 0° north, 90° east.
    The tuple axes are east, north and up respectively.
    """

    azimuth = math.radians(azimuth_deg)
    elevation = math.radians(elevation_deg)
    horizontal = math.cos(elevation)
    return (
        horizontal * math.sin(azimuth),
        horizontal * math.cos(azimuth),
        math.sin(elevation),
    )


def _opening_normal(azimuth_deg: float, tilt_deg: float) -> tuple[float, float, float]:
    """Return the outward-facing normal of a glazed opening.

    Tilt is measured from horizontal: 0° faces the sky, 90° is vertical.
    """

    azimuth = math.radians(azimuth_deg)
    tilt = math.radians(tilt_deg)
    return (
        math.sin(tilt) * math.sin(azimuth),
        math.sin(tilt) * math.cos(azimuth),
        math.cos(tilt),
    )


def direct_incidence_factor(
    opening_azimuth_deg: float,
    opening_tilt_deg: float,
    sun_azimuth_deg: float,
    sun_elevation_deg: float,
) -> float:
    """Return direct solar incidence on the opening plane in the range 0..1."""

    if sun_elevation_deg <= 0.0:
        return 0.0

    sun = _unit_sun_vector(sun_azimuth_deg, sun_elevation_deg)
    normal = _opening_normal(opening_azimuth_deg, opening_tilt_deg)
    dot = sum(a * b for a, b in zip(sun, normal, strict=True))
    return clamp(dot, 0.0, 1.0)


def sky_view_factor(tilt_deg: float) -> float:
    """Return an isotropic-sky view factor for an upward-facing plane.

    A horizontal rooflight sees essentially the full sky dome (1.0), while a
    vertical facade opening sees approximately half of it (0.5).
    """

    tilt = math.radians(clamp(tilt_deg, 0.0, 180.0))
    return clamp((1.0 + math.cos(tilt)) / 2.0, 0.0, 1.0)


def orientation_factor(
    opening: ExteriorOpening,
    *,
    sun_azimuth_deg: float,
    sun_elevation_deg: float,
    diffuse_fraction: float,
) -> tuple[float, float, float]:
    """Return blended orientation, direct-incidence and sky-view factors."""

    diffuse = clamp(diffuse_fraction, 0.0, 1.0)
    direct = direct_incidence_factor(
        opening.azimuth_deg,
        opening.tilt_deg,
        sun_azimuth_deg,
        sun_elevation_deg,
    )
    sky = sky_view_factor(opening.tilt_deg)
    blended = ((1.0 - diffuse) * direct) + (diffuse * sky)
    return clamp(blended, 0.0, 1.0), direct, sky


def estimate_native_daylight(
    room: RoomDefinition,
    *,
    outdoor_lux: float,
    sun_azimuth_deg: float,
    sun_elevation_deg: float,
    diffuse_fraction: float,
    cover_openness: Mapping[str, float] | None = None,
    cover_state_descriptions: Mapping[str, str] | None = None,
    cover_state_sources: Mapping[str, str] | None = None,
) -> NativeDaylightResult:
    """Estimate daylight admitted directly from outside into ``room``.

    Opening contributions scale with glazed area relative to floor area,
    glazing/cover transmission, three-dimensional orientation and a room-level
    utilisation factor.  The result is capped at outdoor illuminance to keep
    the automation-oriented heuristic bounded and predictable.
    """

    outdoor = max(0.0, float(outdoor_lux))
    if outdoor <= 0.0 or room.floor_area_m2 <= 0.0 or not room.openings:
        return NativeDaylightResult(lux=0.0)

    openness = cover_openness or {}
    state_descriptions = cover_state_descriptions or {}
    state_sources = cover_state_sources or {}
    diagnostics: list[OpeningDiagnostic] = []
    raw_total = 0.0

    for opening in room.openings:
        assumed_openness = (
            1.0 if opening.assumed_state is AssumedState.OPEN else 0.0
        )
        opening_openness = clamp(
            float(openness.get(opening.opening_id, assumed_openness)),
            0.0,
            1.0,
        )
        effective_transmission = (
            clamp(opening.transmission, 0.0, 1.0) * opening_openness
        )
        orient, incidence, sky = orientation_factor(
            opening,
            sun_azimuth_deg=sun_azimuth_deg,
            sun_elevation_deg=sun_elevation_deg,
            diffuse_fraction=diffuse_fraction,
        )
        contribution = (
            outdoor
            * (opening.area_m2 / room.floor_area_m2)
            * effective_transmission
            * orient
            * clamp(room.daylight_utilisation, 0.0, 1.0)
        )
        contribution = max(0.0, contribution)
        raw_total += contribution
        diagnostics.append(
            OpeningDiagnostic(
                opening_id=opening.opening_id,
                name=opening.name,
                area_m2=opening.area_m2,
                incidence_factor=incidence,
                sky_view_factor=sky,
                orientation_factor=orient,
                cover_openness=opening_openness,
                effective_transmission=effective_transmission,
                contribution_lux=contribution,
                cover_entity=opening.cover_entity,
                assumed_state=opening.assumed_state.value,
                state_description=state_descriptions.get(opening.opening_id),
                state_source=state_sources.get(opening.opening_id),
            )
        )

    # If the cap is active, scale diagnostics so their contributions still add
    # up to the reported room-native lux.
    native = min(outdoor, raw_total)
    if raw_total > 0.0 and native < raw_total:
        scale = native / raw_total
        diagnostics = [
            OpeningDiagnostic(
                opening_id=item.opening_id,
                name=item.name,
                area_m2=item.area_m2,
                incidence_factor=item.incidence_factor,
                sky_view_factor=item.sky_view_factor,
                orientation_factor=item.orientation_factor,
                cover_openness=item.cover_openness,
                effective_transmission=item.effective_transmission,
                contribution_lux=item.contribution_lux * scale,
                cover_entity=item.cover_entity,
                assumed_state=item.assumed_state,
                state_description=item.state_description,
                state_source=item.state_source,
            )
            for item in diagnostics
        ]

    return NativeDaylightResult(lux=native, openings=tuple(diagnostics))


def valid_lux_values(values: Iterable[float | None]) -> tuple[float, ...]:
    """Return finite, non-negative illuminance samples."""

    valid: list[float] = []
    for value in values:
        if value is None:
            continue
        sample = float(value)
        if math.isfinite(sample) and sample >= 0.0:
            valid.append(sample)
    return tuple(valid)


def apply_sensor_correction(
    modelled_lux: float,
    *,
    outdoor_lux: float,
    sensor_values: Iterable[float | None],
    correction_strength: float,
    artificial_lights_active: bool,
) -> SensorCorrectionResult:
    """Blend local physical lux sensors into the modelled room value.

    The median is robust to a single sensor sitting in a sun patch.  Correction
    is suppressed while configured artificial lights are on, preventing those
    lights from contaminating the natural-daylight network.  Sensor correction
    happens after network transfer and therefore remains local to this room.
    """

    modelled = max(0.0, float(modelled_lux))
    samples = valid_lux_values(sensor_values)
    sensor_median = float(median(samples)) if samples else None

    if sensor_median is None or artificial_lights_active:
        return SensorCorrectionResult(
            estimated_lux=modelled,
            sensor_median_lux=sensor_median,
            adjustment_lux=0.0,
            correction_applied=False,
        )

    strength = clamp(float(correction_strength), 0.0, 1.0)
    blended = modelled + (sensor_median - modelled) * strength

    # Indoor daylight should not exceed the measured outdoor environment in
    # this bounded heuristic.  ``modelled`` is included defensively in case a
    # caller supplies an already bounded value slightly above outdoor lux.
    upper_bound = max(modelled, max(0.0, float(outdoor_lux)))
    estimated = clamp(blended, 0.0, upper_bound)
    return SensorCorrectionResult(
        estimated_lux=estimated,
        sensor_median_lux=sensor_median,
        adjustment_lux=estimated - modelled,
        correction_applied=True,
    )
