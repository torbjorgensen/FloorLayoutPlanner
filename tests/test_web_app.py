from __future__ import annotations

from pathlib import Path

import pytest

from pergo_planner.web.app import create_app
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
