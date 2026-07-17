"""SQLAlchemy engine and session configuration."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def create_database_engine(database_url: str) -> Engine:
    """Create an engine with safe SQLite behavior and portable defaults."""
    engine = create_engine(database_url, pool_pre_ping=True)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _record) -> None:
            # Foreign keys are disabled by default for every SQLite connection.
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return short-lived sessions that keep loaded values after commit."""
    return sessionmaker(bind=engine, expire_on_commit=False)
