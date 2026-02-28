"""add job embedding columns for vector retrieval

Revision ID: 003
Revises: 002
Create Date: 2026-02-27
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE job ADD COLUMN IF NOT EXISTS embedding vector(768)")
    op.execute("ALTER TABLE job ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(128)")
    op.execute("ALTER TABLE job ADD COLUMN IF NOT EXISTS embedding_updated_at TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_job_embedding_hnsw_cosine "
        "ON job USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_job_embedding_hnsw_cosine")
    op.execute("ALTER TABLE job DROP COLUMN IF EXISTS embedding_updated_at")
    op.execute("ALTER TABLE job DROP COLUMN IF EXISTS embedding_model")
    op.execute("ALTER TABLE job DROP COLUMN IF EXISTS embedding")
