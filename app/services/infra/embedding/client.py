"""LiteLLM embedding client."""

from __future__ import annotations

from typing import Any

import litellm

from .config import _normalize_api_base, get_embedding_config, resolve_embedding_model_name
from .parsing import extract_vectors_from_response
from .types import EmbeddingConfig

EMBEDDING_TIMEOUT = 120
_TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
_TRANSIENT_MESSAGE_HINTS = (
    "timed out",
    "timeout",
    "temporary",
    "temporarily",
    "rate limit",
    "service unavailable",
    "try again",
)
_DIMENSION_UNSUPPORTED_HINTS = (
    "unsupported",
    "not support",
    "doesn't support",
    "does not support",
    "unexpected",
    "unknown",
    "invalid",
)


def _build_embedding_kwargs(
    *,
    model_name: str,
    texts: list[str],
    config: EmbeddingConfig,
    dimensions: int | None,
) -> dict[str, Any]:
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
    return kwargs


def _get_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status
    return None


def _is_dimensions_unsupported_error(exc: Exception) -> bool:
    message = str(exc).lower()
    if "dimension" not in message:
        return False
    return any(hint in message for hint in _DIMENSION_UNSUPPORTED_HINTS)


def _is_transient_error(exc: Exception) -> bool:
    if isinstance(
        exc,
        (
            litellm.Timeout,
            litellm.APIConnectionError,
            litellm.RateLimitError,
            litellm.ServiceUnavailableError,
        ),
    ):
        return True

    status_code = _get_status_code(exc)
    if status_code in _TRANSIENT_STATUS_CODES:
        return True

    message = str(exc).lower()
    return any(hint in message for hint in _TRANSIENT_MESSAGE_HINTS)


def _parse_vectors(
    *,
    response: Any,
    config: EmbeddingConfig,
    model_name: str,
    expected_count: int,
    expected_dimensions: int | None = None,
) -> list[list[float]]:
    try:
        return extract_vectors_from_response(
            response,
            expected_count=expected_count,
            expected_dimensions=expected_dimensions,
        )
    except ValueError as exc:
        raise ValueError(f"{exc}; provider={config.provider}; model={model_name}") from exc


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
    active_dimensions = dimensions

    for attempt in range(retries + 1):
        kwargs = _build_embedding_kwargs(
            model_name=model_name,
            texts=texts,
            config=config,
            dimensions=active_dimensions,
        )
        try:
            response = await litellm.aembedding(**kwargs)
            return _parse_vectors(
                response=response,
                config=config,
                model_name=model_name,
                expected_count=len(texts),
                expected_dimensions=active_dimensions,
            )
        except Exception as exc:
            error_to_handle: Exception = exc
            if active_dimensions is not None and _is_dimensions_unsupported_error(exc):
                active_dimensions = None
                try:
                    fallback_kwargs = _build_embedding_kwargs(
                        model_name=model_name,
                        texts=texts,
                        config=config,
                        dimensions=None,
                    )
                    response = await litellm.aembedding(**fallback_kwargs)
                    return _parse_vectors(
                        response=response,
                        config=config,
                        model_name=model_name,
                        expected_count=len(texts),
                    )
                except Exception as fallback_exc:
                    error_to_handle = fallback_exc

            if attempt >= retries or not _is_transient_error(error_to_handle):
                raise error_to_handle

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
