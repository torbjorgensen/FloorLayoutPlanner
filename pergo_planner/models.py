from __future__ import annotations

from dataclasses import dataclass, field

from .planner import Piece

Score = tuple[int | float, ...]
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
    material_metrics: dict[str, float | int] = field(default_factory=dict)


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
    saw_kerf_mm: float
    base_offset: float
    row_width_offset: float
    start_corner: str = "upper_left"


@dataclass(frozen=True)
class Opening:
    x1: float
    y1: float
    x2: float
    y2: float


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
    search_step_mm: float = 5.0


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
class CutPlan:
    connection_id: str
    axis: str
    position_mm: float
    gap_width_mm: float
    method: str
    cut_boards: int
    short_fragments: int
    very_short_fragments: int
    narrow_fragments: int
    very_narrow_fragments: int
    shortest_fragment_mm: float
    narrowest_fragment_mm: float
    center_distance_mm: float
    score: tuple
