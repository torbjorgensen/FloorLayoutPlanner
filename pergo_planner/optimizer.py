from __future__ import annotations

import os
import threading
from concurrent.futures import (
    ProcessPoolExecutor,
    as_completed,
)
from contextlib import contextmanager
from multiprocessing import get_context
from typing import Callable, Iterable, TypeVar

from shapely.geometry import Polygon

from .candidate_evaluator import (
    evaluate_candidate_fast,
    evaluate_candidate_full,
)
from .continuous_solver import best_cut_plan, continuous_candidate_score
from .models import (
    Candidate,
    CandidateInput,
    ContinuousCandidateInput,
    ContinuousEvaluation,
)


class ProcessBudget:
    """Share a fixed process allowance across concurrent optimizer pools."""

    def __init__(self, capacity: int | None = None) -> None:
        self.capacity = max(1, int(capacity or os.cpu_count() or 1))
        self.available = self.capacity
        self.condition = threading.Condition()

    @contextmanager
    def lease(self, requested: int):
        with self.condition:
            while self.available == 0:
                self.condition.wait()
            granted = min(max(1, int(requested)), self.available)
            self.available -= granted
        try:
            yield granted
        finally:
            with self.condition:
                self.available += granted
                self.condition.notify_all()


PROCESS_BUDGET = ProcessBudget()
InputT = TypeVar("InputT")
ResultT = TypeVar("ResultT")


def build_candidate_inputs(
    *,
    floor: Polygon,
    board_length: float,
    board_width: float,
    orientation: str,
    stagger_step: float,
    minimum_piece_length: float,
    minimum_joint_distance: float,
    minimum_row_width: float,
    preferred_minimum_row_width: float,
    optimization_step: float,
    row_width_optimization_step: float,
    saw_kerf_mm: float = 3.2,
    start_corner: str = "upper_left",
) -> list[CandidateInput]:
    longitudinal_offsets = []
    value = 0.0

    while value < board_length:
        longitudinal_offsets.append(value)
        value += optimization_step

    transverse_offsets = []
    value = 0.0

    while value < board_width:
        transverse_offsets.append(value)
        value += row_width_optimization_step

    total = len(longitudinal_offsets) * len(transverse_offsets)

    floor_wkb = floor.wkb
    inputs = []
    attempt = 0

    for row_width_offset in transverse_offsets:
        for base_offset in longitudinal_offsets:
            attempt += 1
            inputs.append(
                CandidateInput(
                    attempt=attempt,
                    total_attempts=total,
                    floor_wkb=floor_wkb,
                    board_length=board_length,
                    board_width=board_width,
                    orientation=orientation,
                    stagger_step=stagger_step,
                    minimum_piece_length=minimum_piece_length,
                    minimum_joint_distance=minimum_joint_distance,
                    minimum_row_width=minimum_row_width,
                    preferred_minimum_row_width=preferred_minimum_row_width,
                    optimization_step=optimization_step,
                    saw_kerf_mm=saw_kerf_mm,
                    base_offset=base_offset,
                    row_width_offset=row_width_offset,
                    start_corner=start_corner,
                )
            )

    return inputs


def _parallel_map(
    *,
    inputs: list[InputT],
    workers: int,
    function: Callable[[InputT], ResultT],
) -> Iterable[ResultT]:
    with PROCESS_BUDGET.lease(workers) as max_workers:
        if max_workers == 1:
            for item in inputs:
                yield function(item)
            return

        with ProcessPoolExecutor(
            max_workers=max_workers,
            # Optimizers are started after Flask opens its listening socket. The
            # Linux default "fork" context would copy that descriptor into every
            # worker and keep the port occupied after the web process exits.
            mp_context=get_context("spawn"),
        ) as executor:
            futures = [executor.submit(function, item) for item in inputs]

            for future in as_completed(futures):
                yield future.result()


def _evaluate_continuous_fast(data: ContinuousCandidateInput) -> ContinuousEvaluation:
    candidate = evaluate_candidate_fast(data.candidate_input)
    return _score_continuous_candidate(data, candidate)


def _evaluate_continuous_full(data: ContinuousCandidateInput) -> ContinuousEvaluation:
    candidate = evaluate_candidate_full(data.candidate_input)
    return _score_continuous_candidate(data, candidate)


def _score_continuous_candidate(
    data: ContinuousCandidateInput, candidate: Candidate
) -> ContinuousEvaluation:
    cut_plan = best_cut_plan(
        candidate,
        data.connection,
        data.orientation,
        data.minimum_piece_length,
        data.minimum_row_width,
        data.preferred_minimum_row_width,
    )
    return ContinuousEvaluation(
        score=continuous_candidate_score(candidate, cut_plan),
        candidate=candidate,
        cut_plan=cut_plan,
    )


def continuous_inputs(
    inputs: list[CandidateInput],
    *,
    connection,
    orientation: str,
    minimum_piece_length: float,
    minimum_row_width: float,
    preferred_minimum_row_width: float,
) -> list[ContinuousCandidateInput]:
    return [
        ContinuousCandidateInput(
            candidate_input=item,
            connection=connection,
            orientation=orientation,
            minimum_piece_length=minimum_piece_length,
            minimum_row_width=minimum_row_width,
            preferred_minimum_row_width=preferred_minimum_row_width,
        )
        for item in inputs
    ]


def parallel_continuous_coarse_generator(*, inputs, workers: int):
    yield from _parallel_map(
        inputs=inputs, workers=workers, function=_evaluate_continuous_fast
    )


def parallel_continuous_refine_generator(*, inputs, workers: int):
    yield from _parallel_map(
        inputs=inputs, workers=workers, function=_evaluate_continuous_full
    )


def parallel_coarse_generator(
    *,
    inputs: list[CandidateInput],
    workers: int,
) -> Iterable[Candidate]:
    yield from _parallel_map(
        inputs=inputs,
        workers=workers,
        function=evaluate_candidate_fast,
    )


def parallel_refine_generator(
    *,
    inputs: list[CandidateInput],
    workers: int,
) -> Iterable[Candidate]:
    yield from _parallel_map(
        inputs=inputs,
        workers=workers,
        function=evaluate_candidate_full,
    )
