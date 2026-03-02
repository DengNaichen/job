"""LiteLLM embedding client."""

from __future__ import annotations

from typing import Any

import litellm

from .config import _normalize_api_base, get_embedding_config, resolve_embedding_model_name
from .parsing import _extract_vector
from .types import EmbeddingConfig

EMBEDDING_TIMEOUT = 120


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
