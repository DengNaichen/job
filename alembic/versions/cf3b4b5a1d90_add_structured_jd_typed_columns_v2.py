"""add structured jd typed columns v2

Revision ID: cf3b4b5a1d90
Revises: 7a6f5f0e3c12
Create Date: 2026-02-27 15:10:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "cf3b4b5a1d90"
down_revision: Union[str, Sequence[str], None] = "7a6f5f0e3c12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add typed columns for structured JD filtering/ranking."""
    op.add_column(
        "job",
        sa.Column(
            "sponsorship_not_available",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )
    op.add_column(
        "job",
        sa.Column("industry_raw", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "job",
        sa.Column(
            "industry_normalized",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )
    op.add_column(
        "job",
        sa.Column(
            "min_degree_level",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )
    op.add_column(
        "job",
        sa.Column(
            "min_degree_rank",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("-1"),
        ),
    )
    op.add_column(
        "job",
        sa.Column(
            "structured_jd_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("2"),
        ),
    )

    op.create_check_constraint(
        "ck_job_sponsorship_not_available_values",
        "job",
        "sponsorship_not_available IN ('yes','no','unknown')",
    )
    op.create_check_constraint(
        "ck_job_min_degree_level_values",
        "job",
        "min_degree_level IN ('none','associate','bachelor','master','doctorate','unknown')",
    )
    op.create_check_constraint(
        "ck_job_industry_normalized_values",
        "job",
        (
            "industry_normalized IN ("
            "'software_internet','fintech','healthcare_biotech','ecommerce_retail','education',"
            "'media_entertainment','consulting_professional_services','manufacturing_hardware',"
            "'logistics_supply_chain','energy_climate','government_public_sector','nonprofit','unknown'"
            ")"
        ),
    )

    op.create_index(
        "ix_job_sponsorship_not_available",
        "job",
        ["sponsorship_not_available"],
        unique=False,
    )
    op.create_index(
        "ix_job_industry_normalized",
        "job",
        ["industry_normalized"],
        unique=False,
    )
    op.create_index(
        "ix_job_min_degree_level",
        "job",
        ["min_degree_level"],
        unique=False,
    )
    op.create_index(
        "ix_job_min_degree_rank",
        "job",
        ["min_degree_rank"],
        unique=False,
    )
    op.create_index(
        "ix_job_structured_jd_version",
        "job",
        ["structured_jd_version"],
        unique=False,
    )

    # Mark previously parsed rows as v1 so backfill can target only historical parsed samples.
    op.execute("UPDATE job SET structured_jd_version = 1 WHERE structured_jd IS NOT NULL")


def downgrade() -> None:
    """Remove typed columns for structured JD filtering/ranking."""
    op.drop_index("ix_job_structured_jd_version", table_name="job")
    op.drop_index("ix_job_min_degree_rank", table_name="job")
    op.drop_index("ix_job_min_degree_level", table_name="job")
    op.drop_index("ix_job_industry_normalized", table_name="job")
    op.drop_index("ix_job_sponsorship_not_available", table_name="job")

    op.drop_constraint("ck_job_industry_normalized_values", "job", type_="check")
    op.drop_constraint("ck_job_min_degree_level_values", "job", type_="check")
    op.drop_constraint("ck_job_sponsorship_not_available_values", "job", type_="check")

    op.drop_column("job", "structured_jd_version")
    op.drop_column("job", "min_degree_rank")
    op.drop_column("job", "min_degree_level")
    op.drop_column("job", "industry_normalized")
    op.drop_column("job", "industry_raw")
    op.drop_column("job", "sponsorship_not_available")
