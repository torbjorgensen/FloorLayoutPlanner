from __future__ import annotations

import copy
import threading
from typing import Any

from pergo_planner.connections import parse_connections
from pergo_planner.models import Candidate


class RoomState:
    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self.running = False
        self.paused = False
        self.finished = False
        self.error: str | None = None
        self.current: Candidate | None = None
        self.best: Candidate | None = None
        self.generation = 0
        self.profile: dict[str, Any] = {
            "phase": "idle",
            "started_at": None,
            "elapsed_s": 0.0,
            "completed": 0,
            "total": 0,
            "candidates_per_second": 0.0,
            "eta_s": None,
            "workers": 0,
            "coarse_total": 0,
            "coarse_completed": 0,
            "refine_total": 0,
            "refine_completed": 0,
            "timing_totals": {},
            "local_variants": 0,
        }


class ContinuousState:
    def __init__(self, connection_id: str) -> None:
        self.connection_id = connection_id
        self.running = False
        self.finished = False
        self.error: str | None = None
        self.current: Candidate | None = None
        self.best: Candidate | None = None
        self.cut_plan = None
        self.room_pieces: dict[str, list] = {}
        self.provisional = False
        self.profile: dict[str, Any] = {
            "phase": "idle",
            "completed": 0,
            "total": 0,
            "percent": 0.0,
            "elapsed_s": 0.0,
            "eta_s": None,
            "candidates_per_second": 0.0,
            "workers": 0,
            "coarse_total": 0,
            "coarse_completed": 0,
            "refine_total": 0,
            "refine_completed": 0,
            "message": "Waiting",
        }
        self.generation = 0


class ProjectState:
    def __init__(self, config: dict[str, Any]) -> None:
        self.lock = threading.RLock()
        self.file_config = copy.deepcopy(config)
        self.active_config = copy.deepcopy(config)
        self.connections = parse_connections(config)
        self.continuous: dict[str, ContinuousState] = {
            connection.connection_id: ContinuousState(connection.connection_id)
            for connection in self.connections
            if connection.connection_type == "continuous_then_cut"
        }
        self.rooms: dict[str, RoomState] = {
            room["id"]: RoomState(room["id"]) for room in config["rooms"]
        }

    @staticmethod
    def piece_payload(piece: Any) -> dict[str, Any]:
        return {
            "row": piece.row,
            "segment": piece.segment,
            "piece": piece.piece,
            "x1": piece.x1,
            "x2": piece.x2,
            "y1": piece.y1,
            "y2": piece.y2,
            "length": piece.length,
            "width": piece.width,
            "source_board_index": piece.source_board_index,
            "physical_board_id": piece.physical_board_id,
            "is_full_length": piece.is_full_length,
        }

    def candidate_payload(self, candidate: Candidate | None) -> dict | None:
        if candidate is None:
            return None

        return {
            "attempt": candidate.attempt,
            "total_attempts": candidate.total_attempts,
            "base_offset": candidate.base_offset,
            "row_width_offset": candidate.row_width_offset,
            "short_count": candidate.short_count,
            "very_short_count": candidate.very_short_count,
            "shortest_piece": candidate.shortest_piece,
            "joint_violations": candidate.joint_violations,
            "narrow_row_count": candidate.narrow_row_count,
            "very_narrow_row_count": candidate.very_narrow_row_count,
            "narrowest_row_width": candidate.narrowest_row_width,
            "row_offsets": candidate.row_offsets,
            "phase": candidate.phase,
            "timings": candidate.timings,
            "material_metrics": candidate.material_metrics,
            "pieces": [self.piece_payload(piece) for piece in candidate.pieces],
        }
