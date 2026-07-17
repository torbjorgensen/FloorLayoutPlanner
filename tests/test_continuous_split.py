from __future__ import annotations

import pytest
from shapely.geometry import box
from shapely.ops import unary_union

from floor_layout_planner.continuous_solver import (
    build_continuous_floor,
    global_room_polygon,
    passage_polygon,
    split_candidate_at_cut,
)
from floor_layout_planner.models import (
    Candidate,
    CutPlan,
    CutSettings,
    Opening,
    Passage,
    RoomConnection,
)
from floor_layout_planner.planner import create_plan


def room(
    room_id: str,
    *,
    origin_x: float,
    origin_y: float,
    width: float,
    height: float,
) -> dict:
    return {
        "id": room_id,
        "name": room_id,
        "origin": {
            "x": origin_x,
            "y": origin_y,
        },
        "rectangles": [
            {
                "x": 0,
                "y": 0,
                "width": width,
                "height": height,
            }
        ],
    }


def connection() -> RoomConnection:
    return RoomConnection(
        connection_id="stue_kjokken",
        room_a="stue",
        room_b="kjokken",
        connection_type="continuous_then_cut",
        opening=Opening(
            x1=800,
            y1=1000,
            x2=1200,
            y2=1000,
        ),
        align_rows=True,
        align_joints=True,
        weight=10,
        passage=Passage(
            x=800,
            y=1000,
            width=400,
            height=120,
        ),
        cut=CutSettings(
            axis="y",
            gap_width_mm=5,
            edge_clearance_mm=15,
            prefer_existing_joint=True,
            search_step_mm=5,
        ),
    )


def cut_plan() -> CutPlan:
    return CutPlan(
        connection_id="stue_kjokken",
        axis="y",
        position_mm=1060,
        gap_width_mm=5,
        method="saw_cut",
        cut_boards=2,
        short_fragments=0,
        very_short_fragments=0,
        narrow_fragments=0,
        very_narrow_fragments=0,
        shortest_fragment_mm=400,
        narrowest_fragment_mm=120,
        center_distance_mm=0,
        score=(0, 0, 0, 0, 1, 2, 0, -120, -400),
    )


def candidate_for(
    room_a: dict,
    room_b: dict,
    connection_value: RoomConnection,
) -> Candidate:
    floor = build_continuous_floor(
        room_a,
        room_b,
        connection_value,
        expansion_gap_mm=0,
    )
    pieces = create_plan(
        floor=floor,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        base_offset=100,
        row_width_offset=30,
    )

    return Candidate(
        attempt=1,
        total_attempts=1,
        phase="refine",
        base_offset=100,
        row_width_offset=30,
        pieces=pieces,
        short_count=0,
        very_short_count=0,
        shortest_piece=min(piece.length for piece in pieces),
        joint_violations=0,
        narrow_row_count=0,
        very_narrow_row_count=0,
        narrowest_row_width=min(piece.width for piece in pieces),
        row_offsets={},
        score=(0, 0, 0, 0, 0, -120, -400),
        timings={},
    )


def pieces_geometry(pieces):
    return unary_union(
        [
            box(
                piece.x1,
                piece.y1,
                piece.x2,
                piece.y2,
            )
            for piece in pieces
        ]
    )


def test_split_returns_two_room_piece_lists() -> None:
    room_a = room(
        "stue",
        origin_x=0,
        origin_y=0,
        width=2000,
        height=1000,
    )
    room_b = room(
        "kjokken",
        origin_x=0,
        origin_y=1120,
        width=2000,
        height=1000,
    )
    connection_value = connection()
    candidate = candidate_for(
        room_a,
        room_b,
        connection_value,
    )

    split = split_candidate_at_cut(
        candidate=candidate,
        room_a=room_a,
        room_b=room_b,
        connection=connection_value,
        cut_plan=cut_plan(),
        orientation="horizontal",
    )

    assert set(split) == {"stue", "kjokken"}
    assert split["stue"]
    assert split["kjokken"]


def test_no_finished_piece_crosses_expansion_joint() -> None:
    room_a = room(
        "stue",
        origin_x=0,
        origin_y=0,
        width=2000,
        height=1000,
    )
    room_b = room(
        "kjokken",
        origin_x=0,
        origin_y=1120,
        width=2000,
        height=1000,
    )
    connection_value = connection()
    candidate = candidate_for(
        room_a,
        room_b,
        connection_value,
    )
    plan = cut_plan()

    split = split_candidate_at_cut(
        candidate=candidate,
        room_a=room_a,
        room_b=room_b,
        connection=connection_value,
        cut_plan=plan,
        orientation="horizontal",
    )

    gap = box(
        connection_value.passage.x,
        plan.position_mm - plan.gap_width_mm / 2,
        connection_value.passage.x + connection_value.passage.width,
        plan.position_mm + plan.gap_width_mm / 2,
    )

    for pieces in split.values():
        assert pieces_geometry(pieces).intersection(gap).area == pytest.approx(
            0,
            abs=1e-6,
        )


def test_room_a_and_room_b_remain_separate_after_split() -> None:
    room_a = room(
        "stue",
        origin_x=0,
        origin_y=0,
        width=2000,
        height=1000,
    )
    room_b = room(
        "kjokken",
        origin_x=0,
        origin_y=1120,
        width=2000,
        height=1000,
    )
    connection_value = connection()
    candidate = candidate_for(
        room_a,
        room_b,
        connection_value,
    )

    split = split_candidate_at_cut(
        candidate=candidate,
        room_a=room_a,
        room_b=room_b,
        connection=connection_value,
        cut_plan=cut_plan(),
        orientation="horizontal",
    )

    geometry_a = pieces_geometry(split["stue"])
    geometry_b = pieces_geometry(split["kjokken"])

    assert geometry_a.intersection(geometry_b).area == pytest.approx(
        0,
        abs=1e-6,
    )
    assert geometry_a.centroid.y < geometry_b.centroid.y


def test_source_board_indices_are_preserved_across_cut() -> None:
    room_a = room(
        "stue",
        origin_x=0,
        origin_y=0,
        width=2000,
        height=1000,
    )
    room_b = room(
        "kjokken",
        origin_x=0,
        origin_y=1120,
        width=2000,
        height=1000,
    )
    connection_value = connection()
    candidate = candidate_for(
        room_a,
        room_b,
        connection_value,
    )

    split = split_candidate_at_cut(
        candidate=candidate,
        room_a=room_a,
        room_b=room_b,
        connection=connection_value,
        cut_plan=cut_plan(),
        orientation="horizontal",
    )

    source_indices = {piece.source_board_index for piece in candidate.pieces}

    assert {
        piece.source_board_index for pieces in split.values() for piece in pieces
    }.issubset(source_indices)


def test_split_does_not_assign_other_room_area_from_same_half_plane() -> None:
    room_a = {
        "id": "stue",
        "name": "Living room",
        "origin": {"x": 0, "y": 0},
        "rectangles": [
            {"x": 0, "y": 0, "width": 2000, "height": 1000},
            {"x": 0, "y": 1000, "width": 4000, "height": 1000},
        ],
    }
    room_b = room(
        "kjokken",
        origin_x=2200,
        origin_y=0,
        width=1800,
        height=1000,
    )
    connection_value = RoomConnection(
        connection_id="stue_kjokken",
        room_a="stue",
        room_b="kjokken",
        connection_type="continuous_then_cut",
        opening=Opening(x1=2200, y1=1000, x2=2600, y2=1000),
        passage=Passage(x=2200, y=1000, width=400, height=120),
        cut=CutSettings(axis="y", gap_width_mm=5),
    )
    candidate = candidate_for(room_a, room_b, connection_value)

    split = split_candidate_at_cut(
        candidate=candidate,
        room_a=room_a,
        room_b=room_b,
        connection=connection_value,
        cut_plan=cut_plan(),
        orientation="horizontal",
    )

    allowed_a = global_room_polygon(room_a).union(passage_polygon(connection_value))
    allowed_b = global_room_polygon(room_b).union(passage_polygon(connection_value))
    assert pieces_geometry(split["stue"]).difference(allowed_a).area == pytest.approx(
        0, abs=1e-6
    )
    outside_b = pieces_geometry(split["kjokken"]).difference(allowed_b).area
    assert outside_b == pytest.approx(0, abs=1e-6)
