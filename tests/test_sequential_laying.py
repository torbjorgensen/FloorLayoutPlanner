from __future__ import annotations

from collections import defaultdict

import pytest
from shapely.geometry import Polygon, box

from pergo_planner.planner import create_plan

SAW_KERF_MM = 3.2


def pieces_by_row(pieces):
    result = defaultdict(list)

    for piece in pieces:
        result[piece.row].append(piece)

    return result


def test_end_cut_starts_next_row() -> None:
    pieces = create_plan(
        floor=box(0, 0, 3550, 480),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        base_offset=0,
        saw_kerf_mm=SAW_KERF_MM,
    )
    rows = pieces_by_row(pieces)

    row_one_end = max(
        rows[1],
        key=lambda piece: piece.x2,
    )
    row_two_start = min(
        rows[2],
        key=lambda piece: piece.x1,
    )

    assert row_one_end.physical_board_id == row_two_start.physical_board_id
    assert row_one_end.length + row_two_start.length + SAW_KERF_MM == pytest.approx(
        2050
    )


def test_real_wall_gap_creates_two_lanes() -> None:
    # Lower row is continuous. The upper row has a real gap from x=1200
    # to x=1800, representing a wall/open area through the full row width.
    floor = Polygon(
        [
            (0, 0),
            (3000, 0),
            (3000, 480),
            (1800, 480),
            (1800, 240),
            (1200, 240),
            (1200, 480),
            (0, 480),
        ]
    )

    pieces = create_plan(
        floor=floor,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        base_offset=0,
        saw_kerf_mm=SAW_KERF_MM,
    )
    rows = pieces_by_row(pieces)

    for piece in rows[2]:
        assert not (piece.x1 < 1800 and piece.x2 > 1200)


def test_board_never_spans_both_sides_of_real_wall_gap() -> None:
    floor = Polygon(
        [
            (0, 0),
            (3000, 0),
            (3000, 480),
            (1800, 480),
            (1800, 240),
            (1200, 240),
            (1200, 480),
            (0, 480),
        ]
    )

    pieces = create_plan(
        floor=floor,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        base_offset=0,
        saw_kerf_mm=SAW_KERF_MM,
    )
    upper_row = [piece for piece in pieces if piece.row == 2]
    sides_by_board = defaultdict(set)

    for piece in upper_row:
        side = "left" if piece.x2 <= 1200 + 1e-6 else "right"
        sides_by_board[piece.physical_board_id].add(side)

    assert all(len(sides) == 1 for sides in sides_by_board.values())


def test_row_that_gets_longer_can_still_use_previous_offcut() -> None:
    # This is not a wall gap. Both rows start at the same wall, while the
    # second row simply extends farther to the right.
    floor = Polygon(
        [
            (0, 0),
            (1500, 0),
            (1500, 240),
            (2500, 240),
            (2500, 480),
            (0, 480),
        ]
    )

    pieces = create_plan(
        floor=floor,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        base_offset=0,
        saw_kerf_mm=SAW_KERF_MM,
    )
    rows = pieces_by_row(pieces)
    row_one_end = max(
        rows[1],
        key=lambda piece: piece.x2,
    )
    row_two_start = min(
        rows[2],
        key=lambda piece: piece.x1,
    )

    assert row_one_end.physical_board_id == row_two_start.physical_board_id


def test_partial_width_geometry_change_keeps_board_identity() -> None:
    floor = Polygon(
        [
            (0, 0),
            (3000, 0),
            (3000, 120),
            (1500, 120),
            (1500, 240),
            (0, 240),
        ]
    )

    pieces = create_plan(
        floor=floor,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        base_offset=0,
        saw_kerf_mm=SAW_KERF_MM,
    )
    fragments_by_board = defaultdict(list)

    for piece in pieces:
        fragments_by_board[piece.physical_board_id].append(piece)

    assert any(
        len(fragments) > 1 and len({piece.row for piece in fragments}) == 1
        for fragments in fragments_by_board.values()
    )
