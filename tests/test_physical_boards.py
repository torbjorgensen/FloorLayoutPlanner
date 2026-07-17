from __future__ import annotations

from collections import Counter, defaultdict

import pytest
from shapely.geometry import box

from floor_layout_planner.planner import create_plan

SAW_KERF_MM = 3.2


def group_by_board(pieces):
    grouped = defaultdict(list)

    for piece in pieces:
        grouped[piece.physical_board_id].append(piece)

    return grouped


def test_physical_board_ids_are_present() -> None:
    pieces = create_plan(
        floor=box(0, 0, 4300, 480),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        saw_kerf_mm=SAW_KERF_MM,
    )

    assert pieces
    assert all(piece.physical_board_id for piece in pieces)


def test_cut_board_can_have_two_visible_placements() -> None:
    pieces = create_plan(
        floor=box(0, 0, 3550, 480),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        saw_kerf_mm=SAW_KERF_MM,
    )
    grouped = group_by_board(pieces)

    reused = [
        fragments
        for fragments in grouped.values()
        if len({piece.row for piece in fragments}) == 2
    ]

    assert reused

    fragments = reused[0]

    assert len(fragments) == 2
    assert sum(piece.length for piece in fragments) + SAW_KERF_MM == pytest.approx(2050)


def test_same_grid_position_may_be_same_physical_board_after_reuse() -> None:
    pieces = create_plan(
        floor=box(0, 0, 3550, 480),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        saw_kerf_mm=SAW_KERF_MM,
    )
    grouped = group_by_board(pieces)

    assert any(
        len({piece.row for piece in fragments}) == 2 for fragments in grouped.values()
    )


def test_physical_board_has_at_most_two_cross_cut_placements() -> None:
    pieces = create_plan(
        floor=box(0, 0, 4300, 720),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        saw_kerf_mm=SAW_KERF_MM,
    )

    rows_per_board = {
        board_id: {piece.row for piece in fragments}
        for board_id, fragments in group_by_board(pieces).items()
    }

    assert max(len(rows) for rows in rows_per_board.values()) <= 2


def test_no_physical_board_is_reused_in_three_rows() -> None:
    pieces = create_plan(
        floor=box(0, 0, 6000, 1200),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        saw_kerf_mm=SAW_KERF_MM,
    )
    counts = Counter(
        (
            piece.physical_board_id,
            piece.row,
        )
        for piece in pieces
    )
    rows_by_board = defaultdict(set)

    for board_id, row in counts:
        rows_by_board[board_id].add(row)

    assert all(len(rows) <= 2 for rows in rows_by_board.values())


def test_hallway_reuses_offcuts_across_rows(
    stue_project_config,
    hallway_floor,
    hallway_settings,
) -> None:
    board = stue_project_config["board"]
    pieces = create_plan(
        floor=hallway_floor,
        board_length=float(board["length_mm"]),
        board_width=float(board["width_mm"]),
        orientation=hallway_settings["orientation"],
        stagger_step=float(hallway_settings["stagger_step_mm"]),
        minimum_piece_length=float(hallway_settings["minimum_piece_length_mm"]),
        saw_kerf_mm=SAW_KERF_MM,
    )
    grouped = group_by_board(pieces)

    reused = [
        fragments
        for fragments in grouped.values()
        if len({piece.row for piece in fragments}) == 2
    ]

    assert reused


def test_hallway_does_not_reuse_one_physical_board_in_three_rows(
    stue_project_config,
    hallway_floor,
    hallway_settings,
) -> None:
    board = stue_project_config["board"]
    pieces = create_plan(
        floor=hallway_floor,
        board_length=float(board["length_mm"]),
        board_width=float(board["width_mm"]),
        orientation=hallway_settings["orientation"],
        stagger_step=float(hallway_settings["stagger_step_mm"]),
        minimum_piece_length=float(hallway_settings["minimum_piece_length_mm"]),
        saw_kerf_mm=SAW_KERF_MM,
    )
    grouped = group_by_board(pieces)
    rows_per_board = {
        board_id: {piece.row for piece in fragments}
        for board_id, fragments in grouped.items()
    }

    assert all(len(rows) <= 2 for rows in rows_per_board.values())
