"""Unit tests for the pure Room Daylight model."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "room_daylight"

# Load the pure calculation module without importing Home Assistant's package
# loader via custom_components.room_daylight.__init__.
package = types.ModuleType("room_daylight_testpkg")
package.__path__ = [str(PKG)]
sys.modules["room_daylight_testpkg"] = package

for name in ("const", "calculation"):
    spec = importlib.util.spec_from_file_location(
        f"room_daylight_testpkg.{name}", PKG / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

calc = sys.modules["room_daylight_testpkg.calculation"]


class DaylightCalculationTests(unittest.TestCase):
    def test_south_window_gets_more_when_sun_is_south(self):
        common = dict(
            outside_lux=10000,
            sun_elevation=20,
            floor_area=20,
            windows=[{"width": 2.0, "height": 1.2, "azimuth": 180}],
        )
        facing = calc.estimate_room_daylight(sun_azimuth=180, **common)
        behind = calc.estimate_room_daylight(sun_azimuth=0, **common)
        self.assertGreater(facing.final_lux, behind.final_lux)

    def test_covered_window_contributes_nothing(self):
        estimate = calc.estimate_room_daylight(
            outside_lux=20000,
            sun_azimuth=180,
            sun_elevation=20,
            floor_area=20,
            windows=[
                {
                    "width": 2.0,
                    "height": 1.2,
                    "azimuth": 180,
                    "covered": True,
                }
            ],
        )
        self.assertEqual(estimate.final_lux, 0)
        self.assertEqual(estimate.covered_windows, 1)
        self.assertEqual(estimate.window_diagnostics[0].contribution_lux, 0)

    def test_indoor_sensor_only_nudges_model(self):
        base = calc.estimate_room_daylight(
            outside_lux=10000,
            sun_azimuth=180,
            sun_elevation=20,
            floor_area=20,
            windows=[{"width": 2.0, "height": 1.2, "azimuth": 180}],
        )
        fused = calc.estimate_room_daylight(
            outside_lux=10000,
            sun_azimuth=180,
            sun_elevation=20,
            floor_area=20,
            windows=[{"width": 2.0, "height": 1.2, "azimuth": 180}],
            indoor_lux_values=[100000],
        )
        self.assertGreater(fused.final_lux, base.final_lux)
        self.assertLessEqual(fused.final_lux, base.final_lux * 1.25 + 0.001)
        self.assertGreater(fused.sensor_adjustment_lux, 0)

    def test_multiple_sensor_median_resists_outlier(self):
        estimate = calc.estimate_room_daylight(
            outside_lux=10000,
            sun_azimuth=180,
            sun_elevation=20,
            floor_area=20,
            windows=[{"width": 2.0, "height": 1.2, "azimuth": 180}],
            indoor_lux_values=[100, 110, 5000],
        )
        self.assertEqual(estimate.indoor_median_lux, 110)
        self.assertEqual(estimate.indoor_sensor_min_lux, 100)
        self.assertEqual(estimate.indoor_sensor_max_lux, 5000)
        self.assertEqual(estimate.indoor_sensor_spread_lux, 4900)
        self.assertEqual(estimate.indoor_sensor_count, 3)

    def test_effective_daylight_ratio_matches_base_to_outdoor_ratio(self):
        estimate = calc.estimate_room_daylight(
            outside_lux=12500,
            sun_azimuth=180,
            sun_elevation=30,
            floor_area=20,
            windows=[{"width": 2.0, "height": 1.2, "azimuth": 180}],
        )
        expected = (estimate.base_lux / 12500) * 100
        self.assertAlmostEqual(estimate.effective_daylight_ratio_pct, expected)

    def test_window_contributions_add_up_to_base_estimate(self):
        estimate = calc.estimate_room_daylight(
            outside_lux=13000,
            sun_azimuth=150,
            sun_elevation=38,
            floor_area=20.2,
            windows=[
                {"width": 1.77, "height": 1.98, "azimuth": 180},
                {"width": 1.30, "height": 1.38, "azimuth": 270},
            ],
        )
        total = sum(item.contribution_lux for item in estimate.window_diagnostics)
        self.assertAlmostEqual(total, estimate.base_lux)
        self.assertEqual(len(estimate.window_diagnostics), 2)
        self.assertGreater(estimate.window_diagnostics[0].contribution_lux, 0)
        self.assertGreater(estimate.window_diagnostics[1].contribution_lux, 0)

    def test_negative_sensor_adjustment_is_reported(self):
        base = calc.estimate_room_daylight(
            outside_lux=13000,
            sun_azimuth=150,
            sun_elevation=38,
            floor_area=20.2,
            windows=[
                {"width": 1.77, "height": 1.98, "azimuth": 180},
                {"width": 1.30, "height": 1.38, "azimuth": 270},
            ],
        )
        fused = calc.estimate_room_daylight(
            outside_lux=13000,
            sun_azimuth=150,
            sun_elevation=38,
            floor_area=20.2,
            windows=[
                {"width": 1.77, "height": 1.98, "azimuth": 180},
                {"width": 1.30, "height": 1.38, "azimuth": 270},
            ],
            indoor_lux_values=[150, 160, 170],
        )
        self.assertEqual(fused.indoor_median_lux, 160)
        self.assertLess(fused.sensor_adjustment_lux, 0)
        self.assertLess(fused.sensor_adjustment_pct, 0)
        self.assertLess(fused.final_lux, base.final_lux)


if __name__ == "__main__":
    unittest.main()
