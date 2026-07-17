from __future__ import annotations

import pytest

from floor_layout_planner.connections import parse_connections


def base_config() -> dict:
    return {
        "rooms": [
            {"id": "stue"},
            {"id": "kjokken"},
        ],
        "connections": [
            {
                "id": "stue_kjokken",
                "room_a": "stue",
                "room_b": "kjokken",
                "type": "open_passage",
                "opening": {
                    "x1": 1000,
                    "y1": 2000,
                    "x2": 1900,
                    "y2": 2000,
                },
                "align": {
                    "rows": True,
                    "joints": False,
                },
                "weight": 10,
            }
        ],
    }


def test_parse_valid_connection() -> None:
    connections = parse_connections(base_config())

    assert len(connections) == 1

    connection = connections[0]

    assert connection.connection_id == "stue_kjokken"
    assert connection.room_a == "stue"
    assert connection.room_b == "kjokken"
    assert connection.align_rows is True
    assert connection.align_joints is False
    assert connection.weight == 10


def test_unknown_room_is_rejected() -> None:
    config = base_config()
    config["connections"][0]["room_b"] = "bod"

    with pytest.raises(ValueError, match="unknown room"):
        parse_connections(config)


def test_room_cannot_connect_to_itself() -> None:
    config = base_config()
    config["connections"][0]["room_b"] = "stue"

    with pytest.raises(ValueError, match="to itself"):
        parse_connections(config)


def test_duplicate_connection_id_is_rejected() -> None:
    config = base_config()
    config["connections"].append(dict(config["connections"][0]))

    with pytest.raises(ValueError, match="Duplicate"):
        parse_connections(config)


def test_zero_length_opening_is_rejected() -> None:
    config = base_config()
    config["connections"][0]["opening"] = {
        "x1": 100,
        "y1": 100,
        "x2": 100,
        "y2": 100,
    }

    with pytest.raises(ValueError, match="distinct endpoints"):
        parse_connections(config)


def test_invalid_connection_type_is_rejected() -> None:
    config = base_config()
    config["connections"][0]["type"] = "magic_portal"

    with pytest.raises(ValueError, match="Invalid"):
        parse_connections(config)


def test_parse_continuous_then_cut_connection() -> None:
    config = base_config()

    config["connections"][0].update(
        {
            "type": "continuous_then_cut",
            "passage": {
                "x": 1000,
                "y": 1940,
                "width": 900,
                "height": 120,
            },
            "cut": {
                "axis": "y",
                "gap_width_mm": 5,
                "edge_clearance_mm": 15,
                "prefer_existing_joint": True,
            },
        }
    )

    connection = parse_connections(config)[0]

    assert connection.passage is not None
    assert connection.cut is not None
    assert connection.passage.height == 120
    assert connection.cut.axis == "y"
    assert connection.cut.gap_width_mm == 5
    assert connection.cut.prefer_existing_joint is True


def test_continuous_connection_requires_passage() -> None:
    config = base_config()
    config["connections"][0]["type"] = "continuous_then_cut"

    with pytest.raises(ValueError, match="passage"):
        parse_connections(config)


def test_cut_axis_must_be_valid() -> None:
    config = base_config()

    config["connections"][0].update(
        {
            "type": "continuous_then_cut",
            "passage": {
                "x": 1000,
                "y": 1940,
                "width": 900,
                "height": 120,
            },
            "cut": {
                "axis": "diagonal",
            },
        }
    )

    with pytest.raises(ValueError, match="x.*y"):
        parse_connections(config)


def test_edge_clearance_must_leave_cut_area() -> None:
    config = base_config()

    config["connections"][0].update(
        {
            "type": "continuous_then_cut",
            "passage": {
                "x": 1000,
                "y": 1940,
                "width": 900,
                "height": 120,
            },
            "cut": {
                "axis": "y",
                "edge_clearance_mm": 60,
            },
        }
    )

    with pytest.raises(ValueError, match="valid area"):
        parse_connections(config)
