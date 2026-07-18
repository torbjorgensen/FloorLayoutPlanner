from __future__ import annotations

from dataclasses import replace

import pytest
from shapely.geometry import box

from floor_layout_planner.models import Candidate, CutPlan
from floor_layout_planner.planner import Piece
from floor_layout_planner.scorer import evaluate_pieces
from floor_layout_planner.validation import (
    InfeasibleLayoutError,
    candidate_meets_installation_minimums,
    candidate_meets_minimum_length,
    cut_plan_meets_minimum_length,
    select_best_valid_candidate,
    split_pieces_meet_minimum_lengths,
)


def piece(length: float, piece_number: int = 1) -> Piece:
    return Piece(
        row=1,
        segment=1,
        piece=piece_number,
        x1=0,
        x2=length,
        y1=0,
        y2=200,
        length=length,
        width=200,
        source_board_index=piece_number,
        physical_board_id=f"B{piece_number:05d}",
        is_full_length=False,
    )


def candidate(length: float, score: tuple = (0,)) -> Candidate:
    return Candidate(
        attempt=1,
        total_attempts=1,
        phase="refine",
        base_offset=0,
        row_width_offset=0,
        pieces=[piece(length)],
        short_count=int(length < 300),
        very_short_count=0,
        shortest_piece=length,
        joint_violations=0,
        narrow_row_count=0,
        very_narrow_row_count=0,
        narrowest_row_width=200,
        row_offsets={},
        score=score,
        timings={},
    )


def cut_plan(short_fragments: int) -> CutPlan:
    return CutPlan(
        connection_id="rooms",
        axis="x",
        position_mm=1000,
        gap_width_mm=5,
        method="saw_cut",
        cut_boards=1,
        short_fragments=short_fragments,
        very_short_fragments=0,
        narrow_fragments=0,
        very_narrow_fragments=0,
        shortest_fragment_mm=300 if not short_fragments else 299,
        narrowest_fragment_mm=200,
        center_distance_mm=0,
        score=(0,),
    )


def test_minimum_length_boundary_is_valid() -> None:
    assert candidate_meets_minimum_length(candidate(300), 300)
    assert candidate_meets_minimum_length(candidate(300 - 1e-7), 300)
    assert not candidate_meets_minimum_length(candidate(299.99), 300)


def test_absolute_minimum_row_width_is_a_hard_constraint() -> None:
    too_narrow = replace(candidate(300), very_narrow_row_count=1)

    assert not candidate_meets_installation_minimums(too_narrow, 300)
    with pytest.raises(InfeasibleLayoutError, match="absolute minimum row width"):
        select_best_valid_candidate([too_narrow], 300)


def test_selection_excludes_better_scoring_invalid_candidate() -> None:
    invalid = candidate(250, score=(0,))
    valid = candidate(350, score=(10,))

    assert select_best_valid_candidate([invalid, valid], 300) is valid


def test_candidate_score_ranks_minimum_length_as_hard_constraint() -> None:
    floor = box(0, 0, 1000, 200)

    def score_for(length: float):
        *_, score = evaluate_pieces(
            [piece(length)],
            minimum_piece_length=300,
            orientation="horizontal",
            minimum_joint_distance=300,
            minimum_row_width=60,
            preferred_minimum_row_width=100,
            floor=floor,
            board_width=200,
            row_width_offset=0,
        )
        return score

    assert score_for(300)[0] == 0
    assert score_for(299)[0] == 1


def test_candidate_score_prioritizes_acceptable_row_widths() -> None:
    floor = box(0, 0, 1000, 250)

    *_, narrow_score = evaluate_pieces(
        [piece(1000)],
        minimum_piece_length=300,
        orientation="horizontal",
        minimum_joint_distance=300,
        minimum_row_width=60,
        preferred_minimum_row_width=100,
        floor=floor,
        board_width=200,
        row_width_offset=0,
    )
    *_, balanced_score = evaluate_pieces(
        [piece(1000)],
        minimum_piece_length=300,
        orientation="horizontal",
        minimum_joint_distance=300,
        minimum_row_width=60,
        preferred_minimum_row_width=100,
        floor=floor,
        board_width=200,
        row_width_offset=75,
    )

    assert narrow_score[2:4] == (1, 1)
    assert balanced_score[2:4] == (0, 0)
    assert balanced_score < narrow_score


def test_selection_reports_infeasible_layout() -> None:
    with pytest.raises(InfeasibleLayoutError, match="minimum piece length"):
        select_best_valid_candidate([candidate(250)], 300)


def test_cut_plan_requires_every_fragment_to_meet_minimum() -> None:
    assert cut_plan_meets_minimum_length(cut_plan(0))
    assert not cut_plan_meets_minimum_length(cut_plan(1))


def test_final_room_split_revalidates_pieces_shown_in_ui() -> None:
    minimums = {"room_a": 300, "room_b": 250}

    assert split_pieces_meet_minimum_lengths(
        {"room_a": [piece(300)], "room_b": [piece(250)]},
        minimums,
    )
    assert not split_pieces_meet_minimum_lengths(
        {"room_a": [piece(299)], "room_b": [piece(250)]},
        minimums,
    )
    assert not split_pieces_meet_minimum_lengths(
        {"room_a": [piece(300)]},
        minimums,
    )


def test_validation_uses_geometry_not_stale_candidate_counts() -> None:
    stale = replace(candidate(250), short_count=0)

    assert not candidate_meets_minimum_length(stale, 300)
