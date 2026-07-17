from __future__ import annotations

from dataclasses import replace
from itertools import count

from .planner import Piece

_LENGTH_TOLERANCE_MM = 1.0
_WIDTH_TOLERANCE_MM = 1.0
_LANE_TOLERANCE_MM = 1.0
_DEFAULT_SAW_KERF_MM = 3.2


def _piece_sort_key(
    piece: Piece,
    orientation: str,
) -> tuple[float, float, int]:
    if orientation == "horizontal":
        return piece.x1, piece.y1, piece.piece

    return piece.y1, piece.x1, piece.piece


def _group_start(
    pieces: list[Piece],
    orientation: str,
) -> float:
    if orientation == "horizontal":
        return min(piece.x1 for piece in pieces)

    return min(piece.y1 for piece in pieces)


def _same_laying_lane(
    previous_group: list[Piece],
    current_group: list[Piece],
    orientation: str,
) -> bool:
    """
    Match only rows that start at the same physical wall/edge.

    The full row lengths are allowed to differ. That is normal in an L-shaped
    room and must not prevent an end offcut from starting the next row.

    A shifted start position means a different lane behind a wall, indentation
    or other geometry break, so the offcut must not be linked automatically.
    """
    return (
        abs(
            _group_start(previous_group, orientation)
            - _group_start(current_group, orientation)
        )
        <= _LANE_TOLERANCE_MM
    )


def _can_reuse_offcut(
    previous_end: Piece,
    current_start: Piece,
    board_length: float,
    saw_kerf_mm: float,
) -> bool:
    """
    Check whether one transverse cut created exactly these two fragments.

    The saw blade consumes ``saw_kerf_mm``. Therefore:

        installed end piece + next-row starter + saw kerf = full board

    A different sum would require another transverse cut and is rejected.
    """
    if previous_end.is_full_length or current_start.is_full_length:
        return False

    if abs(previous_end.width - current_start.width) > _WIDTH_TOLERANCE_MM:
        return False

    return (
        abs(previous_end.length + current_start.length + saw_kerf_mm - board_length)
        <= _LENGTH_TOLERANCE_MM
    )


def _segment_groups(
    pieces: list[Piece],
    orientation: str,
) -> dict[int, dict[int, list[tuple[int, Piece]]]]:
    rows: dict[int, dict[int, list[tuple[int, Piece]]]] = {}

    for index, piece in enumerate(pieces):
        rows.setdefault(
            piece.row,
            {},
        ).setdefault(
            piece.segment,
            [],
        ).append((index, piece))

    for row_segments in rows.values():
        for indexed_group in row_segments.values():
            indexed_group.sort(
                key=lambda item: _piece_sort_key(
                    item[1],
                    orientation,
                )
            )

    return rows


def assign_physical_boards(
    pieces: list[Piece],
    *,
    board_length: float,
    orientation: str,
    id_prefix: str = "B",
    saw_kerf_mm: float = _DEFAULT_SAW_KERF_MM,
) -> list[Piece]:
    """
    Assign physical-board IDs in realistic laying order.

    Rules:

    * each ``(row, segment)`` is an independent laying sequence;
    * the final cut in one row may start the next consecutive row;
    * the next row must start at the same physical wall/edge;
    * the two fragment lengths plus saw kerf must equal one full board;
    * one previous offcut can be consumed only once;
    * no free reuse across rooms or unrelated wall segments is performed.

    IDs are local to the allocation call. The UI scopes ordinary IDs by room
    and continuous-layout IDs by connection.
    """
    if orientation not in {"horizontal", "vertical"}:
        raise ValueError("orientation must be 'horizontal' or 'vertical'.")

    if board_length <= 0:
        raise ValueError("board_length must be greater than 0.")

    if saw_kerf_mm < 0:
        raise ValueError("saw_kerf_mm cannot be negative.")

    if saw_kerf_mm >= board_length:
        raise ValueError("saw_kerf_mm must be less than board_length.")

    if not pieces:
        return []

    board_numbers = count(1)
    board_ids: dict[int, str] = {}
    rows = _segment_groups(
        pieces,
        orientation,
    )

    previous_row_number: int | None = None
    previous_groups: dict[
        int,
        list[tuple[int, Piece]],
    ] = {}

    for row_number in sorted(rows):
        current_groups = rows[row_number]
        used_previous_segments: set[int] = set()

        for segment_number in sorted(current_groups):
            indexed_group = current_groups[segment_number]
            start_index, start_piece = indexed_group[0]

            if (
                previous_row_number is not None
                and row_number == previous_row_number + 1
            ):
                matching_segments: list[tuple[int, int]] = []

                for (
                    previous_segment,
                    previous_indexed_group,
                ) in previous_groups.items():
                    if previous_segment in used_previous_segments:
                        continue

                    previous_pieces = [piece for _, piece in previous_indexed_group]
                    current_pieces = [piece for _, piece in indexed_group]

                    if not _same_laying_lane(
                        previous_pieces,
                        current_pieces,
                        orientation,
                    ):
                        continue

                    (
                        previous_end_index,
                        previous_end,
                    ) = previous_indexed_group[-1]

                    if _can_reuse_offcut(
                        previous_end,
                        start_piece,
                        board_length,
                        saw_kerf_mm,
                    ):
                        matching_segments.append(
                            (
                                previous_segment,
                                previous_end_index,
                            )
                        )

                # Reuse only when the continuation is unambiguous.
                if len(matching_segments) == 1:
                    (
                        previous_segment,
                        previous_end_index,
                    ) = matching_segments[0]
                    board_ids[start_index] = board_ids[previous_end_index]
                    used_previous_segments.add(previous_segment)

            for index, _piece in indexed_group:
                if index not in board_ids:
                    board_ids[index] = f"{id_prefix}{next(board_numbers):05d}"

        previous_row_number = row_number
        previous_groups = current_groups

    return [
        replace(
            piece,
            physical_board_id=board_ids[index],
        )
        for index, piece in enumerate(pieces)
    ]
