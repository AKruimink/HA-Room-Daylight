"""Tests for exterior daylight and local sensor correction."""

from dataclasses import replace
from math import cos, radians, sin

import pytest

from custom_components.room_daylight.calculation import (
    apply_sensor_correction,
    direct_incidence_factor,
    estimate_native_daylight,
    sky_view_factor,
)
from custom_components.room_daylight.const import AssumedState
from custom_components.room_daylight.models import ExteriorOpening, RoomDefinition


def _opening(*, tilt: float = 90.0, azimuth: float = 180.0) -> ExteriorOpening:
    return ExteriorOpening(
        opening_id="opening-1",
        name="Test opening",
        opening_type="custom",
        width_m=1.0,
        height_m=1.0,
        azimuth_deg=azimuth,
        tilt_deg=tilt,
        transmission=1.0,
    )


def _room(openings: tuple[ExteriorOpening, ...]) -> RoomDefinition:
    return RoomDefinition(
        room_id="room-1",
        name="Test room",
        floor_area_m2=10.0,
        openings=openings,
        daylight_utilisation=1.0,
        sensor_correction_strength=0.5,
    )


def test_vertical_window_incidence_matches_expected_geometry() -> None:
    """A facade normal facing the sun receives cos(elevation) direct light."""

    incidence = direct_incidence_factor(180.0, 90.0, 180.0, 30.0)
    assert incidence == pytest.approx(cos(radians(30.0)))


def test_horizontal_rooflight_strengthens_as_sun_rises() -> None:
    """A rooflight receives more direct light from a higher sun."""

    low = direct_incidence_factor(0.0, 0.0, 90.0, 10.0)
    high = direct_incidence_factor(0.0, 0.0, 270.0, 70.0)

    assert low == pytest.approx(sin(radians(10.0)))
    assert high == pytest.approx(sin(radians(70.0)))
    assert high > low


def test_opposite_wall_receives_no_direct_component() -> None:
    """Direct incidence is clipped when the sun is behind an opening."""

    assert direct_incidence_factor(0.0, 90.0, 180.0, 30.0) == 0.0


def test_sky_view_distinguishes_rooflight_and_vertical_window() -> None:
    """Horizontal glazing sees twice the isotropic sky of vertical glazing."""

    assert sky_view_factor(0.0) == pytest.approx(1.0)
    assert sky_view_factor(90.0) == pytest.approx(0.5)


def test_room_with_no_exterior_openings_has_zero_native_daylight() -> None:
    result = estimate_native_daylight(
        _room(()),
        outdoor_lux=20_000.0,
        sun_azimuth_deg=180.0,
        sun_elevation_deg=40.0,
        diffuse_fraction=0.35,
    )
    assert result.lux == 0.0
    assert result.openings == ()


def test_closed_cover_blocks_opening() -> None:
    opening = _opening()
    result = estimate_native_daylight(
        _room((opening,)),
        outdoor_lux=20_000.0,
        sun_azimuth_deg=180.0,
        sun_elevation_deg=40.0,
        diffuse_fraction=0.35,
        cover_openness={opening.opening_id: 0.0},
    )
    assert result.lux == 0.0
    assert result.openings[0].effective_transmission == 0.0


def test_native_daylight_is_bounded_by_outdoor_illuminance() -> None:
    opening = ExteriorOpening(
        opening_id="huge",
        name="Huge rooflight",
        opening_type="rooflight",
        width_m=20.0,
        height_m=20.0,
        azimuth_deg=0.0,
        tilt_deg=0.0,
        transmission=1.0,
    )
    result = estimate_native_daylight(
        _room((opening,)),
        outdoor_lux=1_000.0,
        sun_azimuth_deg=180.0,
        sun_elevation_deg=90.0,
        diffuse_fraction=0.0,
    )
    assert result.lux == pytest.approx(1_000.0)
    assert sum(item.contribution_lux for item in result.openings) == pytest.approx(
        result.lux
    )


def test_sensor_correction_uses_median_and_stays_local() -> None:
    result = apply_sensor_correction(
        100.0,
        outdoor_lux=1_000.0,
        sensor_values=[200.0, 220.0, 10_000.0],
        correction_strength=0.5,
        artificial_lights_active=False,
    )
    assert result.sensor_median_lux == 220.0
    assert result.estimated_lux == pytest.approx(160.0)
    assert result.adjustment_lux == pytest.approx(60.0)
    assert result.correction_applied is True


def test_artificial_light_suppresses_sensor_correction() -> None:
    result = apply_sensor_correction(
        100.0,
        outdoor_lux=1_000.0,
        sensor_values=[800.0],
        correction_strength=1.0,
        artificial_lights_active=True,
    )
    assert result.sensor_median_lux == 800.0
    assert result.estimated_lux == 100.0
    assert result.adjustment_lux == 0.0
    assert result.correction_applied is False


def test_direct_component_is_zero_below_horizon() -> None:
    """Direct daylight is unavailable when the sun is below the horizon."""

    assert direct_incidence_factor(180.0, 90.0, 180.0, -5.0) == 0.0


def test_sensor_correction_ignores_invalid_samples() -> None:
    """Unavailable and non-finite physical readings cannot skew correction."""

    result = apply_sensor_correction(
        100.0,
        outdoor_lux=1_000.0,
        sensor_values=[None, -1.0, float("nan"), float("inf"), 250.0],
        correction_strength=1.0,
        artificial_lights_active=False,
    )

    assert result.sensor_median_lux == 250.0
    assert result.estimated_lux == 250.0


def test_no_valid_sensor_values_leave_model_unchanged() -> None:
    """Sensor correction is a no-op when no usable local reading exists."""

    result = apply_sensor_correction(
        125.0,
        outdoor_lux=1_000.0,
        sensor_values=[None, -10.0, float("nan")],
        correction_strength=1.0,
        artificial_lights_active=False,
    )

    assert result.sensor_median_lux is None
    assert result.estimated_lux == 125.0
    assert result.correction_applied is False


def test_assumed_closed_blind_blocks_opening_without_runtime_state() -> None:
    """The pure calculation honours an opening's configured fallback."""

    opening = replace(
        _opening(),
        assumed_state=AssumedState.CLOSED,
    )
    result = estimate_native_daylight(
        _room((opening,)),
        outdoor_lux=20_000.0,
        sun_azimuth_deg=180.0,
        sun_elevation_deg=40.0,
        diffuse_fraction=0.35,
    )

    assert result.lux == 0.0
    assert result.openings[0].cover_openness == 0.0
