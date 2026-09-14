"""Unit tests for the pure Room Daylight model."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "custom_components" / "room_daylight"

# Load the pure model without importing the Home Assistant integration package.
# This keeps these tests fast and independent of a Home Assistant installation.
package = types.ModuleType("room_daylight_testpkg")
package.__path__ = [str(PACKAGE_DIR)]
sys.modules["room_daylight_testpkg"] = package

for module_name in ("const", "calculation"):
    spec = importlib.util.spec_from_file_location(
        f"room_daylight_testpkg.{module_name}",
        PACKAGE_DIR / f"{module_name}.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

calculation = sys.modules["room_daylight_testpkg.calculation"]

DEFAULT_WINDOW = {"width": 2.0, "height": 1.2, "azimuth": 180}
LIVING_ROOM_WINDOWS = [
    {"width": 1.77, "height": 1.98, "azimuth": 180},
    {"width": 1.30, "height": 1.38, "azimuth": 270},
]


class DaylightCalculationTests(unittest.TestCase):
    """Tests for room daylight calculations and diagnostics."""

    def estimate(self, **overrides):
        """Return an estimate with sensible test defaults."""
        values = {
            "outside_lux": 10_000,
            "sun_azimuth": 180,
            "sun_elevation": 20,
            "floor_area": 20,
            "windows": [DEFAULT_WINDOW],
        }
        values.update(overrides)
        return calculation.estimate_room_daylight(**values)

    def test_south_window_gets_more_when_sun_is_south(self):
        facing = self.estimate(sun_azimuth=180)
        behind = self.estimate(sun_azimuth=0)

        self.assertGreater(facing.final_lux, behind.final_lux)

    def test_covered_window_contributes_nothing(self):
        estimate = self.estimate(windows=[{**DEFAULT_WINDOW, "covered": True}])

        self.assertEqual(estimate.final_lux, 0)
        self.assertEqual(estimate.covered_windows, 1)
        self.assertEqual(estimate.window_diagnostics[0].contribution_lux, 0)

    def test_indoor_sensor_only_nudges_model(self):
        base = self.estimate()
        fused = self.estimate(indoor_lux_values=[100_000])

        self.assertGreater(fused.final_lux, base.final_lux)
        self.assertLessEqual(fused.final_lux, base.final_lux * 1.25 + 0.001)
        self.assertGreater(fused.sensor_adjustment_lux, 0)

    def test_multiple_sensor_median_resists_outlier(self):
        estimate = self.estimate(indoor_lux_values=[100, 110, 5_000])

        self.assertEqual(estimate.indoor_median_lux, 110)
        self.assertEqual(estimate.indoor_sensor_min_lux, 100)
        self.assertEqual(estimate.indoor_sensor_max_lux, 5_000)
        self.assertEqual(estimate.indoor_sensor_spread_lux, 4_900)
        self.assertEqual(estimate.indoor_sensor_count, 3)

    def test_effective_daylight_ratio_matches_base_to_outdoor_ratio(self):
        estimate = self.estimate(outside_lux=12_500, sun_elevation=30)
        expected = (estimate.base_lux / 12_500) * 100

        self.assertAlmostEqual(estimate.effective_daylight_ratio_pct, expected)

    def test_window_contributions_add_up_to_base_estimate(self):
        estimate = self.estimate(
            outside_lux=13_000,
            sun_azimuth=150,
            sun_elevation=38,
            floor_area=20.2,
            windows=LIVING_ROOM_WINDOWS,
        )
        contribution_total = sum(
            window.contribution_lux for window in estimate.window_diagnostics
        )

        self.assertAlmostEqual(contribution_total, estimate.base_lux)
        self.assertEqual(len(estimate.window_diagnostics), 2)
        self.assertTrue(
            all(window.contribution_lux > 0 for window in estimate.window_diagnostics)
        )

    def test_negative_sensor_adjustment_is_reported(self):
        common = {
            "outside_lux": 13_000,
            "sun_azimuth": 150,
            "sun_elevation": 38,
            "floor_area": 20.2,
            "windows": LIVING_ROOM_WINDOWS,
        }
        base = self.estimate(**common)
        fused = self.estimate(**common, indoor_lux_values=[150, 160, 170])

        self.assertEqual(fused.indoor_median_lux, 160)
        self.assertLess(fused.sensor_adjustment_lux, 0)
        self.assertLess(fused.sensor_adjustment_pct, 0)
        self.assertLess(fused.final_lux, base.final_lux)

    def test_sensor_blend_can_be_disabled(self):
        base = self.estimate()
        fused = self.estimate(
            indoor_lux_values=[100_000],
            sensor_blend=0.0,
        )

        self.assertAlmostEqual(fused.final_lux, base.final_lux)
        self.assertAlmostEqual(fused.sensor_adjustment_lux, 0.0)

    def test_window_transmission_changes_window_contribution(self):
        normal = self.estimate(
            windows=[{**DEFAULT_WINDOW, "transmission": 0.65}]
        )
        low_transmission = self.estimate(
            windows=[{**DEFAULT_WINDOW, "transmission": 0.20}]
        )

        self.assertGreater(normal.base_lux, low_transmission.base_lux)
        self.assertAlmostEqual(
            low_transmission.window_diagnostics[0].transmission,
            0.20,
        )

    def test_advanced_model_parameters_change_result(self):
        default = self.estimate()
        calibrated = self.estimate(
            calibration=1.20,
            daylight_gain=0.20,
            diffuse_base=0.50,
        )

        self.assertGreater(calibrated.base_lux, default.base_lux)


if __name__ == "__main__":
    unittest.main()
