"""Configuration helpers for LLM integration."""

from app.core.config import get_settings

from .types import LLMConfig

# OpenRouter JSON-capable models
OPENROUTER_JSON_CAPABLE_MODELS = {
    "anthropic/claude-3-opus",
    "anthropic/claude-3-sonnet",
    "anthropic/claude-3-haiku",
    "anthropic/claude-3.5-sonnet",
    "anthropic/claude-3.5-haiku",
    "anthropic/claude-haiku-4-5-20251001",
    "anthropic/claude-sonnet-4-20250514",
    "anthropic/claude-opus-4-20250514",
    "openai/gpt-4-turbo",
    "openai/gpt-4",
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "openai/gpt-3.5-turbo",
    "google/gemini-pro",
    "google/gemini-1.5-pro",
    "google/gemini-1.5-flash",
    "google/gemini-2.0-flash",
    "deepseek/deepseek-chat",
    "deepseek/deepseek-reasoner",
}


def get_llm_config() -> LLMConfig:
    """Get LLM configuration from settings."""
    settings = get_settings()
    return LLMConfig(
        provider=settings.llm_provider,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        api_base=settings.llm_api_base,
    )


def _normalize_api_base(provider: str, api_base: str | None) -> str | None:
    """Normalize api_base for LiteLLM provider-specific expectations."""
    if not api_base:
        return None

    base = api_base.strip().rstrip("/")

    if provider == "anthropic" and base.endswith("/v1"):
        base = base[: -len("/v1")].rstrip("/")
    if provider == "gemini" and base.endswith("/v1"):
        base = base[: -len("/v1")].rstrip("/")

    return base or None


def _get_model_name(config: LLMConfig) -> str:
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


def _supports_temperature(provider: str, model: str) -> bool:
    """Return whether passing `temperature` is supported."""
    _ = provider
    if "gpt-5" in model.lower():
        return False
    return True


def _supports_json_mode(provider: str, model: str) -> bool:
    """Check if the model supports JSON mode."""
    json_mode_providers = ["openai", "anthropic", "gemini", "deepseek"]
    if provider in json_mode_providers:
        return True
    if provider == "openrouter":
        return model in OPENROUTER_JSON_CAPABLE_MODELS
    return False
