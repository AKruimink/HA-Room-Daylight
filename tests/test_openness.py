"""Tests for state-entity and assumed-state openness resolution."""

import pytest

from custom_components.room_daylight.const import AssumedState
from custom_components.room_daylight.openness import (
    assumed_openness,
    resolve_binary_openness,
    resolve_cover_openness,
)


def test_no_entity_uses_per_entry_assumption() -> None:
    """Missing sensors honour the explicit per-entry fallback."""

    opened = assumed_openness(AssumedState.OPEN)
    closed = assumed_openness(AssumedState.CLOSED)

    assert opened.openness == 1.0
    assert opened.source == "assumed_no_entity"
    assert closed.openness == 0.0
    assert closed.source == "assumed_no_entity"


def test_unavailable_cover_uses_assumption() -> None:
    """Unavailable covers fall back instead of forcing one global behaviour."""

    opened = resolve_cover_openness(
        "unavailable",
        assumed_state=AssumedState.OPEN,
    )
    closed = resolve_cover_openness(
        "unknown",
        assumed_state=AssumedState.CLOSED,
    )

    assert opened.openness == 1.0
    assert opened.source == "assumed_unavailable"
    assert closed.openness == 0.0
    assert closed.source == "assumed_unavailable"


def test_valid_cover_state_overrides_assumption() -> None:
    """A usable cover state takes precedence over the configured fallback."""

    resolved = resolve_cover_openness(
        "open",
        position=25,
        assumed_state=AssumedState.CLOSED,
    )

    assert resolved.openness == pytest.approx(0.25)
    assert resolved.source == "entity"


def test_binary_state_overrides_assumption_and_can_be_inverted() -> None:
    """Known binary states retain existing inversion behaviour."""

    normal = resolve_binary_openness(
        "off",
        assumed_state=AssumedState.OPEN,
    )
    inverted = resolve_binary_openness(
        "off",
        assumed_state=AssumedState.CLOSED,
        invert=True,
    )

    assert normal.openness == 0.0
    assert normal.source == "entity"
    assert inverted.openness == 1.0
    assert inverted.source == "entity"


def test_inversion_does_not_flip_assumed_state() -> None:
    """Fallback states describe reality directly and are never inverted."""

    resolved = resolve_binary_openness(
        "unavailable",
        assumed_state=AssumedState.CLOSED,
        invert=True,
    )

    assert resolved.openness == 0.0
    assert resolved.source == "assumed_unavailable"
