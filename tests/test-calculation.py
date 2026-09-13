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


if __name__ == "__main__":
    unittest.main()
