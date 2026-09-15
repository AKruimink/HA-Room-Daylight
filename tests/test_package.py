"""Release-package contract tests that do not require Home Assistant."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "room_daylight"


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def test_manifest_declares_clean_single_entry_release() -> None:
    manifest = _json(INTEGRATION / "manifest.json")

    assert manifest["domain"] == "room_daylight"
    assert manifest["version"] == "1.0.0"
    assert manifest["config_flow"] is True
    assert manifest["single_config_entry"] is True
    assert manifest["iot_class"] == "calculated"
    assert manifest["requirements"] == []


def test_hacs_metadata_matches_supported_home_assistant_version() -> None:
    hacs = _json(ROOT / "hacs.json")

    assert hacs["name"] == "Room Daylight"
    assert hacs["homeassistant"] == "2026.8.0"
    assert hacs["render_readme"] is True


def test_custom_integration_uses_direct_translation_file() -> None:
    translations = _json(INTEGRATION / "translations" / "en.json")

    assert not (INTEGRATION / "strings.json").exists()
    assert {"room", "connection"} <= set(translations["config_subentries"])
    assert {"opening_type", "connection_type"} <= set(translations["selector"])


def test_every_room_sensor_has_an_english_entity_translation() -> None:
    translations = _json(INTEGRATION / "translations" / "en.json")
    sensor_names = translations["entity"]["sensor"]

    assert set(sensor_names) == {
        "estimated_daylight",
        "native_daylight",
        "transferred_daylight",
        "indoor_sensor_median",
        "indoor_sensor_adjustment",
        "effective_daylight_ratio",
    }
    assert all(item["name"].strip() for item in sensor_names.values())


def test_sensor_platform_declares_coordinator_parallelism_and_translations() -> None:
    """Sensor metadata follows Home Assistant's coordinator/entity conventions."""

    tree = ast.parse((INTEGRATION / "sensor.py").read_text())
    parallel_updates = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "PARALLEL_UPDATES"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
    ]
    assert parallel_updates == [0]

    descriptions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "RoomDaylightSensorDescription"
    ]
    assert len(descriptions) == 6
    for call in descriptions:
        keywords = {keyword.arg for keyword in call.keywords}
        assert "translation_key" in keywords
        assert "name" not in keywords


def test_config_flows_leave_reload_ownership_to_update_listener() -> None:
    """Flows update data only; the config-entry listener owns reloads."""

    source = (INTEGRATION / "config_flow.py").read_text()
    assert "async_update_and_abort" in source
    assert "async_update_reload_and_abort" not in source
