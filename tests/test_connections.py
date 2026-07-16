from __future__ import annotations

import pytest

from pergo_planner.connections import parse_connections


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

    with pytest.raises(ValueError, match="ukjent rom"):
        parse_connections(config)


def test_room_cannot_connect_to_itself() -> None:
    config = base_config()
    config["connections"][0]["room_b"] = "stue"

    with pytest.raises(ValueError, match="seg selv"):
        parse_connections(config)


def test_duplicate_connection_id_is_rejected() -> None:
    config = base_config()
    config["connections"].append(dict(config["connections"][0]))

    with pytest.raises(ValueError, match="Duplisert"):
        parse_connections(config)


def test_zero_length_opening_is_rejected() -> None:
    config = base_config()
    config["connections"][0]["opening"] = {
        "x1": 100,
        "y1": 100,
        "x2": 100,
        "y2": 100,
    }

    with pytest.raises(ValueError, match="endepunkter"):
        parse_connections(config)


def test_invalid_connection_type_is_rejected() -> None:
    config = base_config()
    config["connections"][0]["type"] = "magic_portal"

    with pytest.raises(ValueError, match="Ugyldig"):
        parse_connections(config)
