"""Unit tests for LLM config helpers."""

from app.services.infra.llm.config import (
    _get_model_name,
    _normalize_api_base,
    _supports_json_mode,
    _supports_temperature,
)
from app.services.infra.llm.types import LLMConfig


def test_normalize_api_base_handles_provider_specific_suffix() -> None:
    assert _normalize_api_base("anthropic", "https://api.anthropic.com/v1") == (
        "https://api.anthropic.com"
    )
    assert _normalize_api_base("gemini", "https://example.com/v1/") == "https://example.com"
    assert _normalize_api_base("openai", "https://api.openai.com/v1") == "https://api.openai.com/v1"
    assert _normalize_api_base("openai", None) is None


def test_get_model_name_applies_expected_provider_prefixes() -> None:
    assert (
        _get_model_name(LLMConfig(provider="anthropic", model="claude-3-5-sonnet"))
        == "anthropic/claude-3-5-sonnet"
    )
    assert (
        _get_model_name(LLMConfig(provider="openrouter", model="openai/gpt-4o-mini"))
        == "openrouter/openai/gpt-4o-mini"
    )
    assert (
        _get_model_name(LLMConfig(provider="openrouter", model="openrouter/openai/gpt-4o-mini"))
        == "openrouter/openai/gpt-4o-mini"
    )
    assert (
        _get_model_name(LLMConfig(provider="openai", model="anthropic/claude-3.5-sonnet"))
        == "anthropic/claude-3.5-sonnet"
    )


def test_supports_temperature_blocks_gpt5_models() -> None:
    assert _supports_temperature("openai", "gpt-4o-mini") is True
    assert _supports_temperature("openai", "gpt-5-mini") is False


def test_supports_json_mode_for_supported_providers_and_models() -> None:
    assert _supports_json_mode("openai", "gpt-4o-mini") is True
    assert _supports_json_mode("anthropic", "claude-3.5-sonnet") is True
    assert _supports_json_mode("openrouter", "openai/gpt-4o-mini") is True
    assert _supports_json_mode("openrouter", "meta-llama/llama-3.2") is False
    assert _supports_json_mode("ollama", "llama3.1") is False
