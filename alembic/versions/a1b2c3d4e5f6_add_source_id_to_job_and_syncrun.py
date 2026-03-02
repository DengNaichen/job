"""add source_id FK to job and syncrun with backfill from legacy source string

Revision ID: a1b2c3d4e5f6
Revises: e1f2a3b4c5d6
Create Date: 2026-03-01 00:00:00.000000

Phase 2 (expansion + backfill). DO NOT apply the enforcement revision
(Phase 6) until post-backfill validation shows zero unmatched rows and
zero duplicate (source_id, external_job_id) ownership pairs.

Step order is intentional:
  1. Add nullable columns + indexes  (schema only, no data constraint yet)
  2. Backfill source_id from legacy source key  (data, no FK yet)
  3. Blocker checks  (abort if backfill was incomplete or produces dupes)
  4. Add FK constraints  (safe now: every non-NULL source_id is validated)

FK is created AFTER backfill so the UPDATE statements are never constrained
against a partially-populated sources table, and any unmatched rows are
caught by the blocker checks rather than triggering an FK violation mid-run.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # 1. Add nullable source_id columns + indexes                          #
    # Indexes are created before backfill so the UPDATE joins are fast.   #
    # ------------------------------------------------------------------ #
    op.add_column(
        "job",
        sa.Column("source_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "syncrun",
        sa.Column("source_id", sa.String(36), nullable=True),
    )

    op.create_index("ix_job_source_id", "job", ["source_id"], unique=False)
    op.create_index("ix_syncrun_source_id", "syncrun", ["source_id"], unique=False)
    op.create_index(
        "ix_job_source_id_status_last_seen_at",
        "job",
        ["source_id", "status", "last_seen_at"],
        unique=False,
    )

    # ------------------------------------------------------------------ #
    # 2. Backfill source_id from legacy source key                         #
    # The legacy key is stored as "platform:identifier" in the source col. #
    # sources.identifier may have leading/trailing whitespace (btrim).     #
    # FK does NOT exist yet — updates are unconstrained intentionally.     #
    # ------------------------------------------------------------------ #
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            UPDATE job AS j
            SET source_id = s.id
            FROM sources AS s
            WHERE j.source_id IS NULL
              AND j.source = concat(s.platform, ':', btrim(s.identifier))
            """
        )
    )

    conn.execute(
        sa.text(
            """
            UPDATE syncrun AS r
            SET source_id = s.id
            FROM sources AS s
            WHERE r.source_id IS NULL
              AND r.source = concat(s.platform, ':', btrim(s.identifier))
            """
        )
    )

    # ------------------------------------------------------------------ #
    # 3. Blocker checks — abort if any unmatched or duplicate rows exist   #
    # Must run BEFORE FK creation so a failed migration can be rolled back #
    # cleanly without violating any constraint.                            #
    # ------------------------------------------------------------------ #
    unmatched_jobs = (
        conn.execute(sa.text("SELECT COUNT(*) FROM job WHERE source_id IS NULL")).scalar() or 0
    )
    unmatched_syncruns = (
        conn.execute(sa.text("SELECT COUNT(*) FROM syncrun WHERE source_id IS NULL")).scalar() or 0
    )

    if unmatched_jobs > 0 or unmatched_syncruns > 0:
        raise RuntimeError(
            f"Backfill blockers found: {unmatched_jobs} job row(s) and "
            f"{unmatched_syncruns} syncrun row(s) have no matching source. "
            "Fix the unmatched legacy keys before proceeding."
        )

    duplicate_ownership = (
        conn.execute(
            sa.text(
                """
                SELECT COUNT(*) FROM (
                    SELECT source_id, external_job_id, COUNT(*) AS cnt
                    FROM job
                    GROUP BY source_id, external_job_id
                    HAVING COUNT(*) > 1
                ) AS dupes
                """
            )
        ).scalar()
        or 0
    )

    if duplicate_ownership > 0:
        raise RuntimeError(
            f"Backfill blockers found: {duplicate_ownership} duplicate "
            "(source_id, external_job_id) ownership pair(s) detected. "
            "Resolve the duplicates before applying the enforcement revision."
        )

    # ------------------------------------------------------------------ #
    # 4. Add FK constraints (RESTRICT prevents orphaning)                  #
    # Created last: every source_id in the table is now validated against  #
    # sources.id and blocker checks have confirmed no NULL rows remain.    #
    # ------------------------------------------------------------------ #
    op.create_foreign_key(
        "fk_job_source_id_sources",
        "job",
        "sources",
        ["source_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_syncrun_source_id_sources",
        "syncrun",
        "sources",
        ["source_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_syncrun_source_id_sources", "syncrun", type_="foreignkey")
    op.drop_constraint("fk_job_source_id_sources", "job", type_="foreignkey")
    op.drop_index("ix_job_source_id_status_last_seen_at", table_name="job")
    op.drop_index("ix_syncrun_source_id", table_name="syncrun")
    op.drop_index("ix_job_source_id", table_name="job")
    op.drop_column("syncrun", "source_id")
    op.drop_column("job", "source_id")
