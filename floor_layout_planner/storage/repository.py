"""Repository operations for durable project snapshots."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from floor_layout_planner.storage.models import ProjectModel


class ProjectNotFoundError(LookupError):
    """Raised when a stable project identifier does not exist."""


class ProjectConflictError(RuntimeError):
    """Raised when an update was based on a stale project version."""


@dataclass(frozen=True)
class ProjectRecord:
    """Database-independent project value returned to application services."""

    id: str
    name: str
    config: dict[str, Any]
    version: int
    archived: bool
    created_at: datetime
    updated_at: datetime


class ProjectRepository:
    """Persist project snapshots without exposing ORM objects to callers."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def close(self) -> None:
        """Release pooled database connections owned by this repository."""
        engine = self._sessions.kw.get("bind")
        if engine is not None:
            engine.dispose()

    @staticmethod
    def _record(model: ProjectModel) -> ProjectRecord:
        return ProjectRecord(
            id=model.id,
            name=model.name,
            config=copy.deepcopy(model.config),
            version=model.version,
            archived=model.archived,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def create(
        self, config: dict[str, Any], *, project_id: str | None = None
    ) -> ProjectRecord:
        """Create a project using a caller-provided or generated stable ID."""
        model = ProjectModel(
            id=project_id or str(uuid4()),
            name=str(config["project_name"]),
            config=copy.deepcopy(config),
        )
        with self._sessions.begin() as session:
            session.add(model)
        return self._record(model)

    def get(self, project_id: str) -> ProjectRecord:
        """Load one project or raise a domain-level not-found error."""
        with self._sessions() as session:
            model = session.get(ProjectModel, project_id)
            if model is None:
                raise ProjectNotFoundError(f"Unknown project id: {project_id}")
            return self._record(model)

    def list(self, *, include_archived: bool = False) -> list[ProjectRecord]:
        """List projects with recently updated projects first."""
        statement = select(ProjectModel)
        if not include_archived:
            statement = statement.where(ProjectModel.archived.is_(False))
        statement = statement.order_by(ProjectModel.updated_at.desc(), ProjectModel.id)
        with self._sessions() as session:
            return [self._record(model) for model in session.scalars(statement)]

    def update(
        self,
        project_id: str,
        config: dict[str, Any],
        *,
        expected_version: int,
    ) -> ProjectRecord:
        """Atomically replace a snapshot if its version is still current."""
        statement = (
            update(ProjectModel)
            .where(
                ProjectModel.id == project_id,
                ProjectModel.version == expected_version,
            )
            .values(
                name=str(config["project_name"]),
                config=copy.deepcopy(config),
                version=ProjectModel.version + 1,
                updated_at=datetime.now().astimezone(),
            )
        )
        with self._sessions.begin() as session:
            result = session.execute(statement)
            if result.rowcount != 1:
                self._raise_update_error(session, project_id)
        return self.get(project_id)

    def set_archived(
        self, project_id: str, archived: bool, *, expected_version: int
    ) -> ProjectRecord:
        """Archive or restore a project using optimistic concurrency."""
        statement = (
            update(ProjectModel)
            .where(
                ProjectModel.id == project_id,
                ProjectModel.version == expected_version,
            )
            .values(
                archived=archived,
                version=ProjectModel.version + 1,
                updated_at=datetime.now().astimezone(),
            )
        )
        with self._sessions.begin() as session:
            result = session.execute(statement)
            if result.rowcount != 1:
                self._raise_update_error(session, project_id)
        return self.get(project_id)

    def delete(self, project_id: str, *, expected_version: int) -> None:
        """Permanently delete a project only when explicitly requested."""
        statement = delete(ProjectModel).where(
            ProjectModel.id == project_id,
            ProjectModel.version == expected_version,
        )
        with self._sessions.begin() as session:
            result = session.execute(statement)
            if result.rowcount != 1:
                self._raise_update_error(session, project_id)

    @staticmethod
    def _raise_update_error(session: Session, project_id: str) -> None:
        exists = session.scalar(
            select(ProjectModel.id).where(ProjectModel.id == project_id)
        )
        if exists is None:
            raise ProjectNotFoundError(f"Unknown project id: {project_id}")
        raise ProjectConflictError(
            f"Project {project_id} changed since it was last loaded."
        )
