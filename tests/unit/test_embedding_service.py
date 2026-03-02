"""Unit tests for embedding LiteLLM wrapper."""

from types import SimpleNamespace

import pytest

from app.services.infra.embedding import (
    EmbeddingConfig,
    embed_texts,
    normalize_embedding_model_identity,
    resolve_active_job_embedding_target,
    resolve_embedding_model_name,
)


def test_resolve_embedding_model_name() -> None:
    """Model name should follow provider prefix rules."""
    openai_cfg = EmbeddingConfig(provider="openai", model="Qwen/Qwen3-Embedding-8B")
    gemini_cfg = EmbeddingConfig(provider="gemini", model="gemini-embedding-001")

    assert resolve_embedding_model_name(openai_cfg) == "Qwen/Qwen3-Embedding-8B"
    assert resolve_embedding_model_name(gemini_cfg) == "gemini/gemini-embedding-001"


def test_normalize_embedding_model_identity() -> None:
    """Normalization should stabilize provider/model identities."""
    assert (
        normalize_embedding_model_identity(provider="gemini", model="gemini-embedding-001")
        == "gemini/gemini-embedding-001"
    )
    assert (
        normalize_embedding_model_identity(
            provider="openrouter",
            model="openrouter/qwen/qwen3-embedding-8b",
        )
        == "openrouter/qwen/qwen3-embedding-8b"
    )


def test_resolve_active_job_embedding_target() -> None:
    """Active target descriptor should carry normalized model identity and dimension."""
    cfg = EmbeddingConfig(provider="gemini", model="gemini-embedding-001")

    target = resolve_active_job_embedding_target(config=cfg, embedding_dim=1024)

    assert target.embedding_kind == "job_description"
    assert target.embedding_target_revision == 1
    assert target.embedding_model == "gemini/gemini-embedding-001"
    assert target.embedding_dim == 1024


@pytest.mark.asyncio
async def test_embed_texts_returns_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    """embed_texts should parse vectors from LiteLLM response."""

    async def fake_aembedding(**kwargs):  # noqa: ANN003
        assert kwargs["input"] == ["hello", "world"]
        return SimpleNamespace(
            data=[
                {"embedding": [0.1, 0.2]},
                {"embedding": [0.3, 0.4]},
            ]
        )

    monkeypatch.setattr("app.services.infra.embedding.litellm.aembedding", fake_aembedding)

    vectors = await embed_texts(
        ["hello", "world"],
        config=EmbeddingConfig(provider="openai", model="Qwen/Qwen3-Embedding-8B"),
        dimensions=2,
    )

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


@pytest.mark.asyncio
async def test_embed_texts_fallback_without_dimensions(monkeypatch: pytest.MonkeyPatch) -> None:
    """embed_texts should retry without dimensions when provider rejects it."""
    calls = {"count": 0}

    async def fake_aembedding(**kwargs):  # noqa: ANN003
        calls["count"] += 1
        if "dimensions" in kwargs:
            raise RuntimeError("unsupported dimensions")
        return SimpleNamespace(data=[{"embedding": [0.1, 0.2, 0.3]}])

    monkeypatch.setattr("app.services.infra.embedding.litellm.aembedding", fake_aembedding)

    vectors = await embed_texts(
        ["hello"],
        config=EmbeddingConfig(provider="gemini", model="gemini-embedding-001"),
        dimensions=3,
        retries=0,
    )

    assert calls["count"] == 2
    assert vectors == [[0.1, 0.2, 0.3]]
