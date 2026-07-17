#!/usr/bin/env python3
from __future__ import annotations

import argparse
import cProfile
import json
import pstats
import statistics
import time
from pathlib import Path
from typing import Any

from floor_layout_planner.candidate_evaluator import (
    evaluate_candidate_fast,
    evaluate_candidate_full,
)
from floor_layout_planner.geometry import build_floor_polygon
from floor_layout_planner.optimizer import build_candidate_inputs
from floor_layout_planner.planner import create_plan

DEFAULT_SETTINGS = {
    "orientation": "horizontal",
    "start_corner": "upper_left",
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


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    if "rooms" not in config and "rectangles" in config:
        config = {
            "project_name": config.get("section_name", "Floor Project"),
            "board": config["board"],
            "settings": config.get("settings", {}),
            "rooms": [
                {
                    "id": "room_1",
                    "name": config.get("section_name", "Room 1"),
                    "origin": {"x": 0, "y": 0},
                    "rectangles": config["rectangles"],
                    "settings": {},
                }
            ],
        }

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


def local_floor(
    project_config: dict[str, Any],
    room: dict[str, Any],
):
    settings = merged_settings(project_config, room)
    return build_floor_polygon(
        room["rectangles"],
        float(settings["expansion_gap_mm"]),
    )


def room_by_selector(
    config: dict[str, Any],
    selector: str,
) -> dict[str, Any]:
    for room in config["rooms"]:
        if room["id"] == selector or room["name"] == selector:
            return room

    raise ValueError(f"Unknown room selector: {selector}")


def benchmark_plan(
    *,
    config: dict[str, Any],
    room: dict[str, Any],
    repeat: int,
) -> list[float]:
    settings = merged_settings(config, room)
    board = config["board"]
    floor = local_floor(config, room)
    durations = []

    for _ in range(repeat):
        started = time.perf_counter()
        create_plan(
            floor=floor,
            board_length=float(board["length_mm"]),
            board_width=float(board["width_mm"]),
            orientation=settings["orientation"],
            start_corner=settings["start_corner"],
            stagger_step=float(settings["stagger_step_mm"]),
            minimum_piece_length=float(settings["minimum_piece_length_mm"]),
        )
        durations.append(time.perf_counter() - started)

    return durations


def candidate_sample(
    *,
    config: dict[str, Any],
    room: dict[str, Any],
    sample_size: int,
):
    settings = merged_settings(config, room)
    board = config["board"]
    floor = local_floor(config, room)
    inputs = build_candidate_inputs(
        floor=floor,
        board_length=float(board["length_mm"]),
        board_width=float(board["width_mm"]),
        orientation=settings["orientation"],
        start_corner=settings["start_corner"],
        stagger_step=float(settings["stagger_step_mm"]),
        minimum_piece_length=float(settings["minimum_piece_length_mm"]),
        minimum_joint_distance=float(settings["minimum_joint_distance_mm"]),
        minimum_row_width=float(settings["minimum_row_width_mm"]),
        preferred_minimum_row_width=float(settings["preferred_minimum_row_width_mm"]),
        optimization_step=float(settings["optimization_step_mm"]),
        row_width_optimization_step=float(settings["row_width_optimization_step_mm"]),
    )
    return inputs[: max(1, min(sample_size, len(inputs)))]


def benchmark_candidates(
    *,
    config: dict[str, Any],
    room: dict[str, Any],
    sample_size: int,
    evaluator,
) -> list[float]:
    durations = []

    for item in candidate_sample(
        config=config,
        room=room,
        sample_size=sample_size,
    ):
        started = time.perf_counter()
        evaluator(item)
        durations.append(time.perf_counter() - started)

    return durations


def print_summary(
    *,
    label: str,
    durations: list[float],
) -> None:
    summary = summarize_durations(durations)

    print(label)
    print(f"  runs:   {summary['runs']}")
    print(f"  mean:   {summary['mean_ms']:.2f} ms")
    print(f"  median: {summary['median_ms']:.2f} ms")
    print(f"  min:    {summary['min_ms']:.2f} ms")
    print(f"  max:    {summary['max_ms']:.2f} ms")


def summarize_durations(
    durations: list[float],
) -> dict[str, float]:
    average = statistics.fmean(durations)
    median = statistics.median(durations)
    minimum = min(durations)
    maximum = max(durations)

    return {
        "runs": float(len(durations)),
        "mean_ms": average * 1000,
        "median_ms": median * 1000,
        "min_ms": minimum * 1000,
        "max_ms": maximum * 1000,
    }


def print_comparison(
    *,
    label: str,
    baseline: list[float],
    candidate: list[float],
) -> None:
    baseline_summary = summarize_durations(baseline)
    candidate_summary = summarize_durations(candidate)

    def delta_percent(key: str) -> float:
        baseline_value = baseline_summary[key]
        candidate_value = candidate_summary[key]

        if abs(baseline_value) < 1e-12:
            return 0.0

        return 100.0 * (candidate_value - baseline_value) / baseline_value

    print(label)
    print(
        "  mean:   "
        f"{baseline_summary['mean_ms']:.2f} ms -> "
        f"{candidate_summary['mean_ms']:.2f} ms "
        f"({delta_percent('mean_ms'):+.1f}%)"
    )
    print(
        "  median: "
        f"{baseline_summary['median_ms']:.2f} ms -> "
        f"{candidate_summary['median_ms']:.2f} ms "
        f"({delta_percent('median_ms'):+.1f}%)"
    )
    print(
        "  min:    "
        f"{baseline_summary['min_ms']:.2f} ms -> "
        f"{candidate_summary['min_ms']:.2f} ms "
        f"({delta_percent('min_ms'):+.1f}%)"
    )
    print(
        "  max:    "
        f"{baseline_summary['max_ms']:.2f} ms -> "
        f"{candidate_summary['max_ms']:.2f} ms "
        f"({delta_percent('max_ms'):+.1f}%)"
    )


def profile_call(
    *,
    label: str,
    function,
    sort_by: str,
    top_n: int,
    output: Path | None,
) -> None:
    profiler = cProfile.Profile()
    profiler.enable()
    function()
    profiler.disable()

    print(f"\nProfile: {label}")
    stats = pstats.Stats(profiler).sort_stats(sort_by)
    stats.print_stats(top_n)

    if output is not None:
        profiler.dump_stats(str(output))
        print(f"Saved profile to {output}")


def resolve_rooms(
    *,
    config: dict[str, Any],
    selectors: list[str] | None,
) -> list[dict[str, Any]]:
    if selectors:
        return [room_by_selector(config, selector) for selector in selectors]

    return config["rooms"]


def run_mode(
    *,
    config: dict[str, Any],
    room: dict[str, Any],
    mode: str,
    repeat: int,
    sample_size: int,
    profile: bool,
    sort_by: str,
    top_n: int,
    profile_output: Path | None,
) -> None:
    title = f"{room['name']} ({room['id']})"

    if mode == "plan":
        durations = benchmark_plan(
            config=config,
            room=room,
            repeat=repeat,
        )
        print_summary(label=f"{title} - plan", durations=durations)

        if profile:
            profile_call(
                label=f"{title} - plan",
                function=lambda: benchmark_plan(
                    config=config,
                    room=room,
                    repeat=1,
                ),
                sort_by=sort_by,
                top_n=top_n,
                output=profile_output,
            )
        return

    evaluator = evaluate_candidate_fast if mode == "coarse" else evaluate_candidate_full
    durations = benchmark_candidates(
        config=config,
        room=room,
        sample_size=sample_size,
        evaluator=evaluator,
    )
    print_summary(label=f"{title} - {mode}", durations=durations)

    if profile:
        items = candidate_sample(
            config=config,
            room=room,
            sample_size=1,
        )
        profile_call(
            label=f"{title} - {mode}",
            function=lambda: evaluator(items[0]),
            sort_by=sort_by,
            top_n=top_n,
            output=profile_output,
        )


def collect_durations(
    *,
    config: dict[str, Any],
    room: dict[str, Any],
    mode: str,
    repeat: int,
    sample_size: int,
) -> list[float]:
    if mode == "plan":
        return benchmark_plan(
            config=config,
            room=room,
            repeat=repeat,
        )

    evaluator = evaluate_candidate_fast if mode == "coarse" else evaluate_candidate_full
    return benchmark_candidates(
        config=config,
        room=room,
        sample_size=sample_size,
        evaluator=evaluator,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark and profile the laying engine.",
    )
    parser.add_argument("config", type=Path, help="Project JSON file")
    parser.add_argument(
        "--compare-config",
        type=Path,
        help="Optional second project JSON to compare against the primary config.",
    )
    parser.add_argument(
        "--room",
        action="append",
        dest="rooms",
        help="Room id or name. Repeat to benchmark multiple rooms.",
    )
    parser.add_argument(
        "--mode",
        choices=("plan", "coarse", "refine"),
        default="plan",
        help="What to benchmark.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=10,
        help="Number of repeated plan runs in plan mode.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=10,
        help="Number of candidate evaluations in coarse/refine mode.",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Run cProfile on one representative execution.",
    )
    parser.add_argument(
        "--profile-sort",
        default="cumtime",
        help="pstats sort key, for example cumtime or tottime.",
    )
    parser.add_argument(
        "--profile-top",
        type=int,
        default=20,
        help="Number of profile rows to print.",
    )
    parser.add_argument(
        "--profile-output",
        type=Path,
        help="Optional .prof output path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    compare_config = (
        load_config(args.compare_config) if args.compare_config is not None else None
    )
    rooms = resolve_rooms(
        config=config,
        selectors=args.rooms,
    )

    print(f"Project: {config.get('project_name', args.config.stem)}")
    print(f"Mode: {args.mode}")
    if compare_config is not None:
        print(
            "Compare Against: "
            f"{compare_config.get('project_name', args.compare_config.stem)}"
        )
    print()

    for index, room in enumerate(rooms):
        if index > 0:
            print()

        compare_room = None
        if compare_config is not None:
            compare_room = room_by_selector(
                compare_config,
                room["id"],
            )

        output = None
        if args.profile_output is not None:
            suffix = f".{room['id']}.{args.mode}.prof"
            output = args.profile_output.with_suffix(
                args.profile_output.suffix + suffix
                if args.profile_output.suffix
                else suffix
            )

        if compare_room is None:
            run_mode(
                config=config,
                room=room,
                mode=args.mode,
                repeat=max(1, args.repeat),
                sample_size=max(1, args.sample_size),
                profile=args.profile,
                sort_by=args.profile_sort,
                top_n=max(1, args.profile_top),
                profile_output=output,
            )
            continue

        baseline = collect_durations(
            config=config,
            room=room,
            mode=args.mode,
            repeat=max(1, args.repeat),
            sample_size=max(1, args.sample_size),
        )
        candidate = collect_durations(
            config=compare_config,
            room=compare_room,
            mode=args.mode,
            repeat=max(1, args.repeat),
            sample_size=max(1, args.sample_size),
        )
        title = f"{room['name']} ({room['id']}) - {args.mode}"

        print_summary(label=f"{title} - baseline", durations=baseline)
        print_summary(label=f"{title} - candidate", durations=candidate)
        print_comparison(
            label=f"{title} - delta",
            baseline=baseline,
            candidate=candidate,
        )

        if args.profile:
            print("\nProfile is only run for the primary config in compare mode.")
            run_mode(
                config=config,
                room=room,
                mode=args.mode,
                repeat=max(1, args.repeat),
                sample_size=max(1, args.sample_size),
                profile=True,
                sort_by=args.profile_sort,
                top_n=max(1, args.profile_top),
                profile_output=output,
            )


if __name__ == "__main__":
    main()
