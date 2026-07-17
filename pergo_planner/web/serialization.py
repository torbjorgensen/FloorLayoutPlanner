from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from pergo_planner.connections import connection_payload
from pergo_planner.continuous_solver import cut_plan_payload
from pergo_planner.web.payloads import room_canvas_payload
from pergo_planner.web.state import ProjectState


def build_state_payload(state: ProjectState, output_dir: Path) -> dict[str, Any]:
    """Build a consistent project snapshot while holding the state lock."""
    with state.lock:
        config = copy.deepcopy(state.active_config)
        rooms = [
            room_canvas_payload(config, room, state.rooms[room["id"]], state)
            for room in config["rooms"]
        ]
        connections = [
            {
                **connection_payload(connection),
                "continuous": _continuous_payload(state, connection.connection_id)
                if connection.connection_type == "continuous_then_cut"
                else None,
            }
            for connection in state.connections
        ]

    bounds = [room["bounds"] for room in rooms]
    project_bounds = {
        "min_x": min(item["min_x"] for item in bounds),
        "min_y": min(item["min_y"] for item in bounds),
        "max_x": max(item["max_x"] for item in bounds),
        "max_y": max(item["max_y"] for item in bounds),
    }
    return {
        "project_name": config["project_name"],
        "board": config["board"],
        "rooms": rooms,
        "bounds": project_bounds,
        "output_dir": str(output_dir),
        "connections": connections,
    }


def _continuous_payload(state: ProjectState, connection_id: str) -> dict[str, Any]:
    continuous = state.continuous[connection_id]
    return {
        "running": continuous.running,
        "finished": continuous.finished,
        "error": continuous.error,
        "candidate": state.candidate_payload(continuous.current or continuous.best),
        "profile": copy.deepcopy(continuous.profile),
        "room_pieces": {
            room_id: [state.piece_payload(piece) for piece in pieces]
            for room_id, pieces in continuous.room_pieces.items()
        },
        "cut_plan": (
            cut_plan_payload(continuous.cut_plan)
            if continuous.cut_plan is not None
            else None
        ),
    }
