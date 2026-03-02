"""LiteLLM wrapper for embedding generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import litellm
from pydantic import BaseModel

from app.core.config import get_settings

EMBEDDING_TIMEOUT = 120
JOB_EMBEDDING_KIND = "job_description"
JOB_EMBEDDING_TARGET_REVISION = 1


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


def get_embedding_config() -> EmbeddingConfig:
    """Get embedding configuration from settings."""
    settings = get_settings()
    return EmbeddingConfig(
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        api_key=settings.embedding_api_key or settings.gemini_api_key,
        api_base=settings.embedding_api_base,
    )


def _normalize_api_base(provider: str, api_base: str | None) -> str | None:
    """Normalize provider api_base for LiteLLM expectations."""
    if not api_base:
        return None

    base = api_base.strip().rstrip("/")

    if provider == "anthropic" and base.endswith("/v1"):
        base = base[: -len("/v1")].rstrip("/")
    if provider == "gemini" and base.endswith("/v1"):
        base = base[: -len("/v1")].rstrip("/")

    return base or None


def resolve_embedding_model_name(config: EmbeddingConfig) -> str:
    """Convert provider/model to LiteLLM format."""
    provider_prefixes = {
        "openai": "",
        "anthropic": "anthropic/",
        "openrouter": "openrouter/",
        "gemini": "gemini/",
        "deepseek": "deepseek/",
        "ollama": "ollama/",
    }

    prefix = provider_prefixes.get(config.provider, "")

    if config.provider == "openrouter":
        if config.model.startswith("openrouter/"):
            return config.model
        return f"openrouter/{config.model}"

    known_prefixes = ["openrouter/", "anthropic/", "gemini/", "deepseek/", "ollama/"]
    if any(config.model.startswith(p) for p in known_prefixes):
        return config.model

    return f"{prefix}{config.model}" if prefix else config.model


def normalize_embedding_model_identity(*, provider: str, model: str) -> str:
    """Normalize provider/model identity into one stable persisted string."""
    return resolve_embedding_model_name(EmbeddingConfig(provider=provider, model=model))


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


def _extract_vector(item: Any) -> list[float]:
    """Extract embedding vector from LiteLLM response item."""
    if isinstance(item, dict):
        values = item.get("embedding")
    else:
        values = getattr(item, "embedding", None)

    if not isinstance(values, list) or not values:
        raise ValueError("Invalid embedding response item")

    return [float(v) for v in values]


async def embed_texts(
    texts: list[str],
    *,
    config: EmbeddingConfig | None = None,
    dimensions: int | None = None,
    retries: int = 2,
) -> list[list[float]]:
    """Generate embeddings for a list of texts."""
    if not texts:
        return []

    if config is None:
        config = get_embedding_config()

    model_name = resolve_embedding_model_name(config)
    last_error: Exception | None = None

    for _ in range(retries + 1):
        try:
            kwargs: dict[str, Any] = {
                "model": model_name,
                "input": texts,
                "custom_llm_provider": config.provider,
                "api_key": config.api_key,
                "api_base": _normalize_api_base(config.provider, config.api_base),
                "timeout": EMBEDDING_TIMEOUT,
            }
            if dimensions is not None:
                kwargs["dimensions"] = dimensions

            response = await litellm.aembedding(**kwargs)
            data = getattr(response, "data", None)
            if not isinstance(data, list):
                raise ValueError("Invalid embedding response: missing data list")
            return [_extract_vector(item) for item in data]
        except Exception as exc:
            # Some providers reject dimensions; retry once without it.
            if dimensions is not None:
                try:
                    kwargs = {
                        "model": model_name,
                        "input": texts,
                        "custom_llm_provider": config.provider,
                        "api_key": config.api_key,
                        "api_base": _normalize_api_base(config.provider, config.api_base),
                        "timeout": EMBEDDING_TIMEOUT,
                    }
                    response = await litellm.aembedding(**kwargs)
                    data = getattr(response, "data", None)
                    if not isinstance(data, list):
                        raise ValueError("Invalid embedding response: missing data list")
                    return [_extract_vector(item) for item in data]
                except Exception as fallback_exc:
                    last_error = fallback_exc
                    continue
            last_error = exc
            continue

    if last_error is not None:
        raise last_error
    raise RuntimeError("Embedding request failed without explicit error")


async def embed_text(
    text: str,
    *,
    config: EmbeddingConfig | None = None,
    dimensions: int | None = None,
    retries: int = 2,
) -> list[float]:
    """Generate embedding for a single text."""
    vectors = await embed_texts(
        [text],
        config=config,
        dimensions=dimensions,
        retries=retries,
    )
    if not vectors:
        raise RuntimeError("Embedding response returned no vectors")
    return vectors[0]
