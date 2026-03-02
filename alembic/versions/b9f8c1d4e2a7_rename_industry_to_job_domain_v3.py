"""rename industry columns to job domain v3

Revision ID: b9f8c1d4e2a7
Revises: cf3b4b5a1d90
Create Date: 2026-02-27 19:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b9f8c1d4e2a7"
down_revision: Union[str, Sequence[str], None] = "cf3b4b5a1d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


JOB_DOMAIN_VALUES = (
    "'software_engineering','data_ai','product_program','design',"
    "'sales_account_management','marketing_growth','finance_treasury','operations',"
    "'customer_support','hr_recruiting','legal_compliance','cybersecurity','unknown'"
)


def upgrade() -> None:
    """Rename industry columns to job_domain and bump default schema version."""
    op.drop_index("ix_job_industry_normalized", table_name="job")
    op.drop_constraint("ck_job_industry_normalized_values", "job", type_="check")

    op.alter_column(
        "job",
        "industry_raw",
        new_column_name="job_domain_raw",
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "job",
        "industry_normalized",
        new_column_name="job_domain_normalized",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        existing_server_default=sa.text("'unknown'"),
        server_default=sa.text("'unknown'"),
    )
    op.alter_column(
        "job",
        "structured_jd_version",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("2"),
        server_default=sa.text("3"),
    )

    # Existing v1/v2 values describe company industry, not role domain.
    # Clear them so v3 reparsing is the single source of truth.
    op.execute(
        """
        UPDATE job
        SET job_domain_raw = NULL,
            job_domain_normalized = 'unknown'
        WHERE COALESCE(structured_jd_version, 0) < 3
        """
    )
    op.execute(
        """
        UPDATE job
        SET structured_jd = structured_jd - 'industry_raw' - 'industry_normalized' - 'job_domain_raw'
        WHERE structured_jd IS NOT NULL AND COALESCE(structured_jd_version, 0) < 3
        """
    )

    op.create_check_constraint(
        "ck_job_job_domain_normalized_values",
        "job",
        f"job_domain_normalized IN ({JOB_DOMAIN_VALUES})",
    )
    op.create_index(
        "ix_job_job_domain_normalized",
        "job",
        ["job_domain_normalized"],
        unique=False,
    )


def downgrade() -> None:
    """Rename job_domain columns back to industry and restore default schema version."""
    op.drop_index("ix_job_job_domain_normalized", table_name="job")
    op.drop_constraint("ck_job_job_domain_normalized_values", "job", type_="check")

    op.alter_column(
        "job",
        "job_domain_normalized",
        new_column_name="industry_normalized",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        existing_server_default=sa.text("'unknown'"),
        server_default=sa.text("'unknown'"),
    )
    op.alter_column(
        "job",
        "job_domain_raw",
        new_column_name="industry_raw",
        existing_type=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "job",
        "structured_jd_version",
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default=sa.text("3"),
        server_default=sa.text("2"),
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
        "ix_job_industry_normalized",
        "job",
        ["industry_normalized"],
        unique=False,
    )
