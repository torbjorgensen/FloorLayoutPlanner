"""Application lifecycle helpers for project persistence."""

from __future__ import annotations

from floor_layout_planner.storage.database import (
    create_database_engine,
    create_session_factory,
)
from floor_layout_planner.storage.migrations import upgrade_database
from floor_layout_planner.storage.repository import ProjectRepository
from floor_layout_planner.storage.service import ProjectService


def initialize_project_storage(database_url: str) -> ProjectService:
    """Upgrade configured storage and expose its database-neutral service."""
    upgrade_database(database_url)
    engine = create_database_engine(database_url)
    sessions = create_session_factory(engine)
    return ProjectService(ProjectRepository(sessions))
