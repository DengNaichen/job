"""add same-source job uniqueness for snapshot reconcile

Revision ID: e1f2a3b4c5d6
Revises: b9f8c1d4e2a7
Create Date: 2026-02-28 14:30:00.000000

"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | Sequence[str] | None = "b9f8c1d4e2a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_job_source_external_job_id",
        "job",
        ["source", "external_job_id"],
    )
    op.create_index(
        "ix_job_source_status_last_seen_at",
        "job",
        ["source", "status", "last_seen_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_source_status_last_seen_at", table_name="job")
    op.drop_constraint("uq_job_source_external_job_id", "job", type_="unique")
