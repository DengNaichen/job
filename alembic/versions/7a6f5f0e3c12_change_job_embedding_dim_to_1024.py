"""change job embedding dim to 1024

Revision ID: 7a6f5f0e3c12
Revises: 2f0e2e312c15
Create Date: 2026-02-27 14:30:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7a6f5f0e3c12"
down_revision: str | Sequence[str] | None = "2f0e2e312c15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Change embedding vector dimension from 768 to 1024.

    Existing non-null embeddings are cleared because pgvector cannot
    safely cast vectors across different dimensions.
    """
    op.execute("DROP INDEX IF EXISTS ix_job_embedding_hnsw_cosine")
    op.execute("UPDATE job SET embedding = NULL WHERE embedding IS NOT NULL")
    op.execute("ALTER TABLE job ALTER COLUMN embedding TYPE vector(1024)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_job_embedding_hnsw_cosine "
        "ON job USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """Revert embedding vector dimension from 1024 to 768."""
    op.execute("DROP INDEX IF EXISTS ix_job_embedding_hnsw_cosine")
    op.execute("UPDATE job SET embedding = NULL WHERE embedding IS NOT NULL")
    op.execute("ALTER TABLE job ALTER COLUMN embedding TYPE vector(768)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_job_embedding_hnsw_cosine "
        "ON job USING hnsw (embedding vector_cosine_ops)"
    )
