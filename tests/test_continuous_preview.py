from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from pergo_planner.models import Candidate, CutPlan
from pergo_planner.planner import Piece
from pergo_planner.web.state import ProjectState
from pergo_planner.web.workers import create_worker_manager


def _candidate(attempt: int, score: int) -> Candidate:
    piece = Piece(
        row=1,
        segment=1,
        piece=1,
        x1=0,
        x2=500,
        y1=0,
        y2=193,
        length=500,
        width=193,
        source_board_index=attempt,
        physical_board_id=f"B{attempt:05d}",
        is_full_length=False,
    )
    return Candidate(
        attempt=attempt,
        total_attempts=4,
        phase="coarse",
        base_offset=float(attempt),
        row_width_offset=0,
        pieces=[piece],
        short_count=0,
        very_short_count=0,
        shortest_piece=500,
        joint_violations=0,
        narrow_row_count=0,
        very_narrow_row_count=0,
        narrowest_row_width=193,
        row_offsets={},
        score=(score,),
        timings={},
    )


def test_continuous_previews_publish_best_candidate_at_bounded_cadence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = (
        Path(__file__).resolve().parents[1] / "examples/continuous_horizontal.json"
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["settings"]["preview_every_n_results"] = 2
    config["settings"]["local_optimize_top_n"] = 1
    config["settings"]["optimizer_workers"] = 1
    coarse = [_candidate(1, 3), _candidate(2, 1), _candidate(3, 2)]
    refined = [_candidate(4, 0)]

    monkeypatch.setattr(
        "pergo_planner.web.workers.build_candidate_inputs",
        lambda **_kwargs: [
            SimpleNamespace(base_offset=float(index), row_width_offset=0)
            for index in range(1, 4)
        ],
    )

    monkeypatch.setattr(
        "pergo_planner.web.workers.parallel_coarse_generator",
        lambda **_kwargs: iter(copy.deepcopy(coarse)),
    )
    monkeypatch.setattr(
        "pergo_planner.web.workers.parallel_refine_generator",
        lambda **_kwargs: iter(copy.deepcopy(refined)),
    )
    cut_plan = CutPlan(
        connection_id="living_kitchen",
        axis="y",
        position_mm=4000,
        gap_width_mm=5,
        method="natural_joint",
        cut_boards=0,
        short_fragments=0,
        very_short_fragments=0,
        narrow_fragments=0,
        very_narrow_fragments=0,
        shortest_fragment_mm=500,
        narrowest_fragment_mm=193,
        center_distance_mm=0,
        score=(0,),
    )
    monkeypatch.setattr(
        "pergo_planner.web.workers.best_cut_plan",
        lambda *_args, **_kwargs: cut_plan,
    )

    def split_preview(*, candidate, connection, **_kwargs):
        return {
            connection.room_a: copy.deepcopy(candidate.pieces),
            connection.room_b: copy.deepcopy(candidate.pieces),
        }

    monkeypatch.setattr(
        "pergo_planner.web.workers.split_candidate_at_cut",
        split_preview,
    )
    monkeypatch.setattr(
        "pergo_planner.web.workers.write_piece_csv", lambda *_args: None
    )
    monkeypatch.setattr("pergo_planner.web.workers.plot_plan", lambda **_kwargs: None)

    state = ProjectState(config)
    snapshots: list[tuple[str, int, int]] = []

    def notify() -> None:
        continuous = state.continuous["living_kitchen"]
        if continuous.provisional and continuous.current is not None:
            snapshots.append(
                (
                    str(continuous.profile["phase"]),
                    int(continuous.profile["completed"]),
                    continuous.current.attempt,
                )
            )

    manager = create_worker_manager(state, tmp_path, notify)
    manager.start_all(config)
    deadline = time.monotonic() + 3
    continuous = state.continuous["living_kitchen"]
    while not continuous.finished and time.monotonic() < deadline:
        time.sleep(0.01)
    manager.shutdown()

    assert continuous.finished
    coarse_snapshots = [item for item in snapshots if item[0] == "coarse"]
    assert coarse_snapshots == [("coarse", 2, 2), ("coarse", 3, 2)]
    assert ("refine", 4, 4) in snapshots
    assert continuous.current.attempt == 4
    assert continuous.provisional is False
