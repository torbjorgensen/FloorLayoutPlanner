from __future__ import annotations

import copy
from typing import Any

from pergo_planner.geometry import build_floor_polygon
from pergo_planner.web.config import editable_room_settings, merged_settings
from pergo_planner.web.state import ProjectState, RoomState


def global_rectangles(room: dict[str, Any]) -> list[dict[str, Any]]:
    origin = room.get("origin", {})
    origin_x = float(origin.get("x", 0))
    origin_y = float(origin.get("y", 0))

    result = []
    for rectangle in room["rectangles"]:
        item = copy.deepcopy(rectangle)
        item["x"] = origin_x + float(rectangle["x"])
        item["y"] = origin_y + float(rectangle["y"])
        result.append(item)
    return result


def local_floor(
    project_config: dict[str, Any],
    room: dict[str, Any],
):
    settings = merged_settings(project_config, room)
    return build_floor_polygon(
        room["rectangles"],
        float(settings["expansion_gap_mm"]),
    )


def room_canvas_payload(
    project_config: dict[str, Any],
    room: dict[str, Any],
    room_state: RoomState,
    state: ProjectState,
) -> dict[str, Any]:
    settings = merged_settings(project_config, room)
    floor = local_floor(project_config, room)
    origin = room.get("origin", {})
    origin_x = float(origin.get("x", 0))
    origin_y = float(origin.get("y", 0))

    candidate = (
        room_state.best
        if room_state.finished and room_state.best is not None
        else room_state.current or room_state.best
    )
    candidate_payload = state.candidate_payload(candidate)

    if candidate_payload:
        for piece in candidate_payload["pieces"]:
            piece["x1"] += origin_x
            piece["x2"] += origin_x
            piece["y1"] += origin_y
            piece["y2"] += origin_y

    outline = [[x + origin_x, y + origin_y] for x, y in floor.exterior.coords]

    bounds = floor.bounds
    return {
        "id": room["id"],
        "name": room["name"],
        "origin": {"x": origin_x, "y": origin_y},
        "rectangles": global_rectangles(room),
        "outline": outline,
        "bounds": {
            "min_x": bounds[0] + origin_x,
            "min_y": bounds[1] + origin_y,
            "max_x": bounds[2] + origin_x,
            "max_y": bounds[3] + origin_y,
        },
        "settings": editable_room_settings(project_config, room),
        "minimum_piece_length": float(settings["minimum_piece_length_mm"]),
        "running": room_state.running,
        "paused": room_state.paused,
        "finished": room_state.finished,
        "error": room_state.error,
        "current": candidate_payload,
        "best": state.candidate_payload(room_state.best),
        "profile": copy.deepcopy(room_state.profile),
    }
