from __future__ import annotations

import pytest
from shapely.geometry import box
from shapely.ops import unary_union

from pergo_planner.geometry import build_floor_polygon
from pergo_planner.planner import create_plan, create_row_fragments


def pieces_union(pieces):
    return unary_union(
        [box(piece.x1, piece.y1, piece.x2, piece.y2) for piece in pieces]
    )


def test_exact_board_sized_room_produces_one_piece() -> None:
    floor = build_floor_polygon(
        [{"x": 0, "y": 0, "width": 2050, "height": 240}],
        expansion_gap=0,
    )

    pieces = create_plan(
        floor=floor,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
    )

    assert len(pieces) == 1
    assert pieces[0].length == pytest.approx(2050)
    assert pieces[0].width == pytest.approx(240)
    assert pieces[0].is_full_length


def test_all_piece_dimensions_are_positive(l_floor) -> None:
    pieces = create_plan(
        floor=l_floor,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
    )

    assert pieces
    assert all(piece.length > 0 for piece in pieces)
    assert all(piece.width > 0 for piece in pieces)


def test_l_shape_is_completely_covered(l_floor) -> None:
    pieces = create_plan(
        floor=l_floor,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        row_width_offset=35,
    )

    covered = pieces_union(pieces)

    assert covered.symmetric_difference(l_floor).area == pytest.approx(
        0,
        abs=1e-4,
    )


def test_wall_break_inside_board_row_creates_local_fragments() -> None:
    floor = build_floor_polygon(
        [
            {"x": 0, "y": 0, "width": 2000, "height": 1000},
            {"x": 2000, "y": 350, "width": 1000, "height": 300},
        ],
        expansion_gap=0,
    )

    fragments = create_row_fragments(
        floor=floor,
        board_width=240,
        orientation="horizontal",
        row_width_offset=100,
    )
    pieces = create_plan(
        floor=floor,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        row_width_offset=100,
    )

    assert any(fragment.width < 240 for fragment in fragments)
    assert pieces_union(pieces).symmetric_difference(floor).area == pytest.approx(
        0,
        abs=1e-4,
    )


def test_vertical_orientation_covers_same_floor(l_floor) -> None:
    pieces = create_plan(
        floor=l_floor,
        board_length=2050,
        board_width=240,
        orientation="vertical",
        stagger_step=700,
        minimum_piece_length=300,
        row_width_offset=25,
    )

    assert pieces_union(pieces).symmetric_difference(l_floor).area == pytest.approx(
        0,
        abs=1e-4,
    )


def test_invalid_orientation_is_rejected(l_floor) -> None:
    with pytest.raises(ValueError, match="orientation"):
        create_plan(
            floor=l_floor,
            board_length=2050,
            board_width=240,
            orientation="diagonal",
            stagger_step=700,
            minimum_piece_length=300,
        )
