"""Package contract tests that do not require Home Assistant."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "room_daylight"
MAINTAINED_TRANSLATION_LOCALES = {"en", "de", "es", "fr", "nl"}


def _json(path: Path) -> dict:
    """Load a JSON document from *path*."""

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


def test_manifest_declares_expected_integration_shape() -> None:
    """Protect architectural manifest settings, not release metadata."""

    manifest = _json(INTEGRATION / "manifest.json")

    assert manifest["domain"] == "room_daylight"
    assert manifest["integration_type"] == "service"
    assert manifest["config_flow"] is True
    assert manifest["single_config_entry"] is True
    assert manifest["iot_class"] == "calculated"


def test_custom_integration_uses_direct_translation_files() -> None:
    """Standalone custom integrations should ship translations directly."""

    translations_dir = INTEGRATION / "translations"

    assert (translations_dir / "en.json").is_file()
    assert not (INTEGRATION / "strings.json").exists()


def test_subentry_translations_have_flow_metadata() -> None:
    """Subentry translations include the metadata required by Hassfest."""

    translations = _json(INTEGRATION / "translations" / "en.json")
    subentries = translations.get("config_subentries", {})

    assert subentries
    for name, subentry in subentries.items():
        entry_type = subentry.get("entry_type")
        initiate_flow = subentry.get("initiate_flow", {})

        assert isinstance(entry_type, str) and entry_type.strip(), name
        for flow_type in ("user", "reconfigure"):
            label = initiate_flow.get(flow_type)
            assert isinstance(label, str) and label.strip(), f"{name}.{flow_type}"


def test_no_translation_uses_legacy_config_title() -> None:
    """Reject the obsolete nested config.title translation location."""

    translations_dir = INTEGRATION / "translations"
    for path in sorted(translations_dir.glob("*.json")):
        translation = _json(path)
        assert "title" not in translation.get("config", {}), path.name


def test_maintained_translations_match_english_contract() -> None:
    """Project-maintained locales expose the same keys and placeholders as English."""

    translations_dir = INTEGRATION / "translations"
    english = _json(translations_dir / "en.json")
    english_paths = _leaf_paths(english)
    available_locales = {path.stem for path in translations_dir.glob("*.json")}

    assert MAINTAINED_TRANSLATION_LOCALES <= available_locales

    for locale in sorted(MAINTAINED_TRANSLATION_LOCALES):
        path = translations_dir / f"{locale}.json"
        translation = _json(path)
        assert _leaf_paths(translation) == english_paths, path.name

        for key_path in english_paths:
            value = _string_at(translation, key_path)
            assert value.strip(), f"{path.name}: {'.'.join(key_path)}"
            assert _placeholders(value) == _placeholders(
                _string_at(english, key_path)
            ), f"{path.name}: {'.'.join(key_path)}"


def test_additional_translation_strings_are_well_formed() -> None:
    """Validate any community locale strings without requiring full coverage."""

    translations_dir = INTEGRATION / "translations"
    english = _json(translations_dir / "en.json")
    english_paths = _leaf_paths(english)

    for path in sorted(translations_dir.glob("*.json")):
        if path.stem in MAINTAINED_TRANSLATION_LOCALES:
            continue

        translation = _json(path)
        for key_path in _leaf_paths(translation):
            value = _string_at(translation, key_path)
            assert value.strip(), f"{path.name}: {'.'.join(key_path)}"
            if key_path in english_paths:
                assert _placeholders(value) == _placeholders(
                    _string_at(english, key_path)
                ), f"{path.name}: {'.'.join(key_path)}"


def test_config_entry_runtime_data_uses_a_type_alias() -> None:
    """Keep the config-entry alias usable in type expressions by static analysers."""

    tree = ast.parse((INTEGRATION / "__init__.py").read_text())
    aliases = [
        node
        for node in tree.body
        if isinstance(node, ast.TypeAlias)
        and isinstance(node.name, ast.Name)
        and node.name.id == "RoomDaylightConfigEntry"
    ]

    assert aliases


def test_sensor_translation_keys_have_english_names() -> None:
    """Every sensor description translation key resolves to an English entity name."""

    translations = _json(INTEGRATION / "translations" / "en.json")
    sensor_translations = translations["entity"]["sensor"]
    tree = ast.parse((INTEGRATION / "sensor.py").read_text())

    translation_keys: set[str] = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "RoomDaylightSensorDescription"
        ):
            continue

        for keyword in node.keywords:
            if (
                keyword.arg == "translation_key"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                translation_keys.add(keyword.value.value)

    assert translation_keys
    for translation_key in translation_keys:
        translated = sensor_translations.get(translation_key)
        assert isinstance(translated, dict), translation_key
        name = translated.get("name")
        assert isinstance(name, str) and name.strip(), translation_key


def test_sensor_platform_declares_coordinator_parallelism() -> None:
    """Coordinator-backed read-only sensors should not request parallel updates."""

    tree = ast.parse((INTEGRATION / "sensor.py").read_text())
    values = [
        node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "PARALLEL_UPDATES"
            for target in node.targets
        )
        and isinstance(node.value, ast.Constant)
    ]

    assert values == [0]


def test_config_flows_do_not_trigger_double_reload() -> None:
    """The config-entry update listener owns reloads after flow updates."""

    source = (INTEGRATION / "config_flow.py").read_text()
    assert "async_update_reload_and_abort" not in source
