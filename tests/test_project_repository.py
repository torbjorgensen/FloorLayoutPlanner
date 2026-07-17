from __future__ import annotations

import copy
from pathlib import Path

import pytest
from sqlalchemy import inspect, select

from floor_layout_planner.storage import (
    ProjectConflictError,
    ProjectNotFoundError,
    ProjectRepository,
    ProjectService,
    upgrade_database,
)
from floor_layout_planner.storage.database import (
    create_database_engine,
    create_session_factory,
)
from floor_layout_planner.storage.models import ProjectModel


def project(name: str = "Project") -> dict:
    return {
        "project_name": name,
        "board": {"length_mm": 2050, "width_mm": 240},
        "settings": {},
        "rooms": [
            {
                "id": "room",
                "name": "Room",
                "rectangles": [{"x": 0, "y": 0, "width": 1000, "height": 1000}],
            }
        ],
    }


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'projects.db'}"


@pytest.fixture
def service(database_url: str) -> ProjectService:
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    repository = ProjectRepository(create_session_factory(engine))
    return ProjectService(repository)


def test_migration_creates_versioned_project_schema(database_url: str) -> None:
    upgrade_database(database_url)
    engine = create_database_engine(database_url)

    tables = set(inspect(engine).get_table_names())

    assert tables == {"alembic_version", "projects"}


def test_projects_survive_new_repository_instances(database_url: str) -> None:
    upgrade_database(database_url)
    first_engine = create_database_engine(database_url)
    first = ProjectService(
        ProjectRepository(create_session_factory(first_engine))
    ).create(project("Kitchen"))
    first_engine.dispose()

    second_engine = create_database_engine(database_url)
    second_service = ProjectService(
        ProjectRepository(create_session_factory(second_engine))
    )

    restored = second_service.get(first.id)

    assert restored.name == "Kitchen"
    assert restored.config == project("Kitchen")
    assert restored.version == 1


def test_projects_are_isolated_and_return_detached_snapshots(
    service: ProjectService,
) -> None:
    first = service.create(project("First"))
    second = service.create(project("Second"))

    first.config["project_name"] = "Changed outside repository"

    assert service.get(first.id).name == "First"
    assert service.get(second.id).name == "Second"
    assert {item.id for item in service.list()} == {first.id, second.id}


def test_stale_updates_cannot_overwrite_newer_snapshots(
    service: ProjectService,
) -> None:
    created = service.create(project())
    first_edit = copy.deepcopy(created.config)
    first_edit["project_name"] = "First edit"
    updated = service.update(created.id, first_edit, expected_version=created.version)

    stale_edit = copy.deepcopy(created.config)
    stale_edit["project_name"] = "Stale edit"
    with pytest.raises(ProjectConflictError, match="changed"):
        service.update(created.id, stale_edit, expected_version=created.version)

    assert service.get(created.id).name == "First edit"
    assert updated.version == 2


def test_invalid_updates_preserve_last_valid_snapshot(service: ProjectService) -> None:
    created = service.create(project())
    invalid = copy.deepcopy(created.config)
    invalid["rooms"] = []

    with pytest.raises(ValueError, match="non-empty"):
        service.update(created.id, invalid, expected_version=created.version)

    assert service.get(created.id).config == created.config
    assert service.get(created.id).version == created.version


def test_archive_is_default_non_destructive_removal(service: ProjectService) -> None:
    created = service.create(project())

    archived = service.set_archived(created.id, True, expected_version=created.version)

    assert archived.archived
    assert service.list() == []
    assert service.list(include_archived=True) == [archived]


def test_delete_requires_current_version(service: ProjectService) -> None:
    created = service.create(project())
    archived = service.set_archived(created.id, True, expected_version=created.version)

    with pytest.raises(ProjectConflictError):
        service.delete(created.id, expected_version=created.version)

    service.delete(created.id, expected_version=archived.version)
    with pytest.raises(ProjectNotFoundError):
        service.get(created.id)


def test_active_project_cannot_be_permanently_deleted(
    service: ProjectService,
) -> None:
    created = service.create(project())

    with pytest.raises(ValueError, match="Archive"):
        service.delete(created.id, expected_version=created.version)

    assert service.get(created.id) == created


def test_service_validation_runs_before_database_insert(
    database_url: str,
) -> None:
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    service = ProjectService(ProjectRepository(sessions))

    with pytest.raises(ValueError, match="missing fields"):
        service.create({"project_name": "Broken"})

    with sessions() as session:
        assert session.scalar(select(ProjectModel.id)) is None
