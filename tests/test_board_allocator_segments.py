from __future__ import annotations

from collections import Counter

from pergo_planner.board_allocator import (
    assign_physical_boards,
)
from pergo_planner.planner import Piece

SAW_KERF_MM = 3.2


def make_piece(
    *,
    row: int,
    segment: int,
    piece_number: int,
    x1: float,
    x2: float,
    length: float,
    y1: float,
    y2: float,
    full: bool = False,
) -> Piece:
    return Piece(
        row=row,
        segment=segment,
        piece=piece_number,
        x1=x1,
        x2=x2,
        y1=y1,
        y2=y2,
        length=length,
        width=y2 - y1,
        source_board_index=piece_number,
        physical_board_id="temporary",
        is_full_length=full,
    )


def test_complementary_cut_highlights_both_parts() -> None:
    pieces = [
        make_piece(
            row=1,
            segment=1,
            piece_number=1,
            x1=0,
            x2=1500,
            length=1500,
            y1=0,
            y2=240,
        ),
        make_piece(
            row=2,
            segment=1,
            piece_number=1,
            x1=0,
            x2=546.8,
            length=546.8,
            y1=240,
            y2=480,
        ),
    ]

    allocated = assign_physical_boards(
        pieces,
        board_length=2050,
        orientation="horizontal",
        saw_kerf_mm=SAW_KERF_MM,
    )

    assert allocated[0].physical_board_id == allocated[1].physical_board_id


def test_rows_with_different_lengths_can_share_offcut() -> None:
    pieces = [
        make_piece(
            row=1,
            segment=1,
            piece_number=1,
            x1=0,
            x2=1500,
            length=1500,
            y1=0,
            y2=240,
        ),
        make_piece(
            row=2,
            segment=1,
            piece_number=1,
            x1=0,
            x2=546.8,
            length=546.8,
            y1=240,
            y2=480,
        ),
        make_piece(
            row=2,
            segment=1,
            piece_number=2,
            x1=546.8,
            x2=3046.8,
            length=2500,
            y1=240,
            y2=480,
        ),
    ]

    allocated = assign_physical_boards(
        pieces,
        board_length=2050,
        orientation="horizontal",
        saw_kerf_mm=SAW_KERF_MM,
    )

    assert allocated[0].physical_board_id == allocated[1].physical_board_id


def test_offcut_is_not_reused_across_shifted_wall_segment() -> None:
    pieces = [
        make_piece(
            row=1,
            segment=1,
            piece_number=1,
            x1=0,
            x2=1500,
            length=1500,
            y1=0,
            y2=240,
        ),
        make_piece(
            row=2,
            segment=2,
            piece_number=1,
            x1=2000,
            x2=2546.8,
            length=546.8,
            y1=240,
            y2=480,
        ),
    ]

    allocated = assign_physical_boards(
        pieces,
        board_length=2050,
        orientation="horizontal",
        saw_kerf_mm=SAW_KERF_MM,
    )

    assert allocated[0].physical_board_id != allocated[1].physical_board_id


def test_ambiguous_matching_segments_do_not_share_offcut() -> None:
    pieces = [
        make_piece(
            row=1,
            segment=1,
            piece_number=1,
            x1=0,
            x2=1500,
            length=1500,
            y1=0,
            y2=120,
        ),
        make_piece(
            row=1,
            segment=2,
            piece_number=1,
            x1=0,
            x2=1500,
            length=1500,
            y1=120,
            y2=240,
        ),
        make_piece(
            row=2,
            segment=1,
            piece_number=1,
            x1=0,
            x2=546.8,
            length=546.8,
            y1=240,
            y2=360,
        ),
    ]

    allocated = assign_physical_boards(
        pieces,
        board_length=2050,
        orientation="horizontal",
        saw_kerf_mm=SAW_KERF_MM,
    )

    assert allocated[2].physical_board_id not in {
        allocated[0].physical_board_id,
        allocated[1].physical_board_id,
    }


def test_one_board_has_at_most_two_visible_fragments() -> None:
    pieces = [
        make_piece(
            row=1,
            segment=1,
            piece_number=1,
            x1=0,
            x2=1500,
            length=1500,
            y1=0,
            y2=240,
        ),
        make_piece(
            row=2,
            segment=1,
            piece_number=1,
            x1=0,
            x2=546.8,
            length=546.8,
            y1=240,
            y2=480,
        ),
        make_piece(
            row=2,
            segment=1,
            piece_number=2,
            x1=546.8,
            x2=2596.8,
            length=2050,
            y1=240,
            y2=480,
            full=True,
        ),
    ]

    allocated = assign_physical_boards(
        pieces,
        board_length=2050,
        orientation="horizontal",
        saw_kerf_mm=SAW_KERF_MM,
    )
    counts = Counter(piece.physical_board_id for piece in allocated)

    assert max(counts.values()) <= 2
