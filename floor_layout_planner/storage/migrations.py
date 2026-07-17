"""Programmatic Alembic migration entry points."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade_database(database_url: str, revision: str = "head") -> None:
    """Upgrade a database using the migrations shipped with the application."""
    repository_root = Path(__file__).resolve().parents[2]
    config = Config(str(repository_root / "alembic.ini"))
    config.set_main_option("script_location", str(repository_root / "migrations"))
    # Alembic treats percent signs as interpolation, so escape URL-encoded values.
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(config, revision)
