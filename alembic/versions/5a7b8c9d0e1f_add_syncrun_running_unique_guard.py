"""add partial unique index to guard one running syncrun per source

Revision ID: 5a7b8c9d0e1f
Revises: 2f901e544b79
Create Date: 2026-03-02
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5a7b8c9d0e1f"
down_revision: str | Sequence[str] | None = "2f901e544b79"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    duplicate_running = conn.execute(
        sa.text(
            """
            SELECT source_id, COUNT(*)
            FROM syncrun
            WHERE status = 'running' AND source_id IS NOT NULL
            GROUP BY source_id
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    if duplicate_running:
        raise RuntimeError(
            "Cannot create unique running sync index: duplicate running syncrun rows exist. "
            f"duplicates={duplicate_running}"
        )

    op.create_index(
        "uq_syncrun_running_source_id",
        "syncrun",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running' AND source_id IS NOT NULL"),
        sqlite_where=sa.text("status = 'running' AND source_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_syncrun_running_source_id", table_name="syncrun")
