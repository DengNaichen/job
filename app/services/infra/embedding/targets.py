"""Embedding target descriptor resolution."""

from __future__ import annotations

from app.core.config import get_settings

from .config import get_embedding_config, normalize_embedding_model_identity
from .types import EmbeddingConfig, EmbeddingTargetDescriptor

JOB_EMBEDDING_KIND = "job_description"
JOB_EMBEDDING_TARGET_REVISION = 1


def resolve_active_job_embedding_target(
    *,
    config: EmbeddingConfig | None = None,
    embedding_dim: int | None = None,
) -> EmbeddingTargetDescriptor:
    """Resolve the currently configured active target descriptor for job-side embeddings."""
    if config is None:
        config = get_embedding_config()
    if embedding_dim is None:
        embedding_dim = get_settings().embedding_dim
    if embedding_dim <= 0:
        raise ValueError("embedding_dim must be > 0")

    model_identity = normalize_embedding_model_identity(
        provider=config.provider, model=config.model
    )
    return EmbeddingTargetDescriptor(
        embedding_kind=JOB_EMBEDDING_KIND,
        embedding_target_revision=JOB_EMBEDDING_TARGET_REVISION,
        embedding_model=model_identity,
        embedding_dim=embedding_dim,
    )
