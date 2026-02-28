"""update sources constraints for multi-ats ingestion

Revision ID: 002
Revises: 001
Create Date: 2026-02-27
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Allow same company name across different platforms.
    op.drop_index("ix_sources_name_normalized", table_name="sources")
    op.create_index("ix_sources_name_normalized", "sources", ["name_normalized"], unique=False)
    op.create_unique_constraint(
        "uq_sources_name_platform",
        "sources",
        ["name_normalized", "platform"],
    )
    op.create_unique_constraint(
        "uq_sources_platform_identifier",
        "sources",
        ["platform", "identifier"],
    )

    # Expand supported platform values.
    op.drop_constraint("ck_sources_platform", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_platform",
        "sources",
        "platform IN ('greenhouse', 'lever', 'workday', 'github', 'ashby', 'smartrecruiters')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_sources_platform", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_platform",
        "sources",
        "platform IN ('greenhouse', 'lever', 'workday')",
    )

    op.drop_constraint("uq_sources_platform_identifier", "sources", type_="unique")
    op.drop_constraint("uq_sources_name_platform", "sources", type_="unique")
    op.drop_index("ix_sources_name_normalized", table_name="sources")
    op.create_index("ix_sources_name_normalized", "sources", ["name_normalized"], unique=True)
