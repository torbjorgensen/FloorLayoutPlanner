#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import json
import threading
import time
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from pergo_planner.connections import connection_payload, parse_connections
from pergo_planner.continuous_solver import (
    best_cut_plan,
    build_continuous_floor,
    continuous_candidate_score,
    cut_plan_payload,
)
from pergo_planner.geometry import build_floor_polygon
from pergo_planner.models import Candidate
from pergo_planner.optimizer import (
    build_candidate_inputs,
    parallel_coarse_generator,
    parallel_refine_generator,
)
from pergo_planner.renderer import plot_plan

DEFAULT_SETTINGS = {
    "orientation": "horizontal",
    "expansion_gap_mm": 5.0,
    "minimum_piece_length_mm": 300.0,
    "minimum_joint_distance_mm": 300.0,
    "stagger_step_mm": 700.0,
    "optimization_step_mm": 20.0,
    "row_width_optimization_step_mm": 5.0,
    "minimum_row_width_mm": 60.0,
    "preferred_minimum_row_width_mm": 100.0,
    "optimizer_workers": 8,
    "preview_every_n_results": 25,
    "local_optimize_top_n": 12,
    "frame_delay_ms": 60,
    "waste_percent": 10.0,
    "boards_per_pack": 8,
}


class RoomState:
    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self.running = False
        self.paused = False
        self.finished = False
        self.error: str | None = None
        self.current: Candidate | None = None
        self.best: Candidate | None = None
        self.generation = 0
        self.profile: dict[str, Any] = {
            "phase": "idle",
            "started_at": None,
            "elapsed_s": 0.0,
            "completed": 0,
            "total": 0,
            "candidates_per_second": 0.0,
            "eta_s": None,
            "workers": 0,
            "coarse_total": 0,
            "coarse_completed": 0,
            "refine_total": 0,
            "refine_completed": 0,
            "timing_totals": {},
            "local_variants": 0,
        }


class ContinuousState:
    def __init__(self, connection_id: str) -> None:
        self.connection_id = connection_id
        self.running = False
        self.finished = False
        self.error: str | None = None
        self.current: Candidate | None = None
        self.best: Candidate | None = None
        self.cut_plan = None
        self.generation = 0


class ProjectState:
    def __init__(self, config: dict[str, Any]) -> None:
        self.lock = threading.RLock()
        self.file_config = copy.deepcopy(config)
        self.active_config = copy.deepcopy(config)
        self.connections = parse_connections(config)
        self.continuous: dict[str, ContinuousState] = {
            connection.connection_id: ContinuousState(connection.connection_id)
            for connection in self.connections
            if connection.connection_type == "continuous_then_cut"
        }
        self.rooms: dict[str, RoomState] = {
            room["id"]: RoomState(room["id"]) for room in config["rooms"]
        }

    @staticmethod
    def piece_payload(piece: Any) -> dict[str, Any]:
        return {
            "row": piece.row,
            "segment": piece.segment,
            "piece": piece.piece,
            "x1": piece.x1,
            "x2": piece.x2,
            "y1": piece.y1,
            "y2": piece.y2,
            "length": piece.length,
            "width": piece.width,
            "source_board_index": piece.source_board_index,
            "is_full_length": piece.is_full_length,
        }

    def candidate_payload(self, candidate: Candidate | None) -> dict | None:
        if candidate is None:
            return None

        return {
            "attempt": candidate.attempt,
            "total_attempts": candidate.total_attempts,
            "base_offset": candidate.base_offset,
            "row_width_offset": candidate.row_width_offset,
            "short_count": candidate.short_count,
            "very_short_count": candidate.very_short_count,
            "shortest_piece": candidate.shortest_piece,
            "joint_violations": candidate.joint_violations,
            "narrow_row_count": candidate.narrow_row_count,
            "very_narrow_row_count": candidate.very_narrow_row_count,
            "narrowest_row_width": candidate.narrowest_row_width,
            "row_offsets": candidate.row_offsets,
            "phase": candidate.phase,
            "timings": candidate.timings,
            "pieces": [self.piece_payload(piece) for piece in candidate.pieces],
        }


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Fant ikke konfigurasjonsfilen: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Ugyldig JSON i {path}: linje {exc.lineno}, kolonne {exc.colno}: {exc.msg}"
        ) from exc

    # Backward compatibility: old one-room format.
    if "rooms" not in config and "rectangles" in config:
        config = {
            "project_name": config.get("section_name", "Gulvprosjekt"),
            "board": config["board"],
            "settings": config.get("settings", {}),
            "rooms": [
                {
                    "id": "room_1",
                    "name": config.get("section_name", "Rom 1"),
                    "origin": {"x": 0, "y": 0},
                    "rectangles": config["rectangles"],
                    "settings": {},
                }
            ],
        }

    required = {"project_name", "rooms", "board"}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"Konfigurasjonen mangler felt: {sorted(missing)}")

    if not isinstance(config["rooms"], list) or not config["rooms"]:
        raise ValueError("'rooms' må være en ikke-tom liste.")

    seen_ids: set[str] = set()
    for room in config["rooms"]:
        for field in ("id", "name", "rectangles"):
            if field not in room:
                raise ValueError(f"Et rom mangler feltet '{field}'.")
        if room["id"] in seen_ids:
            raise ValueError(f"Duplisert rom-id: {room['id']}")
        seen_ids.add(room["id"])
        if not room["rectangles"]:
            raise ValueError(f"Rommet '{room['name']}' mangler rektangler.")

    return config


def merged_settings(
    project_config: dict[str, Any],
    room: dict[str, Any],
) -> dict[str, Any]:
    settings = dict(DEFAULT_SETTINGS)
    settings.update(project_config.get("settings", {}))
    settings.update(room.get("settings", {}))

    board_length = float(project_config["board"]["length_mm"])
    if settings.get("stagger_step_mm") in (None, ""):
        settings["stagger_step_mm"] = board_length / 3

    if settings.get("minimum_joint_distance_mm") in (None, ""):
        settings["minimum_joint_distance_mm"] = settings["minimum_piece_length_mm"]

    return settings


def editable_room_settings(
    project_config: dict[str, Any],
    room: dict[str, Any],
) -> dict[str, Any]:
    settings = merged_settings(project_config, room)
    board = project_config["board"]

    return {
        "orientation": settings["orientation"],
        "expansion_gap_mm": float(settings["expansion_gap_mm"]),
        "minimum_piece_length_mm": float(settings["minimum_piece_length_mm"]),
        "minimum_joint_distance_mm": float(settings["minimum_joint_distance_mm"]),
        "stagger_step_mm": float(settings["stagger_step_mm"]),
        "optimization_step_mm": float(settings["optimization_step_mm"]),
        "row_width_optimization_step_mm": float(
            settings["row_width_optimization_step_mm"]
        ),
        "minimum_row_width_mm": float(settings["minimum_row_width_mm"]),
        "preferred_minimum_row_width_mm": float(
            settings["preferred_minimum_row_width_mm"]
        ),
        "optimizer_workers": int(settings["optimizer_workers"]),
        "preview_every_n_results": int(settings["preview_every_n_results"]),
        "local_optimize_top_n": int(settings["local_optimize_top_n"]),
        "frame_delay_ms": int(settings["frame_delay_ms"]),
        "board_length_mm": float(board["length_mm"]),
        "board_width_mm": float(board["width_mm"]),
        "waste_percent": float(settings["waste_percent"]),
        "boards_per_pack": int(settings["boards_per_pack"]),
    }


def parse_float(payload: dict[str, Any], name: str) -> float:
    try:
        return float(payload[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"'{name}' må være et tall.") from exc


def parse_int(payload: dict[str, Any], name: str) -> int:
    try:
        return int(payload[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"'{name}' må være et heltall.") from exc


def update_room_settings(
    project_config: dict[str, Any],
    room_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    config = copy.deepcopy(project_config)
    room = next(
        (item for item in config["rooms"] if item["id"] == room_id),
        None,
    )
    if room is None:
        raise ValueError(f"Ukjent rom-id: {room_id}")

    orientation = str(payload.get("orientation", "")).lower()
    if orientation not in {"horizontal", "vertical"}:
        raise ValueError("'orientation' må være 'horizontal' eller 'vertical'.")

    values = {
        "expansion_gap_mm": parse_float(payload, "expansion_gap_mm"),
        "minimum_piece_length_mm": parse_float(payload, "minimum_piece_length_mm"),
        "minimum_joint_distance_mm": parse_float(payload, "minimum_joint_distance_mm"),
        "stagger_step_mm": parse_float(payload, "stagger_step_mm"),
        "optimization_step_mm": parse_float(payload, "optimization_step_mm"),
        "row_width_optimization_step_mm": parse_float(
            payload, "row_width_optimization_step_mm"
        ),
        "minimum_row_width_mm": parse_float(payload, "minimum_row_width_mm"),
        "preferred_minimum_row_width_mm": parse_float(
            payload, "preferred_minimum_row_width_mm"
        ),
        "optimizer_workers": parse_int(payload, "optimizer_workers"),
        "preview_every_n_results": parse_int(payload, "preview_every_n_results"),
        "local_optimize_top_n": parse_int(payload, "local_optimize_top_n"),
        "frame_delay_ms": parse_int(payload, "frame_delay_ms"),
        "waste_percent": parse_float(payload, "waste_percent"),
        "boards_per_pack": parse_int(payload, "boards_per_pack"),
    }

    board_length = parse_float(payload, "board_length_mm")
    board_width = parse_float(payload, "board_width_mm")

    if values["expansion_gap_mm"] < 0:
        raise ValueError("Ekspansjonsfugen kan ikke være negativ.")
    if values["minimum_piece_length_mm"] <= 0:
        raise ValueError("Minimum bitlengde må være større enn 0.")
    if values["minimum_joint_distance_mm"] < 0:
        raise ValueError("Minimum skjøteavstand kan ikke være negativ.")
    if not 0 < values["stagger_step_mm"] < board_length:
        raise ValueError(
            "Forskyvningen må være større enn 0 og mindre enn bordlengden."
        )
    if values["optimization_step_mm"] <= 0:
        raise ValueError("Optimaliseringssteg må være større enn 0.")
    if values["row_width_optimization_step_mm"] <= 0:
        raise ValueError("Radbredde-steg må være større enn 0.")
    if values["minimum_row_width_mm"] <= 0:
        raise ValueError("Minimum radbredde må være større enn 0.")
    if values["preferred_minimum_row_width_mm"] < values["minimum_row_width_mm"]:
        raise ValueError(
            "Ønsket minimum radbredde kan ikke være mindre enn absolutt minimum."
        )
    if values["optimizer_workers"] <= 0:
        raise ValueError("Antall prosesser må være større enn 0.")
    if values["preview_every_n_results"] <= 0:
        raise ValueError("Visningsintervall må være større enn 0.")
    if values["local_optimize_top_n"] <= 0:
        raise ValueError("Top-N må være større enn 0.")
    if values["frame_delay_ms"] < 0:
        raise ValueError("Visningsforsinkelsen kan ikke være negativ.")
    if board_length <= 0 or board_width <= 0:
        raise ValueError("Bordmål må være større enn 0.")

    config["board"]["length_mm"] = board_length
    config["board"]["width_mm"] = board_width

    room.setdefault("settings", {})
    room["settings"].update({"orientation": orientation, **values})

    return config


def global_rectangles(room: dict[str, Any]) -> list[dict[str, Any]]:
    origin = room.get("origin", {})
    origin_x = float(origin.get("x", 0))
    origin_y = float(origin.get("y", 0))

    result = []
    for rectangle in room["rectangles"]:
        item = copy.deepcopy(rectangle)
        item["x"] = origin_x + float(rectangle["x"])
        item["y"] = origin_y + float(rectangle["y"])
        result.append(item)
    return result


def local_floor(
    project_config: dict[str, Any],
    room: dict[str, Any],
):
    settings = merged_settings(project_config, room)
    return build_floor_polygon(
        room["rectangles"],
        float(settings["expansion_gap_mm"]),
    )


def room_canvas_payload(
    project_config: dict[str, Any],
    room: dict[str, Any],
    room_state: RoomState,
    state: ProjectState,
) -> dict[str, Any]:
    settings = merged_settings(project_config, room)
    floor = local_floor(project_config, room)
    origin = room.get("origin", {})
    origin_x = float(origin.get("x", 0))
    origin_y = float(origin.get("y", 0))

    candidate = (
        room_state.best
        if room_state.finished and room_state.best is not None
        else room_state.current or room_state.best
    )
    candidate_payload = state.candidate_payload(candidate)

    if candidate_payload:
        for piece in candidate_payload["pieces"]:
            piece["x1"] += origin_x
            piece["x2"] += origin_x
            piece["y1"] += origin_y
            piece["y2"] += origin_y

    outline = [[x + origin_x, y + origin_y] for x, y in floor.exterior.coords]

    bounds = floor.bounds
    return {
        "id": room["id"],
        "name": room["name"],
        "origin": {"x": origin_x, "y": origin_y},
        "rectangles": global_rectangles(room),
        "outline": outline,
        "bounds": {
            "min_x": bounds[0] + origin_x,
            "min_y": bounds[1] + origin_y,
            "max_x": bounds[2] + origin_x,
            "max_y": bounds[3] + origin_y,
        },
        "settings": editable_room_settings(project_config, room),
        "minimum_piece_length": float(settings["minimum_piece_length_mm"]),
        "running": room_state.running,
        "paused": room_state.paused,
        "finished": room_state.finished,
        "error": room_state.error,
        "current": candidate_payload,
        "best": state.candidate_payload(room_state.best),
        "profile": copy.deepcopy(room_state.profile),
    }


def write_piece_csv(path: Path, candidate: Candidate) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(
            [
                "rad",
                "segment",
                "bit",
                "x1_mm",
                "x2_mm",
                "y1_mm",
                "y2_mm",
                "lengde_mm",
                "bredde_mm",
                "global_bordindeks",
                "hel_bordlengde",
            ]
        )
        for piece in candidate.pieces:
            writer.writerow(
                [
                    piece.row,
                    piece.segment,
                    piece.piece,
                    round(piece.x1, 1),
                    round(piece.x2, 1),
                    round(piece.y1, 1),
                    round(piece.y2, 1),
                    round(piece.length, 1),
                    round(piece.width, 1),
                    piece.source_board_index,
                    "ja" if piece.is_full_length else "nei",
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Floor Layout Planner med flere rom.")
    parser.add_argument("config", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    initial_config = load_config(args.config)
    state = ProjectState(initial_config)
    app = Flask(__name__)

    output_dir = args.config.parent / f"{args.config.stem}_output"
    output_dir.mkdir(exist_ok=True)

    def room_by_id(config: dict[str, Any], room_id: str) -> dict[str, Any]:
        room = next(
            (item for item in config["rooms"] if item["id"] == room_id),
            None,
        )
        if room is None:
            raise ValueError(f"Ukjent rom-id: {room_id}")
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
            board = config_snapshot["board"]
            floor = local_floor(config_snapshot, room)

            inputs = build_candidate_inputs(
                floor=floor,
                board_length=float(board["length_mm"]),
                board_width=float(board["width_mm"]),
                orientation=settings["orientation"],
                stagger_step=float(settings["stagger_step_mm"]),
                minimum_piece_length=float(settings["minimum_piece_length_mm"]),
                minimum_joint_distance=float(settings["minimum_joint_distance_mm"]),
                minimum_row_width=float(settings["minimum_row_width_mm"]),
                preferred_minimum_row_width=float(
                    settings["preferred_minimum_row_width_mm"]
                ),
                optimization_step=float(settings["optimization_step_mm"]),
                row_width_optimization_step=float(
                    settings["row_width_optimization_step_mm"]
                ),
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

            # FASE 1: billig grovsøk uten lokal radoptimalisering.
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

                    is_new_best = (
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

            # Velg bare de beste globale kandidatene til dyr lokal forbedring.
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

            # Nullstill best før refine, slik at den beste fullverdige
            # kandidaten prioriteres over grovkandidatene.
            refined_best: Candidate | None = None
            refine_completed = 0

            for candidate in parallel_refine_generator(
                inputs=refine_inputs,
                workers=min(workers, max(1, len(refine_inputs))),
            ):
                refine_completed += 1

                while True:
                    with state.lock:
                        room_state = state.rooms[room_id]

                        if generation != room_state.generation:
                            return

                        paused = room_state.paused

                    if not paused:
                        break

                    time.sleep(0.08)

                if refined_best is None or candidate.score < refined_best.score:
                    refined_best = candidate

                with state.lock:
                    room_state = state.rooms[room_id]

                    if generation != room_state.generation:
                        return

                    is_new_best = (
                        room_state.best is None
                        or candidate.score < room_state.best.score
                        or candidate.phase == "refine"
                        and room_state.best.phase == "coarse"
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

            if refined_best is not None:
                with state.lock:
                    room_state = state.rooms[room_id]

                    if generation == room_state.generation:
                        room_state.best = refined_best

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

        except Exception as exc:
            with state.lock:
                room_state = state.rooms[room_id]

                if generation == room_state.generation:
                    room_state.error = str(exc)
                    room_state.running = False
                    room_state.finished = True
                    room_state.profile["phase"] = "error"

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
                    "continuous_then_cut krever samme leggeretning i begge rom."
                )
            orientation = settings_a["orientation"]
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
                stagger_step=float(settings_a["stagger_step_mm"]),
                minimum_piece_length=float(settings_a["minimum_piece_length_mm"]),
                minimum_joint_distance=float(settings_a["minimum_joint_distance_mm"]),
                minimum_row_width=float(settings_a["minimum_row_width_mm"]),
                preferred_minimum_row_width=float(
                    settings_a["preferred_minimum_row_width_mm"]
                ),
                optimization_step=float(settings_a["optimization_step_mm"]),
                row_width_optimization_step=float(
                    settings_a["row_width_optimization_step_mm"]
                ),
            )
            workers = int(settings_a["optimizer_workers"])
            top_n = min(int(settings_a["local_optimize_top_n"]), len(inputs))
            coarse_ranked = []
            for candidate in parallel_coarse_generator(inputs=inputs, workers=workers):
                if generation != continuous_state.generation:
                    return
                cut_plan = best_cut_plan(
                    candidate,
                    connection,
                    orientation,
                    float(settings_a["minimum_piece_length_mm"]),
                    float(settings_a["minimum_row_width_mm"]),
                    float(settings_a["preferred_minimum_row_width_mm"]),
                )
                item = (
                    continuous_candidate_score(candidate, cut_plan),
                    candidate,
                    cut_plan,
                )
                coarse_ranked.append(item)
                with state.lock:
                    continuous_state.current = candidate
            if not coarse_ranked:
                raise ValueError("Ingen kandidater ble generert for kontinuerlig gulv.")
            coarse_ranked.sort(key=lambda item: item[0])
            input_lookup = {
                (item.base_offset, item.row_width_offset): item for item in inputs
            }
            refine_inputs = [
                input_lookup[(candidate.base_offset, candidate.row_width_offset)]
                for _, candidate, _ in coarse_ranked[:top_n]
            ]
            best_item = coarse_ranked[0]
            for candidate in parallel_refine_generator(
                inputs=refine_inputs,
                workers=min(workers, max(1, len(refine_inputs))),
            ):
                cut_plan = best_cut_plan(
                    candidate,
                    connection,
                    orientation,
                    float(settings_a["minimum_piece_length_mm"]),
                    float(settings_a["minimum_row_width_mm"]),
                    float(settings_a["preferred_minimum_row_width_mm"]),
                )
                item = (
                    continuous_candidate_score(candidate, cut_plan),
                    candidate,
                    cut_plan,
                )
                if item[0] < best_item[0]:
                    best_item = item
                with state.lock:
                    continuous_state.current = candidate
            with state.lock:
                continuous_state.best = best_item[1]
                continuous_state.current = best_item[1]
                continuous_state.cut_plan = best_item[2]
                continuous_state.running = False
                continuous_state.finished = True
        except Exception as exc:
            with state.lock:
                continuous_state.error = str(exc)
                continuous_state.running = False
                continuous_state.finished = True

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

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            project_name=state.active_config["project_name"],
        )

    @app.get("/api/state")
    def api_state():
        with state.lock:
            config_snapshot = copy.deepcopy(state.active_config)
            rooms_payload = [
                room_canvas_payload(
                    config_snapshot,
                    room,
                    state.rooms[room["id"]],
                    state,
                )
                for room in config_snapshot["rooms"]
            ]

        all_bounds = [room["bounds"] for room in rooms_payload]
        project_bounds = {
            "min_x": min(item["min_x"] for item in all_bounds),
            "min_y": min(item["min_y"] for item in all_bounds),
            "max_x": max(item["max_x"] for item in all_bounds),
            "max_y": max(item["max_y"] for item in all_bounds),
        }

        return jsonify(
            {
                "project_name": config_snapshot["project_name"],
                "board": config_snapshot["board"],
                "rooms": rooms_payload,
                "bounds": project_bounds,
                "output_dir": str(output_dir),
                "connections": [
                    {
                        **connection_payload(connection),
                        "continuous": (
                            {
                                "running": state.continuous[
                                    connection.connection_id
                                ].running,
                                "finished": state.continuous[
                                    connection.connection_id
                                ].finished,
                                "error": state.continuous[
                                    connection.connection_id
                                ].error,
                                "candidate": state.candidate_payload(
                                    state.continuous[connection.connection_id].current
                                    or state.continuous[connection.connection_id].best
                                ),
                                "cut_plan": (
                                    cut_plan_payload(
                                        state.continuous[
                                            connection.connection_id
                                        ].cut_plan
                                    )
                                    if state.continuous[
                                        connection.connection_id
                                    ].cut_plan
                                    is not None
                                    else None
                                ),
                            }
                            if connection.connection_type == "continuous_then_cut"
                            else None
                        ),
                    }
                    for connection in state.connections
                ],
            }
        )

    @app.post("/api/room/<room_id>/apply")
    def api_room_apply(room_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            with state.lock:
                base_config = copy.deepcopy(state.active_config)

            updated = update_room_settings(
                base_config,
                room_id,
                payload,
            )

            with state.lock:
                state.active_config = copy.deepcopy(updated)

            start_room(room_id, updated)

            room = room_by_id(updated, room_id)
            return jsonify(
                {
                    "ok": True,
                    "settings": editable_room_settings(updated, room),
                }
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/room/<room_id>/save")
    def api_room_save(room_id: str):
        payload = request.get_json(silent=True) or {}
        try:
            with state.lock:
                base_config = copy.deepcopy(state.active_config)

            updated = update_room_settings(
                base_config,
                room_id,
                payload,
            )

            temp_path = args.config.with_suffix(args.config.suffix + ".tmp")
            with temp_path.open("w", encoding="utf-8") as file:
                json.dump(updated, file, indent=2, ensure_ascii=False)
                file.write("\n")
            temp_path.replace(args.config)

            with state.lock:
                state.active_config = copy.deepcopy(updated)
                state.file_config = copy.deepcopy(updated)

            start_room(room_id, updated)

            room = room_by_id(updated, room_id)
            return jsonify(
                {
                    "ok": True,
                    "message": f"Lagret til {args.config}",
                    "settings": editable_room_settings(updated, room),
                }
            )
        except (ValueError, OSError) as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/room/<room_id>/reset")
    def api_room_reset(room_id: str):
        with state.lock:
            restored = copy.deepcopy(state.file_config)
            state.active_config = copy.deepcopy(restored)

        try:
            start_room(room_id, restored)
            room = room_by_id(restored, room_id)
            return jsonify(
                {
                    "ok": True,
                    "settings": editable_room_settings(restored, room),
                }
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.post("/api/room/<room_id>/pause")
    def api_room_pause(room_id: str):
        with state.lock:
            state.rooms[room_id].paused = True
        return jsonify({"ok": True})

    @app.post("/api/room/<room_id>/resume")
    def api_room_resume(room_id: str):
        with state.lock:
            state.rooms[room_id].paused = False
        return jsonify({"ok": True})

    @app.post("/api/room/<room_id>/restart")
    def api_room_restart(room_id: str):
        with state.lock:
            config_snapshot = copy.deepcopy(state.active_config)
        start_room(room_id, config_snapshot)
        return jsonify({"ok": True})

    @app.post("/api/restart-all")
    def api_restart_all():
        with state.lock:
            config_snapshot = copy.deepcopy(state.active_config)
        start_all(config_snapshot)
        return jsonify({"ok": True})

    start_all(initial_config)

    browser_host = "localhost" if args.host in {"0.0.0.0", "127.0.0.1"} else args.host
    url = f"http://{browser_host}:{args.port}"

    print(f"\nFloor Layout Planner kjører på: {url}")
    print("Trykk Ctrl+C for å stoppe serveren.")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    app.run(
        host=args.host,
        port=args.port,
        debug=False,
        threaded=True,
        use_reloader=False,
    )


if __name__ == "__main__":
    try:
        main()
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"FEIL: {exc}") from exc
