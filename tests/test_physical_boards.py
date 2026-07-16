from __future__ import annotations

from collections import Counter

from shapely.geometry import box

from pergo_planner.planner import create_plan


def test_physical_board_id_is_unique_per_unsplit_piece() -> None:
    pieces = create_plan(
        floor=box(0, 0, 4300, 480),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
    )

    ids = [piece.physical_board_id for piece in pieces]

    assert ids
    assert all(ids)
    assert len(ids) == len(set(ids))


def test_same_grid_index_in_different_rows_is_not_same_physical_board() -> None:
    pieces = create_plan(
        floor=box(0, 0, 2050, 480),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=0,
        minimum_piece_length=300,
    )

    by_grid_index: dict[int, set[str]] = {}

    for piece in pieces:
        by_grid_index.setdefault(
            piece.source_board_index,
            set(),
        ).add(piece.physical_board_id)

    assert any(len(board_ids) > 1 for board_ids in by_grid_index.values())


def test_one_physical_board_has_only_one_piece_before_transition_cut() -> None:
    pieces = create_plan(
        floor=box(0, 0, 4300, 720),
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
    )

    counts = Counter(piece.physical_board_id for piece in pieces)

    assert max(counts.values()) == 1
