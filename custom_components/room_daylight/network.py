"""Bounded room-to-room daylight transfer solver."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .const import MAX_NETWORK_ITERATIONS, NETWORK_CONVERGENCE_LUX
from .models import ConnectionDiagnostic


@dataclass(frozen=True, slots=True)
class NetworkConnection:
    """Runtime representation of a bidirectional physical room connection."""

    connection_id: str
    name: str
    room_a: str
    room_b: str
    opening_area_m2: float
    transmission: float
    transfer_efficiency: float
    state_entity: str | None = None
    state_description: str | None = None

    def other_room(self, room_id: str) -> str:
        """Return the room at the opposite end of this connection."""

        if room_id == self.room_a:
            return self.room_b
        if room_id == self.room_b:
            return self.room_a
        raise ValueError(f"Room {room_id!r} is not part of connection {self.name!r}")

    def weight_for(self, receiving_floor_area_m2: float) -> float:
        """Return the directed transfer weight into a receiving room."""

        if receiving_floor_area_m2 <= 0.0:
            return 0.0
        efficiency = min(1.0, max(0.0, self.transfer_efficiency))
        transmission = min(1.0, max(0.0, self.transmission))
        return max(
            0.0,
            (self.opening_area_m2 / receiving_floor_area_m2)
            * efficiency
            * transmission,
        )


@dataclass(frozen=True, slots=True)
class NetworkSolution:
    """Converged network values and explainability data."""

    room_lux: Mapping[str, float]
    diagnostics: Mapping[str, tuple[ConnectionDiagnostic, ...]]
    iterations: int
    converged: bool


def _validate_inputs(
    native_lux: Mapping[str, float],
    floor_area_m2: Mapping[str, float],
    connections: Sequence[NetworkConnection],
) -> None:
    """Validate graph references before solving."""

    room_ids = set(native_lux)
    if room_ids != set(floor_area_m2):
        raise ValueError("Native lux and floor-area maps must contain the same rooms")

    for connection in connections:
        if connection.room_a not in room_ids or connection.room_b not in room_ids:
            raise ValueError(
                f"Connection {connection.name!r} references a room that does not exist"
            )
        if connection.room_a == connection.room_b:
            raise ValueError(
                f"Connection {connection.name!r} connects a room to itself"
            )


def solve_room_network(
    native_lux: Mapping[str, float],
    floor_area_m2: Mapping[str, float],
    connections: Sequence[NetworkConnection],
    *,
    tolerance_lux: float = NETWORK_CONVERGENCE_LUX,
    max_iterations: int = MAX_NETWORK_ITERATIONS,
) -> NetworkSolution:
    """Equilibrate daylight through the room graph without creating light.

    Each room is updated with a Jacobi iteration::

        candidate = (native + sum(weight * neighbour)) / (1 + sum(weight))
        new = max(native, candidate)

    Because every candidate is a weighted average and never drops below native
    daylight, transfer cannot make a room brighter than the brightest reachable
    native daylight source.
    """

    _validate_inputs(native_lux, floor_area_m2, connections)

    native = {room_id: max(0.0, float(value)) for room_id, value in native_lux.items()}
    current = dict(native)
    by_room: dict[str, list[NetworkConnection]] = {room_id: [] for room_id in native}
    for connection in connections:
        by_room[connection.room_a].append(connection)
        by_room[connection.room_b].append(connection)

    if not current:
        return NetworkSolution({}, {}, 0, True)

    converged = False
    iterations = 0
    tolerance = max(0.0, float(tolerance_lux))

    for iteration in range(1, max(1, int(max_iterations)) + 1):
        updated: dict[str, float] = {}
        largest_change = 0.0

        for room_id, native_value in native.items():
            weighted_sum = 0.0
            total_weight = 0.0
            for connection in by_room[room_id]:
                other = connection.other_room(room_id)
                weight = connection.weight_for(floor_area_m2[room_id])
                if weight <= 0.0:
                    continue
                weighted_sum += weight * current[other]
                total_weight += weight

            candidate = (native_value + weighted_sum) / (1.0 + total_weight)
            value = max(native_value, candidate)
            updated[room_id] = value
            largest_change = max(largest_change, abs(value - current[room_id]))

        current = updated
        iterations = iteration
        if largest_change < tolerance:
            converged = True
            break

    diagnostics: dict[str, tuple[ConnectionDiagnostic, ...]] = {}
    for room_id, native_value in native.items():
        room_connections = by_room[room_id]
        weights = [
            connection.weight_for(floor_area_m2[room_id])
            for connection in room_connections
        ]
        denominator = 1.0 + sum(weights)
        transferred_lux = max(0.0, current[room_id] - native_value)
        positive_influences = [
            weight * max(0.0, current[connection.other_room(room_id)] - native_value)
            / denominator
            for connection, weight in zip(room_connections, weights, strict=True)
        ]
        positive_total = sum(positive_influences)
        room_diagnostics: list[ConnectionDiagnostic] = []

        for connection, weight, positive_influence in zip(
            room_connections,
            weights,
            positive_influences,
            strict=True,
        ):
            other = connection.other_room(room_id)
            # Lower-lux neighbours can damp the weighted candidate.  Attribute
            # the room's *actual* positive transfer proportionally across only
            # brighter neighbours so connection contributions remain intuitive
            # and sum to the room's reported transferred daylight.
            contribution = (
                transferred_lux * positive_influence / positive_total
                if positive_total > 0.0
                else 0.0
            )
            room_diagnostics.append(
                ConnectionDiagnostic(
                    connection_id=connection.connection_id,
                    name=connection.name,
                    other_room_id=other,
                    opening_area_m2=connection.opening_area_m2,
                    transmission=connection.transmission,
                    transfer_efficiency=connection.transfer_efficiency,
                    transfer_weight=weight,
                    contribution_lux=contribution,
                    state_entity=connection.state_entity,
                    state_description=connection.state_description,
                )
            )

        diagnostics[room_id] = tuple(room_diagnostics)

    return NetworkSolution(current, diagnostics, iterations, converged)
