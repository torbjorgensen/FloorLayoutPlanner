from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pergo_planner.web.app import PlannerApplication, create_app
from pergo_planner.web.config import load_config


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


@pytest.fixture
def client(runtime: PlannerApplication):
    return runtime.app.test_client()


def seeded_project(client) -> dict:
    response = client.get("/api/projects")
    assert response.status_code == 200
    projects = response.get_json()["projects"]
    assert len(projects) == 1
    return projects[0]


def test_startup_project_is_seeded_and_can_be_opened(client, config_path: Path) -> None:
    project = seeded_project(client)

    response = client.get(f"/api/projects/{project['id']}")

    assert response.status_code == 200
    assert response.get_json()["project"]["config"] == load_config(config_path)
    assert project["optimization_status"] == "not_started"


def test_restart_does_not_replace_existing_database_projects(
    config_path: Path, tmp_path: Path
) -> None:
    database_url = f"sqlite:///{tmp_path / 'persistent.db'}"
    first = create_app(config_path, start_workers=False, database_url=database_url)
    stored = first.projects.list()[0]
    renamed = first.projects.rename(
        stored.id, "Database version", expected_version=stored.version
    )
    first.shutdown()

    file_config = load_config(config_path)
    file_config["project_name"] = "Changed file version"
    config_path.write_text(json.dumps(file_config), encoding="utf-8")
    second = create_app(config_path, start_workers=False, database_url=database_url)

    try:
        projects = second.projects.list()
        assert len(projects) == 1
        assert projects[0].id == renamed.id
        assert projects[0].name == "Database version"
    finally:
        second.shutdown()


def test_create_rename_and_stale_update_conflict(client, config_path: Path) -> None:
    config = load_config(config_path)
    config["project_name"] = "Second project"
    created_response = client.post("/api/projects", json={"config": config})
    created = created_response.get_json()["project"]

    assert created_response.status_code == 201
    assert created["version"] == 1

    rename_response = client.patch(
        f"/api/projects/{created['id']}",
        json={"name": "Renamed", "expected_version": created["version"]},
    )
    renamed = rename_response.get_json()["project"]

    assert rename_response.status_code == 200
    assert renamed["name"] == "Renamed"
    assert renamed["config"]["project_name"] == "Renamed"
    assert renamed["version"] == 2

    stale_response = client.patch(
        f"/api/projects/{created['id']}",
        json={"name": "Stale", "expected_version": created["version"]},
    )

    assert stale_response.status_code == 409
    assert "changed" in stale_response.get_json()["error"]


def test_archive_restore_and_permanent_delete_are_versioned(client) -> None:
    project = seeded_project(client)

    archive_response = client.post(
        f"/api/projects/{project['id']}/archive",
        json={"expected_version": project["version"]},
    )
    archived = archive_response.get_json()["project"]

    assert archived["archived"]
    assert client.get("/api/projects").get_json()["projects"] == []
    assert (
        len(client.get("/api/projects?include_archived=true").get_json()["projects"])
        == 1
    )

    restore_response = client.post(
        f"/api/projects/{project['id']}/restore",
        json={"expected_version": archived["version"]},
    )
    restored = restore_response.get_json()["project"]

    assert not restored["archived"]
    unsafe_delete = client.delete(
        f"/api/projects/{project['id']}",
        json={"expected_version": restored["version"]},
    )
    assert unsafe_delete.status_code == 400

    rearchive_response = client.post(
        f"/api/projects/{project['id']}/archive",
        json={"expected_version": restored["version"]},
    )
    rearchived = rearchive_response.get_json()["project"]
    delete_response = client.delete(
        f"/api/projects/{project['id']}",
        json={"expected_version": rearchived["version"]},
    )
    assert delete_response.status_code == 200
    assert client.get(f"/api/projects/{project['id']}").status_code == 404


def test_duplicate_copies_a_current_snapshot(client) -> None:
    project = seeded_project(client)

    response = client.post(
        f"/api/projects/{project['id']}/duplicate",
        json={"expected_version": project["version"], "name": "Upstairs"},
    )
    duplicate = response.get_json()["project"]

    assert response.status_code == 201
    assert duplicate["id"] != project["id"]
    assert duplicate["name"] == "Upstairs"
    assert duplicate["config"]["project_name"] == "Upstairs"
    assert len(client.get("/api/projects").get_json()["projects"]) == 2


def test_json_import_and_export_round_trip_without_setting_loss(
    client, config_path: Path
) -> None:
    imported_config = load_config(config_path)
    imported_config["project_name"] = "Imported / Exported"

    import_response = client.post("/api/projects/import", json=imported_config)
    imported = import_response.get_json()["project"]
    export_response = client.get(f"/api/projects/{imported['id']}/export")

    assert import_response.status_code == 201
    assert export_response.status_code == 200
    assert json.loads(export_response.text) == imported_config
    assert export_response.headers["Content-Disposition"].endswith(
        'filename="Imported___Exported.json"'
    )


def test_invalid_import_cannot_create_or_replace_projects(client) -> None:
    initial = seeded_project(client)
    stored = client.get(f"/api/projects/{initial['id']}").get_json()["project"]
    invalid = copy.deepcopy(stored["config"])
    invalid["rooms"] = []

    response = client.post("/api/projects/import", json=invalid)

    assert response.status_code == 400
    assert "non-empty" in response.get_json()["error"]
    projects = client.get("/api/projects").get_json()["projects"]
    assert [project["id"] for project in projects] == [initial["id"]]


@pytest.mark.parametrize("expected_version", [None, 0, True, "invalid"])
def test_mutations_require_a_positive_integer_version(
    client, expected_version: object
) -> None:
    project = seeded_project(client)

    response = client.patch(
        f"/api/projects/{project['id']}",
        json={"name": "No version", "expected_version": expected_version},
    )

    assert response.status_code == 400
    assert "expected_version" in response.get_json()["error"]
