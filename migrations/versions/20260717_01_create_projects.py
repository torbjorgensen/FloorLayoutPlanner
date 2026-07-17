"""Create the initial projects table.

Revision ID: 20260717_01
Revises:
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260717_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create durable versioned project snapshots."""
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_archived", "projects", ["archived"])
    op.create_index("ix_projects_name", "projects", ["name"])


def downgrade() -> None:
    """Remove project persistence data when explicitly downgrading."""
    op.drop_index("ix_projects_name", table_name="projects")
    op.drop_index("ix_projects_archived", table_name="projects")
    op.drop_table("projects")
