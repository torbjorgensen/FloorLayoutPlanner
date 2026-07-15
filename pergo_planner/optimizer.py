from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable

from shapely import wkb
from shapely.geometry import Polygon

from .planner import Piece, create_plan, create_row_fragments


@dataclass(frozen=True)
class Candidate:
    attempt: int
    total_attempts: int
    phase: str
    base_offset: float
    row_width_offset: float
    pieces: list[Piece]
    short_count: int
    very_short_count: int
    shortest_piece: float
    joint_violations: int
    narrow_row_count: int
    very_narrow_row_count: int
    narrowest_row_width: float
    row_offsets: dict[int, float]
    score: tuple
    timings: dict[str, float]


@dataclass(frozen=True)
class CandidateInput:
    attempt: int
    total_attempts: int
    floor_wkb: bytes
    board_length: float
    board_width: float
    orientation: str
    stagger_step: float
    minimum_piece_length: float
    minimum_joint_distance: float
    minimum_row_width: float
    preferred_minimum_row_width: float
    optimization_step: float
    base_offset: float
    row_width_offset: float


def _row_joint_positions(
    pieces: list[Piece],
    orientation: str,
) -> dict[int, list[float]]:
    rows: dict[int, dict[int, list[Piece]]] = {}

    for piece in pieces:
        rows.setdefault(piece.row, {}).setdefault(piece.segment, []).append(
            piece
        )

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
    minimum_row_width: float,
    preferred_minimum_row_width: float,
) -> tuple[int, int, float]:
    fragments = create_row_fragments(
        floor=floor,
        board_width=board_width,
        orientation=orientation,
        row_width_offset=row_width_offset,
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


def _problem_rows(
    pieces: list[Piece],
    minimum_piece_length: float,
) -> list[int]:
    return sorted(
        {piece.row for piece in pieces if piece.length < minimum_piece_length}
    )


def improve_problem_rows(
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
    base_offset: float,
    row_width_offset: float,
    initial_pieces: list[Piece],
) -> tuple[list[Piece], dict[int, float], tuple, int]:
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
    )

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


def _candidate_from_evaluation(
    *,
    data: CandidateInput,
    phase: str,
    pieces: list[Piece],
    row_offsets: dict[int, float],
    timings: dict[str, float],
) -> Candidate:
    evaluation_started = time.perf_counter()

    (
        short_count,
        very_short_count,
        shortest_piece,
        joint_violations,
        narrow_count,
        very_narrow_count,
        narrowest_width,
        score,
    ) = evaluate_pieces(
        pieces,
        data.minimum_piece_length,
        data.orientation,
        data.minimum_joint_distance,
        data.minimum_row_width,
        data.preferred_minimum_row_width,
        wkb.loads(data.floor_wkb),
        data.board_width,
        data.row_width_offset,
    )

    timings = dict(timings)
    timings["final_scoring_s"] = time.perf_counter() - evaluation_started
    timings["total_s"] = sum(
        value for key, value in timings.items() if key.endswith("_s")
    )

    return Candidate(
        attempt=data.attempt,
        total_attempts=data.total_attempts,
        phase=phase,
        base_offset=data.base_offset,
        row_width_offset=data.row_width_offset,
        pieces=pieces,
        short_count=short_count,
        very_short_count=very_short_count,
        shortest_piece=shortest_piece,
        joint_violations=joint_violations,
        narrow_row_count=narrow_count,
        very_narrow_row_count=very_narrow_count,
        narrowest_row_width=narrowest_width,
        row_offsets=row_offsets,
        score=score,
        timings=timings,
    )


def evaluate_candidate_fast(
    data: CandidateInput,
) -> Candidate:
    total_started = time.perf_counter()
    floor = wkb.loads(data.floor_wkb)

    generation_started = time.perf_counter()
    pieces = create_plan(
        floor=floor,
        board_length=data.board_length,
        board_width=data.board_width,
        orientation=data.orientation,
        stagger_step=data.stagger_step,
        minimum_piece_length=data.minimum_piece_length,
        base_offset=data.base_offset,
        row_width_offset=data.row_width_offset,
    )
    generation_s = time.perf_counter() - generation_started

    candidate = _candidate_from_evaluation(
        data=data,
        phase="coarse",
        pieces=pieces,
        row_offsets={},
        timings={
            "plan_generation_s": generation_s,
            "local_optimization_s": 0.0,
            "local_variants": 0,
        },
    )

    timings = dict(candidate.timings)
    timings["wall_clock_s"] = time.perf_counter() - total_started

    return Candidate(
        **{
            **candidate.__dict__,
            "timings": timings,
        }
    )


def evaluate_candidate_full(
    data: CandidateInput,
) -> Candidate:
    total_started = time.perf_counter()
    floor = wkb.loads(data.floor_wkb)

    generation_started = time.perf_counter()
    initial_pieces = create_plan(
        floor=floor,
        board_length=data.board_length,
        board_width=data.board_width,
        orientation=data.orientation,
        stagger_step=data.stagger_step,
        minimum_piece_length=data.minimum_piece_length,
        base_offset=data.base_offset,
        row_width_offset=data.row_width_offset,
    )
    generation_s = time.perf_counter() - generation_started

    local_started = time.perf_counter()
    (
        pieces,
        row_offsets,
        _,
        tested_variants,
    ) = improve_problem_rows(
        floor=floor,
        board_length=data.board_length,
        board_width=data.board_width,
        orientation=data.orientation,
        stagger_step=data.stagger_step,
        minimum_piece_length=data.minimum_piece_length,
        minimum_joint_distance=data.minimum_joint_distance,
        minimum_row_width=data.minimum_row_width,
        preferred_minimum_row_width=data.preferred_minimum_row_width,
        optimization_step=data.optimization_step,
        base_offset=data.base_offset,
        row_width_offset=data.row_width_offset,
        initial_pieces=initial_pieces,
    )
    local_s = time.perf_counter() - local_started

    candidate = _candidate_from_evaluation(
        data=data,
        phase="refine",
        pieces=pieces,
        row_offsets=row_offsets,
        timings={
            "plan_generation_s": generation_s,
            "local_optimization_s": local_s,
            "local_variants": tested_variants,
        },
    )

    timings = dict(candidate.timings)
    timings["wall_clock_s"] = time.perf_counter() - total_started

    return Candidate(
        **{
            **candidate.__dict__,
            "timings": timings,
        }
    )


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
