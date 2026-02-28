"""add eightfold to supported source platforms

Revision ID: f4c3b2a1908d
Revises: e1f2a3b4c5d6
Create Date: 2026-02-28 17:30:00.000000
"""

from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f4c3b2a1908d"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_sources_platform", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_platform",
        "sources",
        "platform IN ('greenhouse', 'lever', 'workday', 'github', 'ashby', 'smartrecruiters', 'eightfold')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_sources_platform", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_platform",
        "sources",
        "platform IN ('greenhouse', 'lever', 'workday', 'github', 'ashby', 'smartrecruiters')",
    )
