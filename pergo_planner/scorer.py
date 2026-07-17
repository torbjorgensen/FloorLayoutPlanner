from __future__ import annotations

from shapely.geometry import Polygon

from .planner import Piece, create_row_fragments


def _row_joint_positions(
    pieces: list[Piece],
    orientation: str,
) -> dict[int, list[float]]:
    rows: dict[int, dict[int, list[Piece]]] = {}

    for piece in pieces:
        rows.setdefault(piece.row, {}).setdefault(piece.segment, []).append(piece)

    result: dict[int, list[float]] = {}

    for row_number, segments in rows.items():
        joints: list[float] = []

        for segment_pieces in segments.values():
            if orientation == "horizontal":
                ordered = sorted(
                    segment_pieces,
                    key=lambda item: item.x1,
                )
                joints.extend(piece.x2 for piece in ordered[:-1])
            else:
                ordered = sorted(
                    segment_pieces,
                    key=lambda item: item.y1,
                )
                joints.extend(piece.y2 for piece in ordered[:-1])

        result[row_number] = joints

    return result


def count_joint_violations(
    pieces: list[Piece],
    orientation: str,
    minimum_joint_distance: float,
) -> int:
    if minimum_joint_distance <= 0:
        return 0

    joints = _row_joint_positions(pieces, orientation)
    violations = 0

    for row_number in sorted(joints):
        following = row_number + 1

        if following not in joints:
            continue

        for first in joints[row_number]:
            if any(
                abs(first - second) < minimum_joint_distance
                for second in joints[following]
            ):
                violations += 1

    return violations


def row_width_statistics(
    *,
    floor: Polygon,
    board_width: float,
    orientation: str,
    row_width_offset: float,
    start_corner: str,
    minimum_row_width: float,
    preferred_minimum_row_width: float,
) -> tuple[int, int, float]:
    fragments = create_row_fragments(
        floor=floor,
        board_width=board_width,
        orientation=orientation,
        row_width_offset=row_width_offset,
        start_corner=start_corner,
    )

    if not fragments:
        return 0, 0, 0.0

    widths = [fragment.width for fragment in fragments]

    very_narrow = sum(width < minimum_row_width for width in widths)
    narrow = sum(width < preferred_minimum_row_width for width in widths)

    return narrow, very_narrow, min(widths)


def evaluate_pieces(
    pieces: list[Piece],
    minimum_piece_length: float,
    orientation: str,
    minimum_joint_distance: float,
    minimum_row_width: float,
    preferred_minimum_row_width: float,
    floor: Polygon,
    board_width: float,
    row_width_offset: float,
    start_corner: str = "upper_left",
) -> tuple:
    if not pieces:
        return (
            0,
            0,
            0.0,
            10**9,
            10**9,
            10**9,
            0.0,
            (10**9, 10**9, 10**9, 10**9, 10**9, 0.0, 0.0),
        )

    short_count = sum(piece.length < minimum_piece_length for piece in pieces)
    very_short_limit = min(100.0, minimum_piece_length)
    very_short_count = sum(piece.length < very_short_limit for piece in pieces)
    shortest_piece = min(piece.length for piece in pieces)

    joint_violations = count_joint_violations(
        pieces,
        orientation,
        minimum_joint_distance,
    )

    (
        narrow_count,
        very_narrow_count,
        narrowest_width,
    ) = row_width_statistics(
        floor=floor,
        board_width=board_width,
        orientation=orientation,
        row_width_offset=row_width_offset,
        start_corner=start_corner,
        minimum_row_width=minimum_row_width,
        preferred_minimum_row_width=preferred_minimum_row_width,
    )

    score = (
        joint_violations,
        very_narrow_count,
        very_short_count,
        narrow_count,
        short_count,
        -narrowest_width,
        -shortest_piece,
    )

    return (
        short_count,
        very_short_count,
        shortest_piece,
        joint_violations,
        narrow_count,
        very_narrow_count,
        narrowest_width,
        score,
    )
