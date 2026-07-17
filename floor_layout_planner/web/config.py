from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DEFAULT_SETTINGS = {
    "orientation": "horizontal",
    "start_corner": "upper_left",
    "expansion_gap_mm": 5.0,
    "minimum_piece_length_mm": 300.0,
    "minimum_joint_distance_mm": 300.0,
    "stagger_step_mm": 700.0,
    "optimization_step_mm": 20.0,
    "row_width_optimization_step_mm": 5.0,
    "minimum_row_width_mm": 60.0,
    "preferred_minimum_row_width_mm": 100.0,
    "optimizer_workers": 8,
    "preview_every_n_results": 25,
    "local_optimize_top_n": 12,
    "frame_delay_ms": 60,
    "waste_percent": 10.0,
    "boards_per_pack": 8,
}


def new_project_config(name: str) -> dict[str, Any]:
    """Create a valid editable rectangle project for browser-based creation."""
    project_name = name.strip()
    if not project_name:
        raise ValueError("Project name cannot be empty.")
    return {
        "project_name": project_name,
        "board": {"length_mm": 2050, "width_mm": 240, "saw_kerf_mm": 3.2},
        "settings": copy.deepcopy(DEFAULT_SETTINGS),
        "rooms": [
            {
                "id": "room_1",
                "name": "Room 1",
                "origin": {"x": 0, "y": 0},
                "rectangles": [
                    {
                        "name": "Main area",
                        "x": 0,
                        "y": 0,
                        "width": 4000,
                        "height": 3000,
                    }
                ],
                "settings": {},
            }
        ],
        "connections": [],
    }


def load_config(path: Path) -> dict[str, Any]:
    """Load, normalize, and validate a project configuration file."""
    if not path.exists():
        raise FileNotFoundError(f"Could not find config file: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    return normalize_and_validate_config(config)


def normalize_and_validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a validated configuration, upgrading the legacy one-room shape."""
    config = copy.deepcopy(config)

    # Backward compatibility: old one-room format.
    if "rooms" not in config and "rectangles" in config:
        config = {
            "project_name": config.get("section_name", "Floor Project"),
            "board": config["board"],
            "settings": config.get("settings", {}),
            "rooms": [
                {
                    "id": "room_1",
                    "name": config.get("section_name", "Room 1"),
                    "origin": {"x": 0, "y": 0},
                    "rectangles": config["rectangles"],
                    "settings": {},
                }
            ],
        }

    required = {"project_name", "rooms", "board"}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"Configuration is missing fields: {sorted(missing)}")

    if (
        not isinstance(config["project_name"], str)
        or not config["project_name"].strip()
    ):
        raise ValueError("'project_name' must be a non-empty string.")

    board = config["board"]
    if not isinstance(board, dict):
        raise ValueError("'board' must be an object.")
    for field in ("length_mm", "width_mm"):
        value = _finite_number(board.get(field), f"board.{field}")
        if value <= 0:
            raise ValueError(f"'board.{field}' must be greater than 0.")
    kerf = _finite_number(board.get("saw_kerf_mm", 3.2), "board.saw_kerf_mm")
    if kerf < 0 or kerf >= float(board["length_mm"]):
        raise ValueError(
            "'board.saw_kerf_mm' must be non-negative and less than board length."
        )

    if not isinstance(config["rooms"], list) or not config["rooms"]:
        raise ValueError("'rooms' must be a non-empty list.")

    seen_ids: set[str] = set()
    for room in config["rooms"]:
        if not isinstance(room, dict):
            raise ValueError("Every room must be an object.")
        for field in ("id", "name", "rectangles"):
            if field not in room:
                raise ValueError(f"A room is missing the '{field}' field.")
        if not isinstance(room["id"], str) or not room["id"].strip():
            raise ValueError("Every room must have a non-empty string id.")
        if not isinstance(room["name"], str) or not room["name"].strip():
            raise ValueError(f"Room '{room['id']}' must have a non-empty name.")
        if room["id"] in seen_ids:
            raise ValueError(f"Duplicate room id: {room['id']}")
        seen_ids.add(room["id"])
        if not isinstance(room["rectangles"], list) or not room["rectangles"]:
            raise ValueError(f"Room '{room['name']}' is missing rectangles.")
        origin = room.get("origin", {"x": 0, "y": 0})
        if not isinstance(origin, dict):
            raise ValueError(f"Room '{room['name']}' origin must be an object.")
        _finite_number(origin.get("x", 0), f"{room['name']} origin.x")
        _finite_number(origin.get("y", 0), f"{room['name']} origin.y")
        for index, rectangle in enumerate(room["rectangles"], start=1):
            if not isinstance(rectangle, dict):
                raise ValueError(
                    f"Room '{room['name']}' rectangle {index} must be an object."
                )
            _finite_number(rectangle.get("x"), f"{room['name']} rectangle {index} x")
            _finite_number(rectangle.get("y"), f"{room['name']} rectangle {index} y")
            for field in ("width", "height"):
                value = _finite_number(
                    rectangle.get(field),
                    f"{room['name']} rectangle {index} {field}",
                )
                if value <= 0:
                    raise ValueError(
                        f"Room '{room['name']}' rectangle {index} {field} "
                        "must be greater than 0."
                    )

    return config


def _finite_number(value: Any, name: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'{name}' must be a number.") from exc
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        raise ValueError(f"'{name}' must be a finite number.")
    return parsed


def merged_settings(
    project_config: dict[str, Any],
    room: dict[str, Any],
) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(project_config.get("settings", {}))
    settings.update(room.get("settings", {}))

    board_length = float(project_config["board"]["length_mm"])
    if settings.get("stagger_step_mm") in (None, ""):
        settings["stagger_step_mm"] = board_length / 3

    if settings.get("minimum_joint_distance_mm") in (None, ""):
        settings["minimum_joint_distance_mm"] = settings["minimum_piece_length_mm"]

    return settings


def editable_room_settings(
    project_config: dict[str, Any],
    room: dict[str, Any],
) -> dict[str, Any]:
    settings = merged_settings(project_config, room)
    board = project_config["board"]

    return {
        "orientation": settings["orientation"],
        "start_corner": settings["start_corner"],
        "expansion_gap_mm": float(settings["expansion_gap_mm"]),
        # Keep legacy JSON projects valid while kerf moves into board-level
        # configuration, where every room shares the same cutting process.
        "saw_kerf_mm": float(board.get("saw_kerf_mm", 3.2)),
        "minimum_piece_length_mm": float(settings["minimum_piece_length_mm"]),
        "minimum_joint_distance_mm": float(settings["minimum_joint_distance_mm"]),
        "stagger_step_mm": float(settings["stagger_step_mm"]),
        "optimization_step_mm": float(settings["optimization_step_mm"]),
        "row_width_optimization_step_mm": float(
            settings["row_width_optimization_step_mm"]
        ),
        "minimum_row_width_mm": float(settings["minimum_row_width_mm"]),
        "preferred_minimum_row_width_mm": float(
            settings["preferred_minimum_row_width_mm"]
        ),
        "optimizer_workers": int(settings["optimizer_workers"]),
        "preview_every_n_results": int(settings["preview_every_n_results"]),
        "local_optimize_top_n": int(settings["local_optimize_top_n"]),
        "frame_delay_ms": int(settings["frame_delay_ms"]),
        "board_length_mm": float(board["length_mm"]),
        "board_width_mm": float(board["width_mm"]),
        "waste_percent": float(settings["waste_percent"]),
        "boards_per_pack": int(settings["boards_per_pack"]),
    }


def parse_float(payload: dict[str, Any], name: str) -> float:
    try:
        return float(payload[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"'{name}' must be a number.") from exc


def parse_int(payload: dict[str, Any], name: str) -> int:
    try:
        return int(payload[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"'{name}' must be an integer.") from exc


def update_room_settings(
    project_config: dict[str, Any],
    room_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    config = copy.deepcopy(project_config)
    room = next(
        (item for item in config["rooms"] if item["id"] == room_id),
        None,
    )
    if room is None:
        raise ValueError(f"Unknown room id: {room_id}")

    orientation = str(payload.get("orientation", "")).lower()
    if orientation not in {"horizontal", "vertical"}:
        raise ValueError("'orientation' must be 'horizontal' or 'vertical'.")
    start_corner = str(payload.get("start_corner", "")).lower()
    if start_corner not in {
        "upper_left",
        "upper_right",
        "lower_left",
        "lower_right",
    }:
        raise ValueError(
            "'start_corner' must be one of: "
            "upper_left, upper_right, lower_left, lower_right."
        )

    values = {
        "expansion_gap_mm": parse_float(payload, "expansion_gap_mm"),
        "minimum_piece_length_mm": parse_float(payload, "minimum_piece_length_mm"),
        "minimum_joint_distance_mm": parse_float(payload, "minimum_joint_distance_mm"),
        "stagger_step_mm": parse_float(payload, "stagger_step_mm"),
        "optimization_step_mm": parse_float(payload, "optimization_step_mm"),
        "row_width_optimization_step_mm": parse_float(
            payload, "row_width_optimization_step_mm"
        ),
        "minimum_row_width_mm": parse_float(payload, "minimum_row_width_mm"),
        "preferred_minimum_row_width_mm": parse_float(
            payload, "preferred_minimum_row_width_mm"
        ),
        "optimizer_workers": parse_int(payload, "optimizer_workers"),
        "preview_every_n_results": parse_int(payload, "preview_every_n_results"),
        "local_optimize_top_n": parse_int(payload, "local_optimize_top_n"),
        "frame_delay_ms": parse_int(payload, "frame_delay_ms"),
        "waste_percent": parse_float(payload, "waste_percent"),
        "boards_per_pack": parse_int(payload, "boards_per_pack"),
    }

    board_length = parse_float(payload, "board_length_mm")
    board_width = parse_float(payload, "board_width_mm")
    saw_kerf = parse_float(payload, "saw_kerf_mm")

    if values["expansion_gap_mm"] < 0:
        raise ValueError("Expansion gap cannot be negative.")
    if not 0 <= saw_kerf < board_length:
        raise ValueError("Saw kerf must be non-negative and less than board length.")
    if values["minimum_piece_length_mm"] <= 0:
        raise ValueError("Minimum piece length must be greater than 0.")
    if values["minimum_joint_distance_mm"] < 0:
        raise ValueError("Minimum joint distance cannot be negative.")
    if not 0 < values["stagger_step_mm"] < board_length:
        raise ValueError(
            "Stagger step must be greater than 0 and less than the board length."
        )
    if values["optimization_step_mm"] <= 0:
        raise ValueError("Optimization step must be greater than 0.")
    if values["row_width_optimization_step_mm"] <= 0:
        raise ValueError("Row width step must be greater than 0.")
    if values["minimum_row_width_mm"] <= 0:
        raise ValueError("Minimum row width must be greater than 0.")
    if values["preferred_minimum_row_width_mm"] < values["minimum_row_width_mm"]:
        raise ValueError(
            "Preferred minimum row width cannot be smaller than the absolute minimum."
        )
    if values["optimizer_workers"] <= 0:
        raise ValueError("Worker count must be greater than 0.")
    if values["preview_every_n_results"] <= 0:
        raise ValueError("Preview interval must be greater than 0.")
    if values["local_optimize_top_n"] <= 0:
        raise ValueError("Top-N must be greater than 0.")
    if values["frame_delay_ms"] < 0:
        raise ValueError("Frame delay cannot be negative.")
    if board_length <= 0 or board_width <= 0:
        raise ValueError("Board dimensions must be greater than 0.")

    config["board"]["length_mm"] = board_length
    config["board"]["width_mm"] = board_width
    config["board"]["saw_kerf_mm"] = saw_kerf

    room.setdefault("settings", {})
    room["settings"].update(
        {
            "orientation": orientation,
            "start_corner": start_corner,
            **values,
        }
    )

    return config
