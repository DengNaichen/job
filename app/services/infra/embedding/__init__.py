"""Embedding integration package with backward-compatible exports."""

from .client import EMBEDDING_TIMEOUT, embed_text, embed_texts, litellm
from .config import (
    _normalize_api_base,
    get_embedding_config,
    normalize_embedding_model_identity,
    resolve_embedding_model_name,
)
from .parsing import _extract_vector
from .targets import (
    JOB_EMBEDDING_KIND,
    JOB_EMBEDDING_TARGET_REVISION,
    resolve_active_job_embedding_target,
)
from .types import EmbeddingConfig, EmbeddingTargetDescriptor

__all__ = [
    "EMBEDDING_TIMEOUT",
    "JOB_EMBEDDING_KIND",
    "JOB_EMBEDDING_TARGET_REVISION",
    "EmbeddingConfig",
    "EmbeddingTargetDescriptor",
    "_extract_vector",
    "_normalize_api_base",
    "embed_text",
    "embed_texts",
    "get_embedding_config",
    "litellm",
    "normalize_embedding_model_identity",
    "resolve_active_job_embedding_target",
    "resolve_embedding_model_name",
]
