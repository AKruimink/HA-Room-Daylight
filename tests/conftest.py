"""Test bootstrap for the Home Assistant-independent Room Daylight core."""

import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COMPONENTS = ROOT / "custom_components"
PACKAGE = CUSTOM_COMPONENTS / "room_daylight"

# Import pure modules without executing custom_components.room_daylight.__init__,
# which legitimately depends on Home Assistant and is not installed in this
# lightweight unit-test environment.
custom_components = ModuleType("custom_components")
custom_components.__path__ = [str(CUSTOM_COMPONENTS)]
sys.modules.setdefault("custom_components", custom_components)

room_daylight = ModuleType("custom_components.room_daylight")
room_daylight.__path__ = [str(PACKAGE)]
sys.modules.setdefault("custom_components.room_daylight", room_daylight)
