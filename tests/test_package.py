"""Release-package contract tests that do not require Home Assistant."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "room_daylight"
COMPLETE_TRANSLATION_LOCALES = {"en", "de", "es", "fr", "nl"}


def _json(path: Path) -> dict:
    return json.loads(path.read_text())


def _leaf_paths(value: object, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    """Return paths to translated leaf strings."""

    if isinstance(value, dict):
        paths: set[tuple[str, ...]] = set()
        for key, child in value.items():
            paths.update(_leaf_paths(child, (*prefix, key)))
        return paths
    return {prefix}


def _string_at(value: dict, path: tuple[str, ...]) -> str:
    """Return the string value at a translation path."""

    current: object = value
    for key in path:
        assert isinstance(current, dict)
        current = current[key]
    assert isinstance(current, str)
    return current


def _placeholders(value: str) -> set[str]:
    """Return format placeholders used by a translation string."""

    return set(re.findall(r"\{([A-Za-z0-9_]+)\}", value))


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


def test_subentry_translations_have_required_entry_types() -> None:
    translations = _json(INTEGRATION / "translations" / "en.json")

    assert translations["config_subentries"]["room"]["entry_type"] == "Room"
    assert (
        translations["config_subentries"]["connection"]["entry_type"]
        == "Room connection"
    )


def test_supported_translations_match_english_schema_and_placeholders() -> None:
    """Locales maintained by this project expose the complete translation contract."""

    translations_dir = INTEGRATION / "translations"
    english = _json(translations_dir / "en.json")
    english_paths = _leaf_paths(english)

    assert COMPLETE_TRANSLATION_LOCALES <= {
        path.stem for path in translations_dir.glob("*.json")
    }

    for locale in sorted(COMPLETE_TRANSLATION_LOCALES):
        path = translations_dir / f"{locale}.json"
        translation = _json(path)
        assert "title" not in translation.get("config", {}), path.name
        assert _leaf_paths(translation) == english_paths, path.name
        for key_path in english_paths:
            value = _string_at(translation, key_path)
            assert value.strip(), f"{path.name}: {'.'.join(key_path)}"
            assert _placeholders(value) == _placeholders(
                _string_at(english, key_path)
            ), f"{path.name}: {'.'.join(key_path)}"


def test_additional_translation_files_remain_hassfest_compatible() -> None:
    """Allow community locales to be partial while validating the strings they ship.

    Home Assistant loads English first and uses it as the fallback for missing keys in
    another locale. Requiring every community translation to be complete made the
    package tests stricter than Home Assistant and caused otherwise valid partial
    translations to fail CI.
    """

    translations_dir = INTEGRATION / "translations"
    english = _json(translations_dir / "en.json")
    english_paths = _leaf_paths(english)

    for path in sorted(translations_dir.glob("*.json")):
        if path.stem in COMPLETE_TRANSLATION_LOCALES:
            continue

        translation = _json(path)
        for key_path in _leaf_paths(translation):
            value = _string_at(translation, key_path)
            assert value.strip(), f"{path.name}: {'.'.join(key_path)}"
            if key_path in english_paths:
                assert _placeholders(value) == _placeholders(
                    _string_at(english, key_path)
                ), f"{path.name}: {'.'.join(key_path)}"

        for subentry in translation.get("config_subentries", {}).values():
            assert "entry_type" in subentry, path.name


def test_config_entry_runtime_data_alias_is_an_explicit_type_alias() -> None:
    source = (INTEGRATION / "__init__.py").read_text()
    assert (
        "type RoomDaylightConfigEntry = "
        "ConfigEntry[RoomDaylightCoordinator]"
    ) in source


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
