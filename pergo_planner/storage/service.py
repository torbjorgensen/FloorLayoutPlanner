"""Validated project persistence service."""

from __future__ import annotations

import copy
from typing import Any

from pergo_planner.storage.repository import (
    ProjectConflictError,
    ProjectRecord,
    ProjectRepository,
)
from pergo_planner.web.config import normalize_and_validate_config


class ProjectService:
    """Validate configurations before crossing the persistence boundary."""

    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    def close(self) -> None:
        """Release database resources held by the persistence layer."""
        self._repository.close()

    def create(
        self, config: dict[str, Any], *, project_id: str | None = None
    ) -> ProjectRecord:
        validated = normalize_and_validate_config(copy.deepcopy(config))
        return self._repository.create(validated, project_id=project_id)

    def update(
        self,
        project_id: str,
        config: dict[str, Any],
        *,
        expected_version: int,
    ) -> ProjectRecord:
        validated = normalize_and_validate_config(copy.deepcopy(config))
        return self._repository.update(
            project_id, validated, expected_version=expected_version
        )

    def get(self, project_id: str) -> ProjectRecord:
        return self._repository.get(project_id)

    def duplicate(
        self, project_id: str, *, expected_version: int, name: str | None = None
    ) -> ProjectRecord:
        """Copy a current project snapshot under a new stable identifier."""
        source = self.get(project_id)
        if source.version != expected_version:
            raise ProjectConflictError(
                f"Project {project_id} changed since it was last loaded."
            )
        config = copy.deepcopy(source.config)
        config["project_name"] = name or f"{source.name} Copy"
        return self.create(config)

    def rename(
        self, project_id: str, name: str, *, expected_version: int
    ) -> ProjectRecord:
        """Rename both project metadata and its portable configuration."""
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Project name cannot be empty.")
        current = self.get(project_id)
        config = copy.deepcopy(current.config)
        config["project_name"] = normalized_name
        return self.update(project_id, config, expected_version=expected_version)

    def list(self, *, include_archived: bool = False) -> list[ProjectRecord]:
        return self._repository.list(include_archived=include_archived)

    def set_archived(
        self, project_id: str, archived: bool, *, expected_version: int
    ) -> ProjectRecord:
        return self._repository.set_archived(
            project_id, archived, expected_version=expected_version
        )

    def delete(self, project_id: str, *, expected_version: int) -> None:
        current = self.get(project_id)
        if current.version != expected_version:
            raise ProjectConflictError(
                f"Project {project_id} changed since it was last loaded."
            )
        if not current.archived:
            raise ValueError("Archive the project before permanently deleting it.")
        self._repository.delete(project_id, expected_version=expected_version)
