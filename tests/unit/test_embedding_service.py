"""Unit tests for embedding LiteLLM wrapper."""

from types import SimpleNamespace

import pytest

from app.services.embedding import EmbeddingConfig, embed_texts, resolve_embedding_model_name


def test_resolve_embedding_model_name() -> None:
    """Model name should follow provider prefix rules."""
    openai_cfg = EmbeddingConfig(provider="openai", model="Qwen/Qwen3-Embedding-8B")
    gemini_cfg = EmbeddingConfig(provider="gemini", model="gemini-embedding-001")

    assert resolve_embedding_model_name(openai_cfg) == "Qwen/Qwen3-Embedding-8B"
    assert resolve_embedding_model_name(gemini_cfg) == "gemini/gemini-embedding-001"


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

    monkeypatch.setattr("app.services.embedding.litellm.aembedding", fake_aembedding)

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

    monkeypatch.setattr("app.services.embedding.litellm.aembedding", fake_aembedding)

    vectors = await embed_texts(
        ["hello"],
        config=EmbeddingConfig(provider="gemini", model="gemini-embedding-001"),
        dimensions=3,
        retries=0,
    )

    assert calls["count"] == 2
    assert vectors == [[0.1, 0.2, 0.3]]
