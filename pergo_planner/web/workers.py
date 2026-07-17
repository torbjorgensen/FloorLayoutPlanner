from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pergo_planner.continuous_solver import (
    best_cut_plan,
    build_continuous_floor,
    continuous_candidate_score,
    split_candidate_at_cut,
)
from pergo_planner.models import Candidate
from pergo_planner.optimizer import (
    build_candidate_inputs,
    parallel_coarse_generator,
    parallel_refine_generator,
)
from pergo_planner.renderer import plot_plan
from pergo_planner.validation import (
    InfeasibleLayoutError,
    candidate_meets_minimum_length,
    cut_plan_meets_minimum_length,
    select_best_valid_candidate,
    split_pieces_meet_minimum_lengths,
)
from pergo_planner.web.config import merged_settings
from pergo_planner.web.outputs import write_piece_csv
from pergo_planner.web.payloads import local_floor
from pergo_planner.web.state import ProjectState, RoomState


@dataclass(frozen=True)
class WorkerManager:
    room_by_id: Callable[[dict[str, Any], str], dict[str, Any]]
    start_room: Callable[[str, dict[str, Any]], None]
    start_all: Callable[[dict[str, Any]], None]


def create_worker_manager(
    state: ProjectState,
    output_dir: Path,
    config_path: Path,
    notify_state_changed: Callable[[], None],
) -> WorkerManager:
    def room_by_id(config: dict[str, Any], room_id: str) -> dict[str, Any]:
        room = next(
            (item for item in config["rooms"] if item["id"] == room_id),
            None,
        )
        if room is None:
            raise ValueError(f"Unknown room id: {room_id}")
        return room

    def save_room_best(
        room_id: str,
        generation: int,
        config_snapshot: dict[str, Any],
    ) -> None:
        with state.lock:
            room_state = state.rooms[room_id]
            if generation != room_state.generation:
                return
            best = room_state.best

        if best is None:
            return

        room = room_by_id(config_snapshot, room_id)
        settings = merged_settings(config_snapshot, room)
        minimum_length = float(settings["minimum_piece_length_mm"])
        if not candidate_meets_minimum_length(best, minimum_length):
            raise InfeasibleLayoutError(
                f"Refusing to write invalid output for {room_id}: one or more "
                f"pieces are shorter than {minimum_length:g} mm."
            )
        floor = local_floor(config_snapshot, room)

        csv_path = output_dir / f"{room_id}_pieces.csv"
        png_path = output_dir / f"{room_id}_plan.png"

        write_piece_csv(csv_path, best)
        plot_plan(
            output_path=png_path,
            floor=floor,
            pieces=best.pieces,
            rectangles=room["rectangles"],
            orientation=settings["orientation"],
            section_name=room["name"],
            plot_settings=settings,
            minimum_piece_length=float(settings["minimum_piece_length_mm"]),
        )

    def optimizer_worker(
        room_id: str,
        generation: int,
        config_snapshot: dict[str, Any],
    ) -> None:
        try:
            room = room_by_id(config_snapshot, room_id)
            settings = merged_settings(config_snapshot, room)
            minimum_length = float(settings["minimum_piece_length_mm"])
            board = config_snapshot["board"]
            floor = local_floor(config_snapshot, room)

            inputs = build_candidate_inputs(
                floor=floor,
                board_length=float(board["length_mm"]),
                board_width=float(board["width_mm"]),
                orientation=settings["orientation"],
                start_corner=settings["start_corner"],
                stagger_step=float(settings["stagger_step_mm"]),
                minimum_piece_length=minimum_length,
                minimum_joint_distance=float(settings["minimum_joint_distance_mm"]),
                minimum_row_width=float(settings["minimum_row_width_mm"]),
                preferred_minimum_row_width=float(
                    settings["preferred_minimum_row_width_mm"]
                ),
                optimization_step=float(settings["optimization_step_mm"]),
                row_width_optimization_step=float(
                    settings["row_width_optimization_step_mm"]
                ),
                saw_kerf_mm=float(board.get("saw_kerf_mm", 3.2)),
            )

            workers = int(settings["optimizer_workers"])
            preview_every = int(settings["preview_every_n_results"])
            top_n = min(
                int(settings["local_optimize_top_n"]),
                len(inputs),
            )
            delay_ms = int(settings["frame_delay_ms"])
            started_at = time.perf_counter()

            def update_profile(
                *,
                phase: str,
                completed: int,
                total: int,
                candidate: Candidate | None = None,
            ) -> None:
                elapsed = max(
                    time.perf_counter() - started_at,
                    1e-9,
                )
                rate = completed / elapsed
                remaining = max(total - completed, 0)
                eta = remaining / rate if rate > 0 else None

                with state.lock:
                    room_state = state.rooms[room_id]

                    if generation != room_state.generation:
                        return

                    room_state.profile.update(
                        {
                            "phase": phase,
                            "elapsed_s": elapsed,
                            "completed": completed,
                            "total": total,
                            "candidates_per_second": rate,
                            "eta_s": eta,
                            "workers": workers,
                        }
                    )

                    if candidate is not None:
                        totals = room_state.profile["timing_totals"]

                        for key, value in candidate.timings.items():
                            if key.endswith("_s"):
                                totals[key] = totals.get(key, 0.0) + float(value)

                        room_state.profile["local_variants"] += int(
                            candidate.timings.get(
                                "local_variants",
                                0,
                            )
                        )

                notify_state_changed()

            # Phase 1: cheap coarse search without local row optimization.
            coarse_results: list[Candidate] = []
            coarse_completed = 0

            for candidate in parallel_coarse_generator(
                inputs=inputs,
                workers=workers,
            ):
                coarse_completed += 1
                coarse_results.append(candidate)

                while True:
                    with state.lock:
                        room_state = state.rooms[room_id]

                        if generation != room_state.generation:
                            return

                        paused = room_state.paused

                    if not paused:
                        break

                    time.sleep(0.08)

                with state.lock:
                    room_state = state.rooms[room_id]

                    if generation != room_state.generation:
                        return

                    is_valid = candidate_meets_minimum_length(candidate, minimum_length)
                    is_new_best = is_valid and (
                        room_state.best is None
                        or candidate.score < room_state.best.score
                    )

                    if is_new_best:
                        room_state.best = candidate

                    if is_new_best or coarse_completed % preview_every == 0:
                        room_state.current = candidate

                    room_state.profile["coarse_completed"] = coarse_completed

                update_profile(
                    phase="coarse",
                    completed=coarse_completed,
                    total=len(inputs) + top_n,
                    candidate=candidate,
                )

            # Select only the best global candidates for expensive local refinement.
            coarse_results.sort(key=lambda item: item.score)
            shortlisted = coarse_results[:top_n]

            input_lookup = {
                (
                    item.base_offset,
                    item.row_width_offset,
                ): item
                for item in inputs
            }

            refine_inputs = [
                input_lookup[
                    (
                        candidate.base_offset,
                        candidate.row_width_offset,
                    )
                ]
                for candidate in shortlisted
            ]

            with state.lock:
                room_state = state.rooms[room_id]
                room_state.profile["phase"] = "refine"
                room_state.profile["refine_total"] = len(refine_inputs)

            refined_results: list[Candidate] = []
            refine_completed = 0

            for candidate in parallel_refine_generator(
                inputs=refine_inputs,
                workers=min(workers, max(1, len(refine_inputs))),
            ):
                refine_completed += 1
                refined_results.append(candidate)

                while True:
                    with state.lock:
                        room_state = state.rooms[room_id]

                        if generation != room_state.generation:
                            return

                        paused = room_state.paused

                    if not paused:
                        break

                    time.sleep(0.08)

                with state.lock:
                    room_state = state.rooms[room_id]

                    if generation != room_state.generation:
                        return

                    is_valid = candidate_meets_minimum_length(candidate, minimum_length)
                    is_new_best = is_valid and (
                        room_state.best is None
                        or candidate.score < room_state.best.score
                    )

                    if is_new_best:
                        room_state.best = candidate

                    room_state.current = candidate
                    room_state.profile["refine_completed"] = refine_completed

                update_profile(
                    phase="refine",
                    completed=len(inputs) + refine_completed,
                    total=len(inputs) + len(refine_inputs),
                    candidate=candidate,
                )

                if delay_ms > 0:
                    time.sleep(delay_ms / 1000)

            final_best = select_best_valid_candidate(
                [*coarse_results, *refined_results], minimum_length
            )
            with state.lock:
                room_state = state.rooms[room_id]
                if generation == room_state.generation:
                    room_state.best = final_best

            save_room_best(
                room_id,
                generation,
                config_snapshot,
            )

            with state.lock:
                room_state = state.rooms[room_id]

                if generation == room_state.generation:
                    room_state.current = room_state.best
                    room_state.running = False
                    room_state.finished = True
                    room_state.profile["phase"] = "finished"
                    room_state.profile["eta_s"] = 0.0
                    room_state.profile["elapsed_s"] = time.perf_counter() - started_at

            notify_state_changed()
        except Exception as exc:
            with state.lock:
                room_state = state.rooms[room_id]

                if generation == room_state.generation:
                    room_state.error = str(exc)
                    room_state.running = False
                    room_state.finished = True
                    room_state.profile["phase"] = "error"

            notify_state_changed()

    def continuous_worker(
        connection,
        generation: int,
        config_snapshot: dict[str, Any],
    ) -> None:
        continuous_state = state.continuous[connection.connection_id]
        try:
            room_a = room_by_id(config_snapshot, connection.room_a)
            room_b = room_by_id(config_snapshot, connection.room_b)
            settings_a = merged_settings(config_snapshot, room_a)
            settings_b = merged_settings(config_snapshot, room_b)
            if settings_a["orientation"] != settings_b["orientation"]:
                raise ValueError(
                    "continuous_then_cut requires the same laying "
                    "direction in both rooms."
                )
            if settings_a["start_corner"] != settings_b["start_corner"]:
                raise ValueError(
                    "continuous_then_cut requires the same start corner in both rooms."
                )
            orientation = settings_a["orientation"]
            minimum_length = float(settings_a["minimum_piece_length_mm"])
            minimum_lengths = {
                connection.room_a: minimum_length,
                connection.room_b: float(settings_b["minimum_piece_length_mm"]),
            }
            board = config_snapshot["board"]
            floor = build_continuous_floor(
                room_a,
                room_b,
                connection,
                float(settings_a["expansion_gap_mm"]),
            )
            inputs = build_candidate_inputs(
                floor=floor,
                board_length=float(board["length_mm"]),
                board_width=float(board["width_mm"]),
                orientation=orientation,
                start_corner=settings_a["start_corner"],
                stagger_step=float(settings_a["stagger_step_mm"]),
                minimum_piece_length=minimum_length,
                minimum_joint_distance=float(settings_a["minimum_joint_distance_mm"]),
                minimum_row_width=float(settings_a["minimum_row_width_mm"]),
                preferred_minimum_row_width=float(
                    settings_a["preferred_minimum_row_width_mm"]
                ),
                optimization_step=float(settings_a["optimization_step_mm"]),
                row_width_optimization_step=float(
                    settings_a["row_width_optimization_step_mm"]
                ),
                saw_kerf_mm=float(board.get("saw_kerf_mm", 3.2)),
            )
            workers = int(settings_a["optimizer_workers"])
            top_n = min(int(settings_a["local_optimize_top_n"]), len(inputs))
            started_at = time.perf_counter()
            coarse_total = len(inputs)
            refine_total = top_n
            total = coarse_total + refine_total + 1

            def update_continuous_progress(
                *,
                phase: str,
                completed: int,
                message: str,
                coarse_completed: int,
                refine_completed: int,
            ) -> None:
                elapsed = max(time.perf_counter() - started_at, 1e-9)
                rate = completed / elapsed
                remaining = max(total - completed, 0)
                eta = remaining / rate if rate > 0 else None

                with state.lock:
                    current_state = state.continuous[connection.connection_id]
                    if generation != current_state.generation:
                        return
                    current_state.profile.update(
                        {
                            "phase": phase,
                            "completed": completed,
                            "total": total,
                            "percent": (100.0 * completed / total if total else 0.0),
                            "elapsed_s": elapsed,
                            "eta_s": eta,
                            "candidates_per_second": rate,
                            "workers": workers,
                            "coarse_total": coarse_total,
                            "coarse_completed": coarse_completed,
                            "refine_total": refine_total,
                            "refine_completed": refine_completed,
                            "message": message,
                        }
                    )
                notify_state_changed()

            update_continuous_progress(
                phase="coarse",
                completed=0,
                message="Coarse-searching transition",
                coarse_completed=0,
                refine_completed=0,
            )

            coarse_ranked = []
            refined_ranked = []
            coarse_completed = 0
            for candidate in parallel_coarse_generator(inputs=inputs, workers=workers):
                if generation != continuous_state.generation:
                    return
                cut_plan = best_cut_plan(
                    candidate,
                    connection,
                    orientation,
                    minimum_length,
                    float(settings_a["minimum_row_width_mm"]),
                    float(settings_a["preferred_minimum_row_width_mm"]),
                )
                item = (
                    continuous_candidate_score(candidate, cut_plan),
                    candidate,
                    cut_plan,
                )
                coarse_ranked.append(item)
                coarse_completed += 1
                with state.lock:
                    continuous_state.current = candidate
                update_continuous_progress(
                    phase="coarse",
                    completed=coarse_completed,
                    message="Coarse-searching transition",
                    coarse_completed=coarse_completed,
                    refine_completed=0,
                )
            if not coarse_ranked:
                raise ValueError(
                    "No candidates were generated for the continuous floor."
                )

            def item_is_valid(item) -> bool:
                _, candidate, cut_plan = item
                return candidate_meets_minimum_length(
                    candidate, minimum_length
                ) and cut_plan_meets_minimum_length(cut_plan)

            coarse_ranked.sort(key=lambda item: (not item_is_valid(item), item[0]))
            input_lookup = {
                (item.base_offset, item.row_width_offset): item for item in inputs
            }
            refine_inputs = [
                input_lookup[(candidate.base_offset, candidate.row_width_offset)]
                for _, candidate, _ in coarse_ranked[:top_n]
            ]
            refine_completed = 0
            update_continuous_progress(
                phase="refine",
                completed=coarse_total,
                message="Refining transition",
                coarse_completed=coarse_total,
                refine_completed=0,
            )
            for candidate in parallel_refine_generator(
                inputs=refine_inputs,
                workers=min(workers, max(1, len(refine_inputs))),
            ):
                cut_plan = best_cut_plan(
                    candidate,
                    connection,
                    orientation,
                    minimum_length,
                    float(settings_a["minimum_row_width_mm"]),
                    float(settings_a["preferred_minimum_row_width_mm"]),
                )
                item = (
                    continuous_candidate_score(candidate, cut_plan),
                    candidate,
                    cut_plan,
                )
                refined_ranked.append(item)
                refine_completed += 1
                with state.lock:
                    continuous_state.current = candidate
                update_continuous_progress(
                    phase="refine",
                    completed=coarse_total + refine_completed,
                    message="Refining transition",
                    coarse_completed=coarse_total,
                    refine_completed=refine_completed,
                )

            update_continuous_progress(
                phase="cut",
                completed=coarse_total + refine_total,
                message="Selecting expansion gap",
                coarse_completed=coarse_total,
                refine_completed=refine_total,
            )

            ranked_items = sorted(
                [*coarse_ranked, *refined_ranked],
                key=lambda item: (not item_is_valid(item), item[0]),
            )
            selected_item = None
            selected_room_pieces = None
            for item in ranked_items:
                if not item_is_valid(item):
                    continue
                _, candidate, cut_plan = item
                room_pieces = split_candidate_at_cut(
                    candidate=candidate,
                    room_a=room_a,
                    room_b=room_b,
                    connection=connection,
                    cut_plan=cut_plan,
                    orientation=orientation,
                )
                if split_pieces_meet_minimum_lengths(room_pieces, minimum_lengths):
                    selected_item = item
                    selected_room_pieces = room_pieces
                    break

            if selected_item is None or selected_room_pieces is None:
                raise InfeasibleLayoutError(
                    "No valid continuous layout and expansion-gap position "
                    "satisfies the configured minimum piece lengths after "
                    "splitting the finished rooms."
                )

            best_item = selected_item

            with state.lock:
                continuous_state.best = best_item[1]
                continuous_state.current = best_item[1]
                continuous_state.cut_plan = best_item[2]
                continuous_state.room_pieces = selected_room_pieces
                continuous_state.running = False
                continuous_state.finished = True
                continuous_state.profile.update(
                    {
                        "phase": "finished",
                        "completed": total,
                        "total": total,
                        "percent": 100.0,
                        "elapsed_s": time.perf_counter() - started_at,
                        "eta_s": 0.0,
                        "message": "Finished",
                    }
                )
            notify_state_changed()
        except Exception as exc:
            with state.lock:
                continuous_state.error = str(exc)
                continuous_state.running = False
                continuous_state.finished = True
                continuous_state.profile.update(
                    {
                        "phase": "error",
                        "eta_s": None,
                        "message": str(exc),
                    }
                )
            notify_state_changed()

    def start_continuous(connection, config: dict[str, Any]) -> None:
        continuous_state = state.continuous[connection.connection_id]
        continuous_state.generation += 1
        generation = continuous_state.generation
        continuous_state.running = True
        continuous_state.finished = False
        continuous_state.error = None
        continuous_state.current = None
        continuous_state.best = None
        continuous_state.cut_plan = None
        continuous_state.room_pieces = {}
        continuous_state.profile = {
            "phase": "starting",
            "completed": 0,
            "total": 0,
            "percent": 0.0,
            "elapsed_s": 0.0,
            "eta_s": None,
            "candidates_per_second": 0.0,
            "workers": 0,
            "coarse_total": 0,
            "coarse_completed": 0,
            "refine_total": 0,
            "refine_completed": 0,
            "message": "Starting transition calculation",
        }
        notify_state_changed()
        threading.Thread(
            target=continuous_worker,
            args=(connection, generation, copy.deepcopy(config)),
            daemon=True,
        ).start()

    def start_room(room_id: str, config: dict[str, Any]) -> None:
        room = room_by_id(config, room_id)
        local_floor(config, room)  # validate synchronously

        with state.lock:
            if room_id not in state.rooms:
                state.rooms[room_id] = RoomState(room_id)

            room_state = state.rooms[room_id]
            room_state.generation += 1
            generation = room_state.generation
            room_state.running = True
            room_state.paused = False
            room_state.finished = False
            room_state.error = None
            room_state.current = None
            room_state.best = None
            room_state.profile = {
                "phase": "starting",
                "started_at": time.time(),
                "elapsed_s": 0.0,
                "completed": 0,
                "total": 0,
                "candidates_per_second": 0.0,
                "eta_s": None,
                "workers": int(merged_settings(config, room)["optimizer_workers"]),
                "coarse_total": 0,
                "coarse_completed": 0,
                "refine_total": 0,
                "refine_completed": 0,
                "timing_totals": {},
                "local_variants": 0,
            }

        notify_state_changed()
        threading.Thread(
            target=optimizer_worker,
            args=(room_id, generation, copy.deepcopy(config)),
            daemon=True,
        ).start()

    def start_all(config: dict[str, Any]) -> None:
        for room in config["rooms"]:
            start_room(room["id"], config)
        for connection in state.connections:
            if connection.connection_type == "continuous_then_cut":
                start_continuous(connection, config)

    return WorkerManager(
        room_by_id=room_by_id,
        start_room=start_room,
        start_all=start_all,
    )
