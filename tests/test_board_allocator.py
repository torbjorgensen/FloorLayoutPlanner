from __future__ import annotations

from collections import Counter
from dataclasses import replace

from pergo_planner.board_allocator import (
    assign_physical_boards,
)
from pergo_planner.planner import Piece


def piece(
    *,
    row: int,
    piece_number: int,
    x1: float,
    x2: float,
    length: float,
    width: float = 240.0,
    full: bool = False,
) -> Piece:
    return Piece(
        row=row,
        segment=1,
        piece=piece_number,
        x1=x1,
        x2=x2,
        y1=(row - 1) * width,
        y2=row * width,
        length=length,
        width=width,
        source_board_index=piece_number,
        physical_board_id="temporary",
        is_full_length=full,
    )


def test_end_cut_starts_next_row_when_lengths_are_complementary() -> None:
    pieces = [
        piece(
            row=1,
            piece_number=1,
            x1=0,
            x2=2050,
            length=2050,
            full=True,
        ),
        piece(
            row=1,
            piece_number=2,
            x1=2050,
            x2=3550,
            length=1500,
        ),
        piece(
            row=2,
            piece_number=1,
            x1=0,
            x2=550,
            length=550,
        ),
        piece(
            row=2,
            piece_number=2,
            x1=550,
            x2=2600,
            length=2050,
            full=True,
        ),
    ]

    allocated = assign_physical_boards(
        pieces,
        board_length=2050,
        orientation="horizontal",
    )

    assert allocated[1].physical_board_id == allocated[2].physical_board_id


def test_non_complementary_starter_uses_new_board() -> None:
    pieces = [
        piece(
            row=1,
            piece_number=1,
            x1=0,
            x2=1500,
            length=1500,
        ),
        piece(
            row=2,
            piece_number=1,
            x1=0,
            x2=500,
            length=500,
        ),
    ]

    allocated = assign_physical_boards(
        pieces,
        board_length=2050,
        orientation="horizontal",
    )

    assert allocated[0].physical_board_id != allocated[1].physical_board_id


def test_width_mismatch_prevents_offcut_reuse() -> None:
    pieces = [
        piece(
            row=1,
            piece_number=1,
            x1=0,
            x2=1500,
            length=1500,
            width=240,
        ),
        piece(
            row=2,
            piece_number=1,
            x1=0,
            x2=550,
            length=550,
            width=120,
        ),
    ]

    allocated = assign_physical_boards(
        pieces,
        board_length=2050,
        orientation="horizontal",
    )

    assert allocated[0].physical_board_id != allocated[1].physical_board_id


def test_no_physical_board_has_more_than_two_fragments() -> None:
    pieces = [
        piece(
            row=1,
            piece_number=1,
            x1=0,
            x2=1500,
            length=1500,
        ),
        piece(
            row=2,
            piece_number=1,
            x1=0,
            x2=550,
            length=550,
        ),
        piece(
            row=2,
            piece_number=2,
            x1=550,
            x2=1550,
            length=1000,
        ),
        piece(
            row=3,
            piece_number=1,
            x1=0,
            x2=1050,
            length=1050,
        ),
    ]

    allocated = assign_physical_boards(
        pieces,
        board_length=2050,
        orientation="horizontal",
    )

    counts = Counter(item.physical_board_id for item in allocated)

    assert max(counts.values()) <= 2


def test_existing_temporary_ids_are_replaced() -> None:
    pieces = [
        replace(
            piece(
                row=1,
                piece_number=1,
                x1=0,
                x2=2050,
                length=2050,
                full=True,
            ),
            physical_board_id="r1:s1:g0",
        )
    ]

    allocated = assign_physical_boards(
        pieces,
        board_length=2050,
        orientation="horizontal",
    )

    assert allocated[0].physical_board_id == "B00001"
