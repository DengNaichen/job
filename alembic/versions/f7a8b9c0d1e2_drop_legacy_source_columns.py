"""drop_legacy_source_columns

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-03-02 18:25:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(sa.text("DROP INDEX IF EXISTS ix_job_source"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_job_source_status_last_seen_at"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_syncrun_source"))

    op.drop_column("job", "source")
    op.drop_column("syncrun", "source")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("job", sa.Column("source", sa.String(length=255), nullable=True))
    op.add_column("syncrun", sa.Column("source", sa.String(length=255), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE job AS j
            SET source = (s.platform::text || ':' || s.identifier)
            FROM sources AS s
            WHERE s.id = j.source_id
              AND (j.source IS NULL OR btrim(j.source) = '')
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE syncrun AS r
            SET source = (s.platform::text || ':' || s.identifier)
            FROM sources AS s
            WHERE s.id = r.source_id
              AND (r.source IS NULL OR btrim(r.source) = '')
            """
        )
    )

    op.alter_column("job", "source", nullable=False)
    op.alter_column("syncrun", "source", nullable=False)

    op.create_index("ix_job_source", "job", ["source"], unique=False)
    op.create_index(
        "ix_job_source_status_last_seen_at",
        "job",
        ["source", "status", "last_seen_at"],
        unique=False,
    )
    op.create_index("ix_syncrun_source", "syncrun", ["source"], unique=False)
