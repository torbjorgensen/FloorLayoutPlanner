from __future__ import annotations

from dataclasses import replace

from pergo_planner.optimizer import (
    CandidateInput,
    build_candidate_inputs,
    evaluate_candidate_fast,
)


def candidate_input(floor) -> CandidateInput:
    return CandidateInput(
        attempt=1,
        total_attempts=1,
        floor_wkb=floor.wkb,
        board_length=2050,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        minimum_joint_distance=300,
        minimum_row_width=60,
        preferred_minimum_row_width=100,
        optimization_step=200,
        base_offset=0,
        row_width_offset=0,
    )


def test_fast_optimizer_returns_candidate(l_floor) -> None:
    candidate = evaluate_candidate_fast(candidate_input(l_floor))

    assert candidate.phase == "coarse"
    assert candidate.pieces
    assert candidate.total_attempts == 1
    assert candidate.score
    assert candidate.shortest_piece > 0
    assert candidate.narrowest_row_width > 0


def test_candidate_grid_count(l_floor) -> None:
    inputs = build_candidate_inputs(
        floor=l_floor,
        board_length=2000,
        board_width=240,
        orientation="horizontal",
        stagger_step=700,
        minimum_piece_length=300,
        minimum_joint_distance=300,
        minimum_row_width=60,
        preferred_minimum_row_width=100,
        optimization_step=500,
        row_width_optimization_step=60,
    )

    assert len(inputs) == 16
    assert {item.total_attempts for item in inputs} == {16}
    assert [item.attempt for item in inputs] == list(range(1, 17))


def test_row_width_offset_is_reflected_in_candidate(l_floor) -> None:
    data = replace(
        candidate_input(l_floor),
        row_width_offset=75,
    )

    candidate = evaluate_candidate_fast(data)

    assert candidate.row_width_offset == 75
