"""drop legacy in-row job embedding columns

Revision ID: d2c3b4a5e6f7
Revises: c1d2e3f4a5b6
Create Date: 2026-03-02 19:40:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2c3b4a5e6f7"
down_revision: str | Sequence[str] | None = "c1d2e3f4a5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_job_embedding_hnsw_cosine")
    op.execute("ALTER TABLE job DROP COLUMN IF EXISTS embedding_updated_at")
    op.execute("ALTER TABLE job DROP COLUMN IF EXISTS embedding_model")
    op.execute("ALTER TABLE job DROP COLUMN IF EXISTS embedding")


def downgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE job ADD COLUMN IF NOT EXISTS embedding vector(1024)")
    op.execute("ALTER TABLE job ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(128)")
    op.execute("ALTER TABLE job ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_job_embedding_hnsw_cosine "
        "ON job USING hnsw (embedding vector_cosine_ops)"
    )
