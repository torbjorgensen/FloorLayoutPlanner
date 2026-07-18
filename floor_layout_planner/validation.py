from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from floor_layout_planner.models import Candidate, CutPlan
    from floor_layout_planner.planner import Piece


_LENGTH_EPSILON_MM = 1e-6


class InfeasibleLayoutError(ValueError):
    """Raised when optimization cannot produce an installable layout."""


def length_meets_minimum(length: float, minimum_length: float) -> bool:
    return length + _LENGTH_EPSILON_MM >= minimum_length


def piece_meets_minimum_length(piece: Piece, minimum_length: float) -> bool:
    return length_meets_minimum(piece.length, minimum_length)


def candidate_meets_minimum_length(
    candidate: Candidate,
    minimum_length: float,
) -> bool:
    return bool(candidate.pieces) and all(
        piece_meets_minimum_length(piece, minimum_length) for piece in candidate.pieces
    )


def candidate_meets_installation_minimums(
    candidate: Candidate,
    minimum_length: float,
) -> bool:
    """Return whether both piece length and absolute row-width limits hold."""
    return (
        candidate_meets_minimum_length(candidate, minimum_length)
        and candidate.very_narrow_row_count == 0
    )


def cut_plan_meets_minimum_length(cut_plan: CutPlan) -> bool:
    return cut_plan.short_fragments == 0


def split_pieces_meet_minimum_lengths(
    room_pieces: dict[str, list[Piece]],
    minimum_lengths: dict[str, float],
) -> bool:
    return all(
        pieces
        and all(
            piece_meets_minimum_length(piece, minimum_lengths[room_id])
            for piece in pieces
        )
        for room_id, pieces in room_pieces.items()
    ) and set(room_pieces) == set(minimum_lengths)


def select_best_valid_candidate(
    candidates: Iterable[Candidate],
    minimum_length: float,
) -> Candidate:
    valid = [
        candidate
        for candidate in candidates
        if candidate_meets_installation_minimums(candidate, minimum_length)
    ]
    if not valid:
        raise InfeasibleLayoutError(
            "No valid layout satisfies the minimum piece length and "
            "absolute minimum row width. Try a finer row-width search step, the "
            "other laying direction, or adjust the room geometry."
        )
    return min(valid, key=lambda candidate: candidate.score)
