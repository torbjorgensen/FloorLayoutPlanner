from __future__ import annotations

import time

from shapely import wkb

from .layout_solver import improve_problem_rows
from .models import Candidate, CandidateInput
from .planner import Piece, create_plan
from .scorer import evaluate_pieces


def _candidate_from_evaluation(
    *,
    data: CandidateInput,
    phase: str,
    pieces: list[Piece],
    row_offsets: dict[int, float],
    timings: dict[str, float],
) -> Candidate:
    evaluation_started = time.perf_counter()
    floor = wkb.loads(data.floor_wkb)

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
        floor,
        data.board_width,
        data.row_width_offset,
        data.start_corner,
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
        row_width_offset=(data.row_width_offset),
        pieces=pieces,
        short_count=short_count,
        very_short_count=(very_short_count),
        shortest_piece=shortest_piece,
        joint_violations=(joint_violations),
        narrow_row_count=narrow_count,
        very_narrow_row_count=(very_narrow_count),
        narrowest_row_width=(narrowest_width),
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
        board_length=(data.board_length),
        board_width=data.board_width,
        orientation=data.orientation,
        start_corner=data.start_corner,
        stagger_step=(data.stagger_step),
        minimum_piece_length=(data.minimum_piece_length),
        base_offset=data.base_offset,
        row_width_offset=(data.row_width_offset),
    )

    candidate = _candidate_from_evaluation(
        data=data,
        phase="coarse",
        pieces=pieces,
        row_offsets={},
        timings={
            "plan_generation_s": (time.perf_counter() - generation_started),
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
        board_length=(data.board_length),
        board_width=data.board_width,
        orientation=data.orientation,
        start_corner=data.start_corner,
        stagger_step=(data.stagger_step),
        minimum_piece_length=(data.minimum_piece_length),
        base_offset=data.base_offset,
        row_width_offset=(data.row_width_offset),
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
        board_length=(data.board_length),
        board_width=data.board_width,
        orientation=data.orientation,
        start_corner=data.start_corner,
        stagger_step=(data.stagger_step),
        minimum_piece_length=(data.minimum_piece_length),
        minimum_joint_distance=(data.minimum_joint_distance),
        minimum_row_width=(data.minimum_row_width),
        preferred_minimum_row_width=(data.preferred_minimum_row_width),
        optimization_step=(data.optimization_step),
        base_offset=data.base_offset,
        row_width_offset=(data.row_width_offset),
        initial_pieces=(initial_pieces),
    )

    candidate = _candidate_from_evaluation(
        data=data,
        phase="refine",
        pieces=pieces,
        row_offsets=row_offsets,
        timings={
            "plan_generation_s": (generation_s),
            "local_optimization_s": (time.perf_counter() - local_started),
            "local_variants": (tested_variants),
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
