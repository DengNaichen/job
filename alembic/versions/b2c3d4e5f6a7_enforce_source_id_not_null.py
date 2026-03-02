"""add NOT NULL enforcement on source_id in job and syncrun

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-01 00:05:00.000000

Phase 6 (enforcement). Only apply after:
  1. Phase 2 revision (a1b2c3d4e5f6) has been applied and all rows backfilled.
  2. Post-backfill validation shows zero unmatched rows.
  3. Application has been deployed with Phase 3–5 changes so all new writes
     populate source_id.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Enforce NOT NULL on source_id                                     #
    # ------------------------------------------------------------------ #
    op.alter_column("job", "source_id", nullable=False)
    op.alter_column("syncrun", "source_id", nullable=False)

    # ------------------------------------------------------------------ #
    # 2. Swap the uniqueness constraint on job from string → source_id     #
    # The authoritative constraint is keyed on source_id.                  #
    # The legacy constraint uq_job_source_external_job_id is dropped here  #
    # because source_id is now enforced NOT NULL and is the sole owner key.#
    # Physical rename of the source column itself is deferred to a future  #
    # cleanup migration.                                                   #
    # ------------------------------------------------------------------ #
    op.create_unique_constraint(
        "uq_job_source_id_external_job_id",
        "job",
        ["source_id", "external_job_id"],
    )
    op.drop_constraint("uq_job_source_external_job_id", "job", type_="unique")

    # ------------------------------------------------------------------ #
    # 3. Note: ix_job_source_id_status_last_seen_at was already created    #
    # in Phase 2 — no additional index work needed here.                  #
    # ------------------------------------------------------------------ #


def downgrade() -> None:
    op.create_unique_constraint(
        "uq_job_source_external_job_id",
        "job",
        ["source", "external_job_id"],
    )
    op.drop_constraint("uq_job_source_id_external_job_id", "job", type_="unique")
    op.alter_column("syncrun", "source_id", nullable=True)
    op.alter_column("job", "source_id", nullable=True)
