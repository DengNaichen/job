"""Unit tests for embedding config helpers."""

from app.services.infra.embedding.config import (
    _normalize_api_base,
    normalize_embedding_model_identity,
    resolve_embedding_model_name,
)
from app.services.infra.embedding.types import EmbeddingConfig


def test_normalize_api_base_handles_provider_suffix_rules() -> None:
    assert _normalize_api_base("anthropic", "https://api.anthropic.com/v1") == (
        "https://api.anthropic.com"
    )
    assert _normalize_api_base("gemini", "https://example.com/v1/") == "https://example.com"
    assert _normalize_api_base("openai", "https://api.openai.com/v1") == "https://api.openai.com/v1"
    assert _normalize_api_base("openai", None) is None


def test_resolve_embedding_model_name_applies_prefixes() -> None:
    assert (
        resolve_embedding_model_name(
            EmbeddingConfig(provider="anthropic", model="claude-3-5-haiku")
        )
        == "anthropic/claude-3-5-haiku"
    )
    assert (
        resolve_embedding_model_name(
            EmbeddingConfig(provider="openrouter", model="openai/text-embedding-3-small")
        )
        == "openrouter/openai/text-embedding-3-small"
    )
    assert (
        resolve_embedding_model_name(
            EmbeddingConfig(
                provider="openrouter",
                model="openrouter/openai/text-embedding-3-small",
            )
        )
        == "openrouter/openai/text-embedding-3-small"
    )


def test_normalize_embedding_model_identity_is_stable() -> None:
    assert (
        normalize_embedding_model_identity(
            provider="gemini",
            model="gemini-embedding-001",
        )
        == "gemini/gemini-embedding-001"
    )
