"""Pure helpers for resolving opening and connection openness.

Home Assistant state objects are deliberately kept out of this module.  The
coordinator passes the small amount of state data required here so fallback
behaviour remains independently testable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .const import AssumedState

_UNKNOWN_STATES = {None, "unknown", "unavailable"}
_OPEN_COVER_STATES = {"open", "opening"}
_CLOSED_COVER_STATES = {"closed", "closing"}


@dataclass(frozen=True, slots=True)
class ResolvedOpenness:
    """Effective openness and explainability metadata for one state source."""

    openness: float
    description: str
    source: str


def _clamp(value: float, lower: float, upper: float) -> float:
    """Clamp ``value`` to an inclusive interval."""

    return max(lower, min(upper, value))


def _assumed_openness(assumed_state: AssumedState, *, source: str) -> ResolvedOpenness:
    """Resolve a configured assumption to an effective openness."""

    openness = 1.0 if assumed_state is AssumedState.OPEN else 0.0
    reason = "no entity" if source == "assumed_no_entity" else "entity unavailable"
    return ResolvedOpenness(
        openness=openness,
        description=f"assumed {assumed_state.value} ({reason})",
        source=source,
    )


def assumed_openness(assumed_state: AssumedState) -> ResolvedOpenness:
    """Return the fallback used when no state entity is configured."""

    return _assumed_openness(assumed_state, source="assumed_no_entity")


def resolve_cover_openness(
    state: str | None,
    *,
    position: Any = None,
    assumed_state: AssumedState,
    invert: bool = False,
) -> ResolvedOpenness:
    """Resolve a cover state, falling back to the configured assumption.

    ``position`` is the Home Assistant ``current_position`` attribute when it
    is available.  Inversion applies only to a known entity state; it never
    changes the configured fallback assumption.
    """

    if state in _UNKNOWN_STATES:
        return _assumed_openness(assumed_state, source="assumed_unavailable")

    openness: float | None = None
    if position is not None:
        try:
            parsed_position = float(position)
        except (TypeError, ValueError):
            parsed_position = math.nan
        if math.isfinite(parsed_position):
            openness = _clamp(parsed_position / 100.0, 0.0, 1.0)

    if openness is None:
        if state in _OPEN_COVER_STATES:
            openness = 1.0
        elif state in _CLOSED_COVER_STATES:
            openness = 0.0
        else:
            return _assumed_openness(assumed_state, source="assumed_unavailable")

    if invert:
        openness = 1.0 - openness
        suffix = " (inverted)"
    else:
        suffix = ""

    return ResolvedOpenness(
        openness=openness,
        description=f"{round(openness * 100)}% open{suffix}",
        source="entity",
    )


def resolve_binary_openness(
    state: str | None,
    *,
    assumed_state: AssumedState,
    invert: bool = False,
) -> ResolvedOpenness:
    """Resolve binary open/closed semantics with an assumed fallback."""

    if state in _UNKNOWN_STATES:
        return _assumed_openness(assumed_state, source="assumed_unavailable")

    if state == "on":
        openness = 1.0
    elif state == "off":
        openness = 0.0
    else:
        return _assumed_openness(assumed_state, source="assumed_unavailable")

    if invert:
        openness = 1.0 - openness
        suffix = " (inverted)"
    else:
        suffix = ""

    effective_state = "open" if openness >= 1.0 else "closed"
    return ResolvedOpenness(
        openness=openness,
        description=f"{effective_state}{suffix}",
        source="entity",
    )
