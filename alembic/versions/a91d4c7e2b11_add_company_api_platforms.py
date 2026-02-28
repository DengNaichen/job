"""add apple uber and tiktok source platforms

Revision ID: a91d4c7e2b11
Revises: f4c3b2a1908d
Create Date: 2026-02-28 18:30:00.000000
"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a91d4c7e2b11"
down_revision: str | Sequence[str] | None = "f4c3b2a1908d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_sources_platform", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_platform",
        "sources",
        "platform IN ('greenhouse', 'lever', 'workday', 'github', 'ashby', 'smartrecruiters', 'eightfold', 'apple', 'uber', 'tiktok')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_sources_platform", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_platform",
        "sources",
        "platform IN ('greenhouse', 'lever', 'workday', 'github', 'ashby', 'smartrecruiters', 'eightfold')",
    )
