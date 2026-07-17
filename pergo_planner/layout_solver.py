from __future__ import annotations

from shapely.geometry import Polygon

from .planner import Piece, create_plan
from .scorer import evaluate_pieces
from .validation import piece_meets_minimum_length


def _problem_rows(
    pieces: list[Piece],
    minimum_piece_length: float,
) -> list[int]:
    """Return rows containing pieces shorter than the configured minimum."""
    return sorted(
        {
            piece.row
            for piece in pieces
            if not piece_meets_minimum_length(piece, minimum_piece_length)
        }
    )


def improve_problem_rows(
    *,
    floor: Polygon,
    board_length: float,
    board_width: float,
    orientation: str,
    start_corner: str,
    stagger_step: float,
    minimum_piece_length: float,
    minimum_joint_distance: float,
    minimum_row_width: float,
    preferred_minimum_row_width: float,
    optimization_step: float,
    base_offset: float,
    row_width_offset: float,
    initial_pieces: list[Piece],
) -> tuple[list[Piece], dict[int, float], tuple, int]:
    """Improve rows containing short pieces by testing local row offsets."""
    row_offsets: dict[int, float] = {}
    best_pieces = initial_pieces
    tested_variants = 0

    *_, best_score = evaluate_pieces(
        best_pieces,
        minimum_piece_length,
        orientation,
        minimum_joint_distance,
        minimum_row_width,
        preferred_minimum_row_width,
        floor,
        board_width,
        row_width_offset,
        start_corner,
    )

    # Run a second pass because changing one row can affect its neighbours.
    for _pass in range(2):
        rows = _problem_rows(
            best_pieces,
            minimum_piece_length,
        )

        if not rows:
            break

        changed = False

        for row_number in rows:
            row_best_pieces = best_pieces
            row_best_score = best_score
            row_best_offset = row_offsets.get(row_number)

            offset = 0.0

            while offset < board_length:
                tested_variants += 1

                trial_offsets = dict(row_offsets)
                trial_offsets[row_number] = offset

                trial_pieces = create_plan(
                    floor=floor,
                    board_length=board_length,
                    board_width=board_width,
                    orientation=orientation,
                    start_corner=start_corner,
                    stagger_step=stagger_step,
                    minimum_piece_length=minimum_piece_length,
                    base_offset=base_offset,
                    row_offsets=trial_offsets,
                    row_width_offset=row_width_offset,
                )

                *_, trial_score = evaluate_pieces(
                    trial_pieces,
                    minimum_piece_length,
                    orientation,
                    minimum_joint_distance,
                    minimum_row_width,
                    preferred_minimum_row_width,
                    floor,
                    board_width,
                    row_width_offset,
                    start_corner,
                )

                if trial_score < row_best_score:
                    row_best_score = trial_score
                    row_best_pieces = trial_pieces
                    row_best_offset = offset

                offset += optimization_step

            if row_best_score < best_score and row_best_offset is not None:
                row_offsets[row_number] = row_best_offset
                best_pieces = row_best_pieces
                best_score = row_best_score
                changed = True

        if not changed:
            break

    return (
        best_pieces,
        row_offsets,
        best_score,
        tested_variants,
    )
