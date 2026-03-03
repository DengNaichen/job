"""drop_job_location_text_column

Revision ID: e6f7a8b9c0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-03-02 14:30:00.000000

"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ensure_unknown_location(connection: sa.Connection) -> str:
    locations = sa.table(
        "locations",
        sa.column("id", sa.String(length=36)),
        sa.column("canonical_key", sa.String(length=255)),
        sa.column("display_name", sa.String(length=255)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    unknown_location_id = connection.execute(
        sa.select(locations.c.id).where(locations.c.canonical_key == "unknown")
    ).scalar_one_or_none()
    if unknown_location_id:
        return str(unknown_location_id)

    now = datetime.now(timezone.utc)
    unknown_location_id = str(uuid.uuid4())
    connection.execute(
        sa.insert(locations).values(
            id=unknown_location_id,
            canonical_key="unknown",
            display_name="Unknown",
            created_at=now,
            updated_at=now,
        )
    )
    return unknown_location_id


def _backfill_primary_link_for_jobs_without_primary(connection: sa.Connection) -> None:
    job_locations = sa.table(
        "job_locations",
        sa.column("id", sa.String(length=36)),
        sa.column("job_id", sa.String(length=36)),
        sa.column("location_id", sa.String(length=36)),
        sa.column("is_primary", sa.Boolean()),
        sa.column("source_raw", sa.Text()),
        sa.column("workplace_type", sa.String(length=32)),
        sa.column("remote_scope", sa.Text()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    candidates = connection.execute(
        sa.text(
            """
            SELECT j.id AS job_id, j.location_text AS location_text
            FROM job AS j
            LEFT JOIN job_locations AS jl
              ON jl.job_id = j.id AND jl.is_primary = TRUE
            WHERE jl.job_id IS NULL
              AND j.location_text IS NOT NULL
              AND btrim(j.location_text) <> ''
            """
        )
    ).mappings()

    rows = list(candidates)
    if not rows:
        return

    unknown_location_id = _ensure_unknown_location(connection)
    now = datetime.now(timezone.utc)
    connection.execute(
        sa.insert(job_locations),
        [
            {
                "id": str(uuid.uuid4()),
                "job_id": str(row["job_id"]),
                "location_id": unknown_location_id,
                "is_primary": True,
                "source_raw": str(row["location_text"]),
                "workplace_type": "unknown",
                "remote_scope": None,
                "created_at": now,
            }
            for row in rows
        ],
    )


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()

    _backfill_primary_link_for_jobs_without_primary(connection)
    op.drop_column("job", "location_text")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("job", sa.Column("location_text", sa.Text(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE job AS j
            SET location_text = jl.source_raw
            FROM job_locations AS jl
            WHERE jl.job_id = j.id
              AND jl.is_primary = TRUE
              AND jl.source_raw IS NOT NULL
              AND btrim(jl.source_raw) <> ''
              AND (j.location_text IS NULL OR btrim(j.location_text) = '')
            """
        )
    )
