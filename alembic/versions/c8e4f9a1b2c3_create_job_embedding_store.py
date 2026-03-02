"""create dedicated job_embedding store

Revision ID: c8e4f9a1b2c3
Revises: 6f9a1c158e9a
Create Date: 2026-03-02 02:20:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8e4f9a1b2c3"
down_revision: str | Sequence[str] | None = "6f9a1c158e9a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS job_embedding (
            id VARCHAR(36) PRIMARY KEY,
            job_id VARCHAR(36) NOT NULL REFERENCES job(id) ON DELETE CASCADE,
            embedding_kind VARCHAR(64) NOT NULL,
            embedding_target_revision INTEGER NOT NULL DEFAULT 1,
            embedding_model VARCHAR(255) NOT NULL,
            embedding_dim INTEGER NOT NULL,
            embedding vector(1024) NOT NULL,
            content_fingerprint VARCHAR(128),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_job_embedding_job_target
                UNIQUE (
                    job_id,
                    embedding_kind,
                    embedding_target_revision,
                    embedding_model,
                    embedding_dim
                )
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_job_embedding_job_id ON job_embedding (job_id)")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_job_embedding_active_target
        ON job_embedding (
            embedding_kind,
            embedding_target_revision,
            embedding_model,
            embedding_dim,
            job_id
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_job_embedding_content_fingerprint
        ON job_embedding (content_fingerprint)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_job_embedding_store_hnsw_cosine
        ON job_embedding USING hnsw (embedding vector_cosine_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_job_embedding_store_hnsw_cosine")
    op.execute("DROP INDEX IF EXISTS ix_job_embedding_content_fingerprint")
    op.execute("DROP INDEX IF EXISTS ix_job_embedding_active_target")
    op.execute("DROP INDEX IF EXISTS ix_job_embedding_job_id")
    op.execute("DROP TABLE IF EXISTS job_embedding")
