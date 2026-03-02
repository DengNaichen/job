"""add job_location metadata and backfill

Revision ID: 8d9f0a1b2c3d
Revises: 2f901e544b79
Create Date: 2026-03-02 17:20:00.000000

"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "8d9f0a1b2c3d"
down_revision: Union[str, Sequence[str], None] = "2f901e544b79"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _slug_part(value: str) -> str:
    part = value.replace("-", " ")
    part = unicodedata.normalize("NFKD", part).encode("ASCII", "ignore").decode("ASCII")
    part = re.sub(r"[^a-z0-9\s]", "", part.lower())
    part = re.sub(r"\s+", "-", part.strip())
    return part


def _build_canonical_key(city: str | None, region: str | None, country_code: str | None) -> str:
    parts: list[str] = []
    if country_code:
        parts.append(country_code.lower())
    if region:
        parts.append(region.lower())
    if city:
        parts.append(city.lower())

    normalized: list[str] = []
    for part in parts:
        slug = _slug_part(part)
        if slug:
            normalized.append(slug)
    return "-".join(normalized) if normalized else "unknown"


def _build_display_name(city: str | None, region: str | None, country_code: str | None) -> str:
    parts = [part for part in [city, region, country_code.upper() if country_code else None] if part]
    return ", ".join(parts) if parts else "Unknown Location"


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    op.add_column(
        "job_locations",
        sa.Column(
            "workplace_type",
            sa.String(length=32),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
    )
    op.add_column("job_locations", sa.Column("remote_scope", sa.String(length=255), nullable=True))
    op.create_index(
        "ix_job_locations_job_id_is_primary",
        "job_locations",
        ["job_id", "is_primary"],
        unique=False,
    )

    job = sa.table(
        "job",
        sa.column("id", sa.String(length=36)),
        sa.column("location_text", sa.Text()),
        sa.column("location_city", sa.String()),
        sa.column("location_region", sa.String()),
        sa.column("location_country_code", sa.String()),
        sa.column("location_workplace_type", sa.String()),
        sa.column("location_remote_scope", sa.String()),
    )
    location = sa.table(
        "locations",
        sa.column("id", sa.String(length=36)),
        sa.column("canonical_key", sa.String(length=255)),
        sa.column("display_name", sa.String(length=255)),
        sa.column("city", sa.String(length=128)),
        sa.column("region", sa.String(length=128)),
        sa.column("country_code", sa.String(length=2)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    job_location = sa.table(
        "job_locations",
        sa.column("id", sa.String(length=36)),
        sa.column("job_id", sa.String(length=36)),
        sa.column("location_id", sa.String(length=36)),
        sa.column("is_primary", sa.Boolean()),
        sa.column("source_raw", sa.Text()),
        sa.column("workplace_type", sa.String(length=32)),
        sa.column("remote_scope", sa.String(length=255)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    # Existing lookup tables to keep the migration idempotent and avoid duplicate inserts.
    location_by_key: dict[str, str] = {
        row.canonical_key: row.id
        for row in bind.execute(sa.select(location.c.id, location.c.canonical_key)).all()
    }

    links_by_job: dict[str, list] = defaultdict(list)
    link_rows = bind.execute(
        sa.select(
            job_location.c.id,
            job_location.c.job_id,
            job_location.c.location_id,
            job_location.c.is_primary,
            job_location.c.source_raw,
            job_location.c.workplace_type,
            job_location.c.remote_scope,
            job_location.c.created_at,
        ).order_by(job_location.c.job_id, job_location.c.created_at, job_location.c.id)
    ).all()
    for row in link_rows:
        links_by_job[row.job_id].append(row)

    now_utc = datetime.now(timezone.utc)

    for row in bind.execute(sa.select(job)).all():
        job_id = row.id
        legacy_workplace_type = row.location_workplace_type or "unknown"
        legacy_remote_scope = row.location_remote_scope
        legacy_source_raw = row.location_text

        existing_links = links_by_job.get(job_id, [])
        if existing_links:
            primary_link = next((link for link in existing_links if link.is_primary), existing_links[0])
            update_values: dict[str, object] = {}

            if not primary_link.is_primary:
                update_values["is_primary"] = True
            if (primary_link.workplace_type or "unknown") == "unknown" and legacy_workplace_type:
                update_values["workplace_type"] = legacy_workplace_type
            if primary_link.remote_scope is None and legacy_remote_scope:
                update_values["remote_scope"] = legacy_remote_scope
            if primary_link.source_raw is None and legacy_source_raw:
                update_values["source_raw"] = legacy_source_raw

            if update_values:
                bind.execute(
                    sa.update(job_location)
                    .where(job_location.c.id == primary_link.id)
                    .values(**update_values)
                )
            continue

        city = row.location_city
        region = row.location_region
        country_code = row.location_country_code
        if country_code:
            country_code = country_code.upper()

        # Skip rows without enough structure to build a canonical location.
        if not any([city, region, country_code]):
            continue

        canonical_key = _build_canonical_key(city=city, region=region, country_code=country_code)
        location_id = location_by_key.get(canonical_key)
        if location_id is None:
            location_id = str(uuid.uuid4())
            bind.execute(
                sa.insert(location).values(
                    id=location_id,
                    canonical_key=canonical_key,
                    display_name=_build_display_name(
                        city=city,
                        region=region,
                        country_code=country_code,
                    ),
                    city=city,
                    region=region,
                    country_code=country_code,
                    created_at=now_utc,
                    updated_at=now_utc,
                )
            )
            location_by_key[canonical_key] = location_id

        bind.execute(
            sa.insert(job_location).values(
                id=str(uuid.uuid4()),
                job_id=job_id,
                location_id=location_id,
                is_primary=True,
                source_raw=legacy_source_raw,
                workplace_type=legacy_workplace_type,
                remote_scope=legacy_remote_scope,
                created_at=now_utc,
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_job_locations_job_id_is_primary", table_name="job_locations")
    op.drop_column("job_locations", "remote_scope")
    op.drop_column("job_locations", "workplace_type")
