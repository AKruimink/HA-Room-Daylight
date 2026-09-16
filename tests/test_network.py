"""Tests for the bounded room daylight network."""

import pytest

from custom_components.room_daylight.network import (
    NetworkConnection,
    solve_room_network,
)


def _connection(
    room_a: str,
    room_b: str,
    *,
    connection_id: str = "connection",
    area: float = 1.0,
    transmission: float = 1.0,
    efficiency: float = 1.0,
) -> NetworkConnection:
    return NetworkConnection(
        connection_id=connection_id,
        name=connection_id,
        room_a=room_a,
        room_b=room_b,
        opening_area_m2=area,
        transmission=transmission,
        transfer_efficiency=efficiency,
    )


def test_bright_room_transfers_without_dimming_or_amplifying_source() -> None:
    solution = solve_room_network(
        {"bright": 300.0, "dark": 0.0},
        {"bright": 10.0, "dark": 10.0},
        [_connection("bright", "dark")],
    )

    assert solution.room_lux["bright"] == 300.0
    assert 0.0 < solution.room_lux["dark"] < 300.0
    assert max(solution.room_lux.values()) <= 300.0
    assert solution.converged is True


def test_equal_native_rooms_remain_equal() -> None:
    solution = solve_room_network(
        {"a": 100.0, "b": 100.0},
        {"a": 10.0, "b": 10.0},
        [_connection("a", "b")],
    )
    assert solution.room_lux == {"a": 100.0, "b": 100.0}


def test_multi_hop_transfer_reaches_rooms_without_exterior_daylight() -> None:
    solution = solve_room_network(
        {"bedroom": 300.0, "landing": 0.0, "hall": 0.0},
        {"bedroom": 10.0, "landing": 5.0, "hall": 8.0},
        [
            _connection("bedroom", "landing", connection_id="door"),
            _connection("landing", "hall", connection_id="stairs"),
        ],
    )
    assert solution.room_lux["landing"] > 0.0
    assert solution.room_lux["hall"] > 0.0
    assert solution.room_lux["hall"] < solution.room_lux["landing"] < 300.0


def test_receiving_floor_area_makes_transfer_direction_asymmetric() -> None:
    connection = _connection("large", "small")

    into_small = solve_room_network(
        {"large": 300.0, "small": 0.0},
        {"large": 30.0, "small": 5.0},
        [connection],
    )
    into_large = solve_room_network(
        {"large": 0.0, "small": 300.0},
        {"large": 30.0, "small": 5.0},
        [connection],
    )

    assert into_small.room_lux["small"] > into_large.room_lux["large"]


def test_multiple_connections_between_same_rooms_are_combined() -> None:
    one = solve_room_network(
        {"a": 300.0, "b": 0.0},
        {"a": 10.0, "b": 10.0},
        [_connection("a", "b", connection_id="one")],
    )
    two = solve_room_network(
        {"a": 300.0, "b": 0.0},
        {"a": 10.0, "b": 10.0},
        [
            _connection("a", "b", connection_id="one"),
            _connection("a", "b", connection_id="two"),
        ],
    )
    assert two.room_lux["b"] > one.room_lux["b"]


def test_closed_connection_transfers_nothing() -> None:
    solution = solve_room_network(
        {"a": 300.0, "b": 0.0},
        {"a": 10.0, "b": 10.0},
        [_connection("a", "b", transmission=0.0)],
    )
    assert solution.room_lux == {"a": 300.0, "b": 0.0}


def test_network_never_exceeds_brightest_native_room() -> None:
    native = {"a": 420.0, "b": 40.0, "c": 0.0, "d": 120.0}
    solution = solve_room_network(
        native,
        {room_id: 4.0 + index for index, room_id in enumerate(native)},
        [
            _connection("a", "b", connection_id="ab", area=4.0),
            _connection("b", "c", connection_id="bc", area=3.0),
            _connection("c", "d", connection_id="cd", area=2.0),
            _connection("d", "a", connection_id="da", area=5.0),
        ],
    )
    assert max(solution.room_lux.values()) <= max(native.values())
    for room_id, native_lux in native.items():
        assert solution.room_lux[room_id] >= native_lux


def test_connection_diagnostics_sum_to_reported_transfer() -> None:
    solution = solve_room_network(
        {"bright": 300.0, "middle": 50.0, "dark": 0.0},
        {"bright": 10.0, "middle": 10.0, "dark": 10.0},
        [
            _connection("bright", "middle", connection_id="bright-middle"),
            _connection("middle", "dark", connection_id="middle-dark"),
            _connection("bright", "dark", connection_id="bright-dark"),
        ],
    )

    for room_id, native_lux in {
        "bright": 300.0,
        "middle": 50.0,
        "dark": 0.0,
    }.items():
        diagnostic_transfer = sum(
            item.contribution_lux for item in solution.diagnostics[room_id]
        )
        assert diagnostic_transfer == pytest.approx(
            solution.room_lux[room_id] - native_lux
        )


def test_connection_ratios_are_bounded_defensively() -> None:
    connection = _connection(
        "a",
        "b",
        area=2.0,
        transmission=5.0,
        efficiency=4.0,
    )
    assert connection.weight_for(10.0) == pytest.approx(0.2)


def test_invalid_connection_reference_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not exist"):
        solve_room_network(
            {"a": 100.0},
            {"a": 10.0},
            [_connection("a", "missing")],
        )


def test_other_room_rejects_unrelated_room() -> None:
    connection = _connection("a", "b")
    with pytest.raises(ValueError, match="not part"):
        connection.other_room("c")


def test_zero_or_negative_receiving_area_has_no_transfer_weight() -> None:
    connection = _connection("a", "b")
    assert connection.weight_for(0.0) == 0.0
    assert connection.weight_for(-1.0) == 0.0


def test_floor_area_map_must_match_native_rooms() -> None:
    with pytest.raises(ValueError, match="same rooms"):
        solve_room_network({"a": 100.0}, {"b": 10.0}, [])


def test_self_connection_is_rejected() -> None:
    with pytest.raises(ValueError, match="itself"):
        solve_room_network(
            {"a": 100.0},
            {"a": 10.0},
            [_connection("a", "a")],
        )


def test_empty_network_is_valid() -> None:
    solution = solve_room_network({}, {}, [])
    assert solution.room_lux == {}
    assert solution.diagnostics == {}
    assert solution.iterations == 0
    assert solution.converged is True
