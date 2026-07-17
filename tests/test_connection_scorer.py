from __future__ import annotations

import pytest

from floor_layout_planner.connection_scorer import (
    _circular_distance,
    score_row_alignment,
)
from floor_layout_planner.models import (
    Candidate,
    Opening,
    RoomConnection,
)


def candidate(row_width_offset: float) -> Candidate:
    return Candidate(
        attempt=1,
        total_attempts=1,
        phase="refine",
        base_offset=0,
        row_width_offset=row_width_offset,
        pieces=[],
        short_count=0,
        very_short_count=0,
        shortest_piece=500,
        joint_violations=0,
        narrow_row_count=0,
        very_narrow_row_count=0,
        narrowest_row_width=120,
        row_offsets={},
        score=(0,),
        timings={},
    )


def connection() -> RoomConnection:
    return RoomConnection(
        connection_id="stue_kjokken",
        room_a="stue",
        room_b="kjokken",
        connection_type="open_passage",
        opening=Opening(
            x1=1000,
            y1=2000,
            x2=1900,
            y2=2000,
        ),
        align_rows=True,
        align_joints=False,
        weight=10,
    )


def test_circular_distance_wraps_board_width() -> None:
    assert _circular_distance(5, 235, 240) == pytest.approx(10)


def test_identical_row_grids_score_one_hundred_percent() -> None:
    result = score_row_alignment(
        connection=connection(),
        room_a={"origin": {"x": 0, "y": 0}},
        candidate_a=candidate(20),
        orientation_a="horizontal",
        floor_bounds_a=(5, 5, 1000, 1000),
        room_b={"origin": {"x": 1000, "y": 0}},
        candidate_b=candidate(20),
        orientation_b="horizontal",
        floor_bounds_b=(5, 5, 1000, 1000),
        board_width=240,
    )

    assert result["row_mismatch_mm"] == pytest.approx(0)
    assert result["row_alignment_percent"] == pytest.approx(100)


def test_half_board_mismatch_scores_zero_percent() -> None:
    result = score_row_alignment(
        connection=connection(),
        room_a={"origin": {"x": 0, "y": 0}},
        candidate_a=candidate(0),
        orientation_a="horizontal",
        floor_bounds_a=(0, 0, 1000, 1000),
        room_b={"origin": {"x": 1000, "y": 0}},
        candidate_b=candidate(120),
        orientation_b="horizontal",
        floor_bounds_b=(0, 0, 1000, 1000),
        board_width=240,
    )

    assert result["row_mismatch_mm"] == pytest.approx(120)
    assert result["row_alignment_percent"] == pytest.approx(0)


def test_matching_lower_start_corners_keep_row_alignment() -> None:
    result = score_row_alignment(
        connection=connection(),
        room_a={
            "origin": {"x": 0, "y": 0},
            "settings": {"start_corner": "lower_left"},
        },
        candidate_a=candidate(20),
        orientation_a="horizontal",
        floor_bounds_a=(0, 5, 1000, 1000),
        room_b={
            "origin": {"x": 1000, "y": 0},
            "settings": {"start_corner": "lower_left"},
        },
        candidate_b=candidate(20),
        orientation_b="horizontal",
        floor_bounds_b=(0, 5, 1000, 1000),
        board_width=240,
    )

    assert result["row_mismatch_mm"] == pytest.approx(0)
    assert result["row_alignment_percent"] == pytest.approx(100)
