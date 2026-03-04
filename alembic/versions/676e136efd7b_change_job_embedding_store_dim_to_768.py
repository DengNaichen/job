"""change_job_embedding_store_dim_to_768

Revision ID: 676e136efd7b
Revises: 3fb338c5dab5
Create Date: 2026-03-03 18:19:50.912721

"""
from collections.abc import Sequence

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "676e136efd7b"
down_revision: str | Sequence[str] | None = "3fb338c5dab5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Change dedicated job_embedding vector dim from 1024 to 768."""
    op.execute("DROP INDEX IF EXISTS ix_job_embedding_store_hnsw_cosine")
    # Existing vectors are fixed-width (1024) and are incompatible with vector(768).
    # Clear and re-backfill to avoid cast failures and mixed-dim rows.
    op.execute("TRUNCATE TABLE job_embedding")
    op.execute("ALTER TABLE job_embedding ALTER COLUMN embedding TYPE vector(768)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_job_embedding_store_hnsw_cosine
        ON job_embedding USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    """Restore dedicated job_embedding vector dim from 768 to 1024."""
    op.execute("DROP INDEX IF EXISTS ix_job_embedding_store_hnsw_cosine")
    op.execute("TRUNCATE TABLE job_embedding")
    op.execute("ALTER TABLE job_embedding ALTER COLUMN embedding TYPE vector(1024)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_job_embedding_store_hnsw_cosine
        ON job_embedding USING hnsw (embedding vector_cosine_ops)
        """
    )
