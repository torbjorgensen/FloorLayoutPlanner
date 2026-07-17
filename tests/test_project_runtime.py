from __future__ import annotations

import copy
from pathlib import Path

import pytest

from pergo_planner.web.app import PlannerApplication, create_app
from pergo_planner.web.config import editable_room_settings
from pergo_planner.web.sockets import STATE_EVENT


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[1] / "examples" / "example_project.json"
    destination = tmp_path / "project.json"
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return destination


@pytest.fixture
def runtime(config_path: Path, tmp_path: Path) -> PlannerApplication:
    application = create_app(
        config_path,
        start_workers=False,
        database_url=f"sqlite:///{tmp_path / 'projects.db'}",
    )
    yield application
    application.shutdown()


def create_second_project(application: PlannerApplication) -> tuple[str, dict]:
    config = copy.deepcopy(application.projects.list()[0].config)
    config["project_name"] = "Second project"
    created = application.projects.create(config)
    return created.id, config


def initial_payload(client) -> dict:
    received = client.get_received()
    assert received[0]["name"] == STATE_EVENT
    return received[0]["args"][0]


def test_socket_clients_receive_only_their_selected_project(
    runtime: PlannerApplication,
) -> None:
    first = runtime.projects.list()[0]
    second_id, _ = create_second_project(runtime)

    first_client = runtime.socketio.test_client(
        runtime.app, auth={"project_id": first.id}
    )
    second_client = runtime.socketio.test_client(
        runtime.app, auth={"project_id": second_id}
    )

    first_payload = initial_payload(first_client)
    second_payload = initial_payload(second_client)
    assert first_payload["project_id"] == first.id
    assert second_payload["project_id"] == second_id

    first_runtime = runtime.runtimes.get(first.id)
    first_runtime.emitter.minimum_interval_s = 0
    with first_runtime.state.lock:
        first_runtime.state.rooms["stue"].paused = True
    first_runtime.emitter.notify()

    update = initial_payload(first_client)
    assert update["project_id"] == first.id
    assert second_client.get_received() == []


def test_unknown_and_archived_projects_cannot_open_socket_runtime(
    runtime: PlannerApplication,
) -> None:
    unknown = runtime.socketio.test_client(runtime.app, auth={"project_id": "missing"})
    assert not unknown.is_connected()

    project = runtime.projects.list()[0]
    runtime.projects.set_archived(project.id, True, expected_version=project.version)
    archived = runtime.socketio.test_client(
        runtime.app, auth={"project_id": project.id}
    )
    assert not archived.is_connected()


def test_runtime_outputs_and_commands_are_project_scoped(
    runtime: PlannerApplication,
) -> None:
    first = runtime.projects.list()[0]
    second_id, _ = create_second_project(runtime)
    client = runtime.app.test_client()

    first_response = client.post(f"/api/projects/{first.id}/runtime/room/stue/pause")

    assert first_response.status_code == 200
    assert runtime.runtimes.get(first.id).state.rooms["stue"].paused
    assert not runtime.runtimes.get(second_id).state.rooms["stue"].paused
    assert runtime.runtimes.get(first.id).output_dir.name == first.id
    assert runtime.runtimes.get(second_id).output_dir.name == second_id


def test_runtime_keeps_the_snapshot_version_it_started_with(
    runtime: PlannerApplication,
) -> None:
    project = runtime.projects.list()[0]
    allocated = runtime.runtimes.get(project.id)
    external = copy.deepcopy(project.config)
    external["project_name"] = "New stored name"

    updated = runtime.projects.update(
        project.id, external, expected_version=project.version
    )

    assert updated.version == 2
    assert allocated.project_version == 1
    assert allocated.state.active_config["project_name"] == project.name


def test_scoped_save_updates_database_version_and_rejects_stale_runtime(
    runtime: PlannerApplication,
) -> None:
    project = runtime.projects.list()[0]
    project_runtime = runtime.runtimes.get(project.id)
    room = project.config["rooms"][0]
    payload = editable_room_settings(project.config, room)
    payload["saw_kerf_mm"] = 2.7
    client = runtime.app.test_client()

    response = client.post(
        f"/api/projects/{project.id}/runtime/room/{room['id']}/save",
        json=payload,
    )

    assert response.status_code == 200
    assert project_runtime.project_version == 2
    assert runtime.projects.get(project.id).config["board"]["saw_kerf_mm"] == 2.7

    external = copy.deepcopy(runtime.projects.get(project.id).config)
    external["project_name"] = "External edit"
    runtime.projects.update(project.id, external, expected_version=2)
    stale_response = client.post(
        f"/api/projects/{project.id}/runtime/room/{room['id']}/save",
        json=payload,
    )

    assert stale_response.status_code == 409


def test_archiving_discards_allocated_runtime(runtime: PlannerApplication) -> None:
    project = runtime.projects.list()[0]
    socket_client = runtime.socketio.test_client(
        runtime.app, auth={"project_id": project.id}
    )
    socket_client.get_received()
    assert project.id in runtime.runtimes.active_project_ids()

    response = runtime.app.test_client().post(
        f"/api/projects/{project.id}/archive",
        json={"expected_version": project.version},
    )

    assert response.status_code == 200
    assert project.id not in runtime.runtimes.active_project_ids()
    assert not socket_client.is_connected()

    command = runtime.app.test_client().post(
        f"/api/projects/{project.id}/runtime/restart-all"
    )
    assert command.status_code == 404
