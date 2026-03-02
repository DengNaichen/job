"""Embedding configuration helpers."""

from __future__ import annotations

from app.core.config import get_settings

from .types import EmbeddingConfig


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
