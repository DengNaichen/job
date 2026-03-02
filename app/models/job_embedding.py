"""Persisted job embedding representations isolated from the hot job row."""

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.types import DateTime
from sqlmodel import Field, SQLModel


class JobEmbedding(SQLModel, table=True):
    """Stored job embedding for one explicit embedding target."""

    __tablename__ = "job_embedding"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "embedding_kind",
            "embedding_target_revision",
            "embedding_model",
            "embedding_dim",
            name="uq_job_embedding_job_target",
        ),
        Index(
            "ix_job_embedding_active_target",
            "embedding_kind",
            "embedding_target_revision",
            "embedding_model",
            "embedding_dim",
            "job_id",
        ),
    )

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    job_id: str = Field(
        sa_column=Column(
            String(36),
            ForeignKey("job.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    embedding_kind: str = Field(sa_column=Column(String(64), nullable=False))
    embedding_target_revision: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False),
    )
    embedding_model: str = Field(sa_column=Column(String(255), nullable=False))
    embedding_dim: int = Field(sa_column=Column(Integer, nullable=False))
    embedding: list[float] = Field(default_factory=list, sa_column=Column(Vector(1024), nullable=False))
    content_fingerprint: str | None = Field(
        default=None,
        sa_column=Column(String(128), nullable=True, index=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
