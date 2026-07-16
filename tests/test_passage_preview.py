from __future__ import annotations

import pytest
from shapely.geometry import box
from shapely.ops import unary_union

from pergo_planner.models import (
    Candidate,
    CutSettings,
    Opening,
    Passage,
    RoomConnection,
)
from pergo_planner.passage_preview import create_passage_preview


def make_candidate(
    *,
    base_offset: float = 0.0,
    row_width_offset: float = 0.0,
) -> Candidate:
    return Candidate(
        attempt=1,
        total_attempts=1,
        phase="refine",
        base_offset=base_offset,
        row_width_offset=row_width_offset,
        pieces=[],
        short_count=0,
        very_short_count=0,
        shortest_piece=500.0,
        joint_violations=0,
        narrow_row_count=0,
        very_narrow_row_count=0,
        narrowest_row_width=120.0,
        row_offsets={},
        score=(0, 0, 0, 0, 0, -120.0, -500.0),
        timings={},
    )


def make_horizontal_connection() -> RoomConnection:
    return RoomConnection(
        connection_id="living_kitchen",
        room_a="living",
        room_b="kitchen",
        connection_type="continuous_then_cut",
        opening=Opening(
            x1=2000.0,
            y1=4000.0,
            x2=3000.0,
            y2=4000.0,
        ),
        align_rows=True,
        align_joints=True,
        weight=10.0,
        passage=Passage(
            x=2000.0,
            y=4000.0,
            width=1000.0,
            height=120.0,
        ),
        cut=CutSettings(
            axis="y",
            gap_width_mm=5.0,
            edge_clearance_mm=15.0,
            prefer_existing_joint=True,
        ),
    )


def make_vertical_connection() -> RoomConnection:
    return RoomConnection(
        connection_id="living_hall",
        room_a="living",
        room_b="hall",
        connection_type="continuous_then_cut",
        opening=Opening(
            x1=4000.0,
            y1=1700.0,
            x2=4000.0,
            y2=2600.0,
        ),
        align_rows=True,
        align_joints=True,
        weight=10.0,
        passage=Passage(
            x=4000.0,
            y=1700.0,
            width=120.0,
            height=900.0,
        ),
        cut=CutSettings(
            axis="x",
            gap_width_mm=5.0,
            edge_clearance_mm=15.0,
            prefer_existing_joint=True,
        ),
    )


def pieces_polygon(pieces):
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


def test_horizontal_passage_preview_contains_valid_pieces() -> None:
    room = {
        "id": "living",
        "name": "Living room",
        "origin": {
            "x": 0,
            "y": 0,
        },
        "rectangles": [
            {
                "x": 0,
                "y": 0,
                "width": 5000,
                "height": 4000,
            }
        ],
    }

    pieces = create_passage_preview(
        connection=make_horizontal_connection(),
        master_room=room,
        candidate=make_candidate(
            base_offset=350,
            row_width_offset=40,
        ),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
    )

    assert pieces
    assert all(piece.length > 0 for piece in pieces)
    assert all(piece.width > 0 for piece in pieces)


def test_horizontal_preview_covers_entire_passage() -> None:
    connection = make_horizontal_connection()

    room = {
        "id": "living",
        "origin": {
            "x": 0,
            "y": 0,
        },
        "rectangles": [
            {
                "x": 0,
                "y": 0,
                "width": 5000,
                "height": 4000,
            }
        ],
    }

    pieces = create_passage_preview(
        connection=connection,
        master_room=room,
        candidate=make_candidate(
            base_offset=0,
            row_width_offset=35,
        ),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
    )

    passage = connection.passage
    assert passage is not None

    expected_polygon = box(
        passage.x,
        passage.y,
        passage.x + passage.width,
        passage.y + passage.height,
    )
    actual_polygon = pieces_polygon(pieces)

    assert actual_polygon.symmetric_difference(expected_polygon).area == pytest.approx(
        0,
        abs=1e-4,
    )


def test_vertical_preview_covers_entire_passage() -> None:
    connection = make_vertical_connection()

    room = {
        "id": "living",
        "origin": {
            "x": 0,
            "y": 0,
        },
        "rectangles": [
            {
                "x": 0,
                "y": 0,
                "width": 4000,
                "height": 5000,
            }
        ],
    }

    pieces = create_passage_preview(
        connection=connection,
        master_room=room,
        candidate=make_candidate(
            base_offset=200,
            row_width_offset=25,
        ),
        board_length=2050,
        board_width=240,
        orientation="vertical",
        stagger_step=700,
        minimum_piece_length=300,
    )

    passage = connection.passage
    assert passage is not None

    expected_polygon = box(
        passage.x,
        passage.y,
        passage.x + passage.width,
        passage.y + passage.height,
    )
    actual_polygon = pieces_polygon(pieces)

    assert pieces
    assert actual_polygon.symmetric_difference(expected_polygon).area == pytest.approx(
        0,
        abs=1e-4,
    )


def test_preview_pieces_stay_inside_passage() -> None:
    connection = make_horizontal_connection()

    room = {
        "id": "living",
        "origin": {
            "x": 0,
            "y": 0,
        },
        "rectangles": [
            {
                "x": 0,
                "y": 0,
                "width": 5000,
                "height": 4000,
            }
        ],
    }

    pieces = create_passage_preview(
        connection=connection,
        master_room=room,
        candidate=make_candidate(),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
    )

    passage = connection.passage
    assert passage is not None

    passage_polygon = box(
        passage.x,
        passage.y,
        passage.x + passage.width,
        passage.y + passage.height,
    )

    for piece in pieces:
        piece_polygon = box(
            piece.x1,
            piece.y1,
            piece.x2,
            piece.y2,
        )

        assert passage_polygon.covers(piece_polygon)


def test_connection_without_passage_returns_empty_preview() -> None:
    connection = RoomConnection(
        connection_id="living_kitchen",
        room_a="living",
        room_b="kitchen",
        connection_type="threshold",
        opening=Opening(
            x1=2000.0,
            y1=4000.0,
            x2=3000.0,
            y2=4000.0,
        ),
        align_rows=True,
        align_joints=False,
        weight=5.0,
        passage=None,
        cut=None,
    )

    room = {
        "id": "living",
        "origin": {
            "x": 0,
            "y": 0,
        },
        "rectangles": [
            {
                "x": 0,
                "y": 0,
                "width": 5000,
                "height": 4000,
            }
        ],
    }

    pieces = create_passage_preview(
        connection=connection,
        master_room=room,
        candidate=make_candidate(),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
    )

    assert pieces == []
