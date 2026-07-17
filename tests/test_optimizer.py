from __future__ import annotations

import threading
from dataclasses import replace

from pergo_planner.models import (
    CandidateInput,
    CutSettings,
    Opening,
    Passage,
    RoomConnection,
)
from pergo_planner.optimizer import (
    ProcessBudget,
    build_candidate_inputs,
    continuous_inputs,
    evaluate_candidate_fast,
    parallel_continuous_coarse_generator,
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
        saw_kerf_mm=3.2,
        base_offset=0,
        row_width_offset=0,
    )


def test_fast_optimizer_returns_candidate(l_floor) -> None:
    candidate = evaluate_candidate_fast(candidate_input(l_floor))

    assert candidate.phase == "coarse"
    assert candidate.pieces
    assert candidate.total_attempts == 1
    assert candidate.score
    assert candidate.material_metrics["new_boards"] > 0
    assert candidate.score[-4] == candidate.material_metrics["new_boards"]
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
    assert {item.saw_kerf_mm for item in inputs} == {3.2}
    assert {item.total_attempts for item in inputs} == {16}
    assert [item.attempt for item in inputs] == list(range(1, 17))


def test_row_width_offset_is_reflected_in_candidate(l_floor) -> None:
    data = replace(
        candidate_input(l_floor),
        row_width_offset=75,
    )

    candidate = evaluate_candidate_fast(data)

    assert candidate.row_width_offset == 75


def test_process_budget_prevents_concurrent_pool_oversubscription() -> None:
    budget = ProcessBudget(capacity=2)
    first_acquired = threading.Event()
    release_first = threading.Event()
    second_acquired = threading.Event()
    grants: list[int] = []

    def first_job() -> None:
        with budget.lease(2) as granted:
            grants.append(granted)
            first_acquired.set()
            release_first.wait(timeout=1)

    def second_job() -> None:
        first_acquired.wait(timeout=1)
        with budget.lease(2) as granted:
            grants.append(granted)
            second_acquired.set()

    first = threading.Thread(target=first_job)
    second = threading.Thread(target=second_job)
    first.start()
    second.start()

    assert first_acquired.wait(timeout=1)
    assert not second_acquired.wait(timeout=0.05)
    release_first.set()
    first.join(timeout=1)
    second.join(timeout=1)

    assert second_acquired.is_set()
    assert grants == [2, 2]
    assert budget.available == budget.capacity


def test_continuous_generation_and_scoring_run_in_worker_processes(l_floor) -> None:
    inputs = [
        candidate_input(l_floor),
        replace(candidate_input(l_floor), attempt=2, base_offset=200),
    ]
    connection = RoomConnection(
        connection_id="test_transition",
        room_a="a",
        room_b="b",
        connection_type="continuous_then_cut",
        opening=Opening(0, 900, 1000, 900),
        passage=Passage(0, 900, 1000, 200),
        cut=CutSettings(axis="y", search_step_mm=50),
    )
    tasks = continuous_inputs(
        inputs,
        connection=connection,
        orientation="horizontal",
        minimum_piece_length=300,
        minimum_row_width=60,
        preferred_minimum_row_width=100,
    )

    results = list(parallel_continuous_coarse_generator(inputs=tasks, workers=2))

    assert {result.candidate.attempt for result in results} == {1, 2}
    assert all(result.cut_plan.connection_id == "test_transition" for result in results)
    assert all(result.score for result in results)
