"""Embedding value objects and types."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel


class EmbeddingConfig(BaseModel):
    """Embedding configuration model."""

    provider: str
    model: str
    api_key: str | None = None
    api_base: str | None = None


@dataclass(frozen=True)
class EmbeddingTargetDescriptor:
    """Stable embedding target descriptor used by storage and retrieval paths."""

    embedding_kind: str
    embedding_target_revision: int
    embedding_model: str
    embedding_dim: int
