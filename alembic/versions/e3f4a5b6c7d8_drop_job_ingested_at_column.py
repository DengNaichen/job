"""drop job ingested_at column

Revision ID: e3f4a5b6c7d8
Revises: d2c3b4a5e6f7
Create Date: 2026-03-02 21:35:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"
down_revision: str | Sequence[str] | None = "d2c3b4a5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE job DROP COLUMN IF EXISTS ingested_at")


def downgrade() -> None:
    op.execute("ALTER TABLE job ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMP")
    op.execute(
        """
        UPDATE job
        SET ingested_at = COALESCE(ingested_at, created_at, last_seen_at, updated_at, NOW())
        WHERE ingested_at IS NULL
        """
    )
    op.execute("ALTER TABLE job ALTER COLUMN ingested_at SET NOT NULL")
