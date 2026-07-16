from __future__ import annotations

from dataclasses import dataclass

from .planner import Piece

Score = tuple[int, int, int, int, int, float, float]
TimingValue = float | int


@dataclass(frozen=True)
class Candidate:
    attempt: int
    total_attempts: int
    phase: str
    base_offset: float
    row_width_offset: float
    pieces: list[Piece]
    short_count: int
    very_short_count: int
    shortest_piece: float
    joint_violations: int
    narrow_row_count: int
    very_narrow_row_count: int
    narrowest_row_width: float
    row_offsets: dict[int, float]
    score: Score
    timings: dict[str, TimingValue]


@dataclass(frozen=True)
class CandidateInput:
    attempt: int
    total_attempts: int
    floor_wkb: bytes
    board_length: float
    board_width: float
    orientation: str
    stagger_step: float
    minimum_piece_length: float
    minimum_joint_distance: float
    minimum_row_width: float
    preferred_minimum_row_width: float
    optimization_step: float
    base_offset: float
    row_width_offset: float


@dataclass(frozen=True)
class Opening:
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class RoomConnection:
    connection_id: str
    room_a: str
    room_b: str
    connection_type: str
    opening: Opening
    align_rows: bool = True
    align_joints: bool = False
    weight: float = 1.0
    passage: Passage | None = None
    cut: CutSettings | None = None


@dataclass(frozen=True)
class Passage:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class CutSettings:
    axis: str
    gap_width_mm: float = 5.0
    edge_clearance_mm: float = 15.0
    prefer_existing_joint: bool = True
