from __future__ import annotations

import copy
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from pergo_planner.models import Candidate
from pergo_planner.planner import Piece
from pergo_planner.web.app import create_app
from pergo_planner.web.config import load_config
from pergo_planner.web.sockets import STATE_EVENT


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[1] / "examples" / "example_project.json"
    destination = tmp_path / "project.json"
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


def test_app_factory_can_start_without_optimizer_workers(config_path: Path) -> None:
    runtime = create_app(config_path, start_workers=False)

    client = runtime.socketio.test_client(runtime.app)
    received = client.get_received()

    assert received[0]["name"] == STATE_EVENT
    assert received[0]["args"][0]["project_name"]
    assert all(not room.running for room in runtime.state.rooms.values())


def test_unknown_room_commands_return_client_errors(config_path: Path) -> None:
    runtime = create_app(config_path, start_workers=False)
    client = runtime.app.test_client()

    pause = client.post("/api/room/missing/pause")
    restart = client.post("/api/room/missing/restart")

    assert pause.status_code == 404
    assert pause.get_json() == {"ok": False, "error": "Unknown room id: missing"}
    assert restart.status_code == 404


def test_health_endpoint_reports_readiness(config_path: Path) -> None:
    """Health checks must not depend on optimizer workers or frontend assets."""
    runtime = create_app(config_path, start_workers=False)

    response = runtime.app.test_client().get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_app_initializes_configured_project_storage(
    config_path: Path, tmp_path: Path
) -> None:
    """Database storage is optional but migration-managed when configured."""
    database_url = f"sqlite:///{tmp_path / 'projects.db'}"

    runtime = create_app(config_path, start_workers=False, database_url=database_url)

    assert runtime.projects is not None
    stored = runtime.projects.create(load_config(config_path))
    assert runtime.projects.get(stored.id).config == load_config(config_path)


def test_invalid_search_reports_error_without_writing_outputs(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_piece = Piece(
        row=1,
        segment=1,
        piece=1,
        x1=0,
        x2=100,
        y1=0,
        y2=200,
        length=100,
        width=200,
        source_board_index=1,
        physical_board_id="B00001",
        is_full_length=False,
    )
    invalid_candidate = Candidate(
        attempt=1,
        total_attempts=1,
        phase="refine",
        base_offset=0,
        row_width_offset=0,
        pieces=[invalid_piece],
        short_count=1,
        very_short_count=0,
        shortest_piece=100,
        joint_violations=0,
        narrow_row_count=0,
        very_narrow_row_count=0,
        narrowest_row_width=200,
        row_offsets={},
        score=(1, 0, 0, 0, 0, -200, -100),
        timings={},
    )

    def candidates(**_kwargs):
        yield copy.deepcopy(invalid_candidate)

    write_csv = Mock()
    plot_plan = Mock()
    monkeypatch.setattr(
        "pergo_planner.web.workers.parallel_coarse_generator", candidates
    )
    monkeypatch.setattr(
        "pergo_planner.web.workers.parallel_refine_generator", candidates
    )
    monkeypatch.setattr("pergo_planner.web.workers.write_piece_csv", write_csv)
    monkeypatch.setattr("pergo_planner.web.workers.plot_plan", plot_plan)

    runtime = create_app(config_path, start_workers=False)
    room_id = next(iter(runtime.state.rooms))
    response = runtime.app.test_client().post(f"/api/room/{room_id}/restart")

    assert response.status_code == 200
    deadline = time.monotonic() + 2
    while runtime.state.rooms[room_id].running and time.monotonic() < deadline:
        time.sleep(0.01)

    room = runtime.state.rooms[room_id]
    assert not room.running
    assert room.best is None
    assert "No valid layout satisfies the minimum piece length" in (room.error or "")
    write_csv.assert_not_called()
    plot_plan.assert_not_called()
