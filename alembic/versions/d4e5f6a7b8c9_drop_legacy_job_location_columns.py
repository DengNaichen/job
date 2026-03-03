"""drop legacy structured location columns from job

Revision ID: d4e5f6a7b8c9
Revises: 8d9f0a1b2c3d
Create Date: 2026-03-02 18:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "8d9f0a1b2c3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("job"):
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("job")}
        if "ix_job_location_country_code" in existing_indexes:
            op.drop_index("ix_job_location_country_code", table_name="job")
        if "ix_job_location_workplace_type" in existing_indexes:
            op.drop_index("ix_job_location_workplace_type", table_name="job")

        existing_columns = {col["name"] for col in inspector.get_columns("job")}
        for column_name in (
            "location_city",
            "location_region",
            "location_country_code",
            "location_workplace_type",
            "location_remote_scope",
        ):
            if column_name in existing_columns:
                op.drop_column("job", column_name)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("job"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("job")}
    if "location_city" not in existing_columns:
        op.add_column("job", sa.Column("location_city", sa.String(), nullable=True))
    if "location_region" not in existing_columns:
        op.add_column("job", sa.Column("location_region", sa.String(), nullable=True))
    if "location_country_code" not in existing_columns:
        op.add_column("job", sa.Column("location_country_code", sa.String(), nullable=True))
    if "location_workplace_type" not in existing_columns:
        op.add_column(
            "job",
            sa.Column(
                "location_workplace_type",
                sa.String(length=32),
                nullable=False,
                server_default=sa.text("'unknown'"),
            ),
        )
    if "location_remote_scope" not in existing_columns:
        op.add_column("job", sa.Column("location_remote_scope", sa.String(), nullable=True))

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("job")}
    if "ix_job_location_country_code" not in existing_indexes:
        op.create_index("ix_job_location_country_code", "job", ["location_country_code"], unique=False)
    if "ix_job_location_workplace_type" not in existing_indexes:
        op.create_index(
            "ix_job_location_workplace_type",
            "job",
            ["location_workplace_type"],
            unique=False,
        )
