from __future__ import annotations

import os
from concurrent.futures import (
    ProcessPoolExecutor,
    as_completed,
)
from typing import Iterable

from shapely.geometry import Polygon

from .candidate_evaluator import (
    evaluate_candidate_fast,
    evaluate_candidate_full,
)
from .models import Candidate, CandidateInput


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
                    base_offset=base_offset,
                    row_width_offset=row_width_offset,
                    start_corner=start_corner,
                )
            )

    return inputs


def _parallel_map(
    *,
    inputs: list[CandidateInput],
    workers: int,
    function,
) -> Iterable[Candidate]:
    max_workers = max(
        1,
        min(int(workers), os.cpu_count() or 1),
    )

    if max_workers == 1:
        for item in inputs:
            yield function(item)
        return

    with ProcessPoolExecutor(
        max_workers=max_workers,
    ) as executor:
        futures = [executor.submit(function, item) for item in inputs]

        for future in as_completed(futures):
            yield future.result()


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
