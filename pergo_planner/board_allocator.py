from __future__ import annotations

from dataclasses import replace
from itertools import count

from .planner import Piece

_LENGTH_TOLERANCE_MM = 1.0
_WIDTH_TOLERANCE_MM = 1.0


def _piece_sort_key(
    piece: Piece,
    orientation: str,
) -> tuple[float, float, int, int]:
    if orientation == "horizontal":
        return (
            piece.x1,
            piece.y1,
            piece.segment,
            piece.piece,
        )

    return (
        piece.y1,
        piece.x1,
        piece.segment,
        piece.piece,
    )


def _row_groups(
    pieces: list[Piece],
    orientation: str,
) -> list[tuple[int, list[Piece]]]:
    rows: dict[int, list[Piece]] = {}

    for piece in pieces:
        rows.setdefault(piece.row, []).append(piece)

    return [
        (
            row_number,
            sorted(
                row_pieces,
                key=lambda piece: _piece_sort_key(
                    piece,
                    orientation,
                ),
            ),
        )
        for row_number, row_pieces in sorted(rows.items())
    ]


def _can_reuse_offcut(
    previous_end: Piece,
    current_start: Piece,
    board_length: float,
) -> bool:
    """
    Check whether the end cut from one row is exactly the starter for the next.

    One transverse cut produces exactly two usable lengths. Therefore the two
    fragments must together equal one full board; a shorter starter would
    require a second transverse cut and is intentionally rejected.
    """
    if previous_end.is_full_length or current_start.is_full_length:
        return False

    if abs(previous_end.width - current_start.width) > _WIDTH_TOLERANCE_MM:
        return False

    return (
        abs(previous_end.length + current_start.length - board_length)
        <= _LENGTH_TOLERANCE_MM
    )


def assign_physical_boards(
    pieces: list[Piece],
    *,
    board_length: float,
    orientation: str,
    id_prefix: str = "B",
) -> list[Piece]:
    """
    Assign realistic physical-board IDs in laying order.

    Rules implemented in this first allocator:

    * every full/middle piece consumes one physical board;
    * the cut at the end of a row may start the next row;
    * reuse is allowed only when the two lengths are complementary and have
      the same width;
    * one physical board therefore has one or two visible fragments;
    * no free cross-room/global best-fit reuse is performed.

    For a continuous-then-cut layout this function is run before the expansion
    strip is removed. When the strip later divides a piece, both resulting
    fragments preserve the same physical-board ID.
    """
    if orientation not in {"horizontal", "vertical"}:
        raise ValueError("orientation må være 'horizontal' eller 'vertical'.")

    if board_length <= 0:
        raise ValueError("board_length må være større enn 0.")

    if not pieces:
        return []

    board_numbers = count(1)
    board_ids: dict[int, str] = {}
    previous_row_end_index: int | None = None

    indexed_pieces = list(enumerate(pieces))

    rows: dict[int, list[tuple[int, Piece]]] = {}
    for index, piece in indexed_pieces:
        rows.setdefault(piece.row, []).append((index, piece))

    for _, indexed_row in sorted(rows.items()):
        indexed_row.sort(
            key=lambda item: _piece_sort_key(
                item[1],
                orientation,
            )
        )

        current_start_index, current_start = indexed_row[0]

        if previous_row_end_index is not None:
            previous_end = pieces[previous_row_end_index]

            if _can_reuse_offcut(
                previous_end,
                current_start,
                board_length,
            ):
                board_ids[current_start_index] = board_ids[previous_row_end_index]

        for index, _piece in indexed_row:
            if index not in board_ids:
                board_ids[index] = f"{id_prefix}{next(board_numbers):05d}"

        previous_row_end_index = indexed_row[-1][0]

    return [
        replace(
            piece,
            physical_board_id=board_ids[index],
        )
        for index, piece in indexed_pieces
    ]
