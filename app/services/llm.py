"""LiteLLM wrapper for multi-provider AI support.

简化版，复用自 Resume-Matcher，去掉了 config_path 相关逻辑。
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import litellm
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# LLM timeout configuration (seconds)
LLM_TIMEOUT_HEALTH_CHECK = 30
LLM_TIMEOUT_COMPLETION = 120
LLM_TIMEOUT_JSON = 180


# ============================================
# Token Usage Tracking
# ============================================

@dataclass
class TokenUsage:
    """Track token usage across LLM calls."""
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_requests: int = 0
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def add_usage(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        """Add token usage from a single request."""
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens
        self.total_requests += 1

        if model not in self.by_model:
            self.by_model[model] = {"prompt": 0, "completion": 0, "requests": 0}
        self.by_model[model]["prompt"] += prompt_tokens
        self.by_model[model]["completion"] += completion_tokens
        self.by_model[model]["requests"] += 1

    @property
    def total_tokens(self) -> int:
        return self.total_prompt_tokens + self.total_completion_tokens

    def summary(self) -> dict[str, Any]:
        """Return a summary of token usage."""
        return {
            "total_requests": self.total_requests,
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "by_model": self.by_model,
        }

    def reset(self) -> None:
        """Reset all counters."""
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0
        self.by_model = {}


# Global token tracker instance
_token_usage = TokenUsage()


def get_token_usage() -> TokenUsage:
    """Get the global token usage tracker."""
    return _token_usage


def _track_usage(kwargs: dict[str, Any], response: Any, start_time: float, end_time: float) -> None:
    """Callback to track token usage after each LLM call."""
    try:
        usage = getattr(response, "usage", None)
        if usage:
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            model = kwargs.get("model", "unknown")
            _token_usage.add_usage(model, prompt_tokens, completion_tokens)
            logger.debug(f"Token usage: {model} - prompt={prompt_tokens}, completion={completion_tokens}")
    except Exception as e:
        logger.warning(f"Failed to track token usage: {e}")


# Register callback with LiteLLM
litellm.success_callback = [_track_usage]

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

# JSON extraction safety limits
MAX_JSON_EXTRACTION_RECURSION = 50
MAX_JSON_CONTENT_SIZE = 1024 * 1024  # 1MB


class LLMConfig(BaseModel):
    """LLM configuration model."""

    provider: str
    model: str
    api_key: str | None = None
    api_base: str | None = None


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


def _extract_text_parts(value: Any, depth: int = 0, max_depth: int = 10) -> list[str]:
    """Recursively extract text segments from nested response structures."""
    if depth >= max_depth or value is None:
        return []

    if isinstance(value, str):
        return [value] if value.strip() else []

    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(_extract_text_parts(item, depth + 1, max_depth))
        return parts

    if isinstance(value, dict):
        for key in ("text", "content", "value"):
            if key in value:
                return _extract_text_parts(value[key], depth + 1, max_depth)
        return []

    if hasattr(value, "content"):
        return _extract_text_parts(getattr(value, "content"), depth + 1, max_depth)

    return []


def _extract_choice_text(choice: Any) -> str | None:
    """Extract plain text from a LiteLLM choice object."""
    message = getattr(choice, "message", None) if hasattr(choice, "message") else choice.get("message") if isinstance(choice, dict) else None

    if message:
        content = getattr(message, "content", None) if hasattr(message, "content") else message.get("content") if isinstance(message, dict) else None
        if content:
            parts = _extract_text_parts(content)
            if parts:
                return "\n".join(parts)

    return None


def _extract_choice_content(choice: Any) -> Any:
    """Extract raw content from a LiteLLM choice object."""
    message = getattr(choice, "message", None) if hasattr(choice, "message") else choice.get("message") if isinstance(choice, dict) else None
    if not message:
        return None
    return getattr(message, "content", None) if hasattr(message, "content") else message.get("content") if isinstance(message, dict) else None


def _extract_json(content: str) -> str:
    """Extract JSON from LLM response, handling various formats."""
    if len(content) > MAX_JSON_CONTENT_SIZE:
        raise ValueError(f"Content too large: {len(content)} bytes")

    original = content

    # Remove markdown code blocks
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        parts = content.split("```")
        if len(parts) >= 2:
            content = parts[1]
            if content.startswith(("json", "JSON")):
                content = content[4:]

    content = content.strip()

    # Find the first { and extract complete JSON object
    start_idx = content.find("{")
    if start_idx == -1:
        raise ValueError(f"No JSON found in response: {original[:200]}")

    json_content = content[start_idx:]

    # Find matching braces
    depth = 0
    end_idx = -1
    in_string = False
    escape_next = False

    for i, char in enumerate(json_content):
        if escape_next:
            escape_next = False
            continue
        if char == "\\":
            escape_next = True
            continue
        if char == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                end_idx = i
                break

    if end_idx != -1:
        return json_content[: end_idx + 1]

    raise ValueError(f"Incomplete JSON in response: {original[:200]}")


async def complete_json(
    prompt: str,
    system_prompt: str | None = None,
    config: LLMConfig | None = None,
    max_tokens: int = 4096,
    retries: int = 2,
    response_schema: type[BaseModel] | None = None,
) -> dict[str, Any]:
    """Make a completion request expecting JSON response."""
    if config is None:
        config = get_llm_config()

    model_name = _get_model_name(config)

    json_system = (
        system_prompt or ""
    ) + "\n\nYou must respond with valid JSON only. No explanations, no markdown."
    messages = [
        {"role": "system", "content": json_system},
        {"role": "user", "content": prompt},
    ]

    use_json_mode = _supports_json_mode(config.provider, config.model)
    supports_response_schema = False
    if response_schema is not None:
        try:
            supports_response_schema = litellm.supports_response_schema(
                model=model_name,
                custom_llm_provider=config.provider,
            )
        except Exception:
            logger.debug(
                "Failed to detect response schema support for model=%s provider=%s",
                model_name,
                config.provider,
                exc_info=True,
            )

    last_error = None
    for attempt in range(retries + 1):
        try:
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": messages,
                "custom_llm_provider": config.provider,
                "max_tokens": max_tokens,
                "api_key": config.api_key,
                "api_base": _normalize_api_base(config.provider, config.api_base),
                "timeout": LLM_TIMEOUT_JSON,
            }
            if _supports_temperature(config.provider, model_name):
                temperatures = [0.1, 0.3, 0.5, 0.7]
                kwargs["temperature"] = temperatures[min(attempt, len(temperatures) - 1)]

            if response_schema is not None and supports_response_schema:
                kwargs["response_format"] = response_schema
            elif use_json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            response = await litellm.acompletion(**kwargs)

            # Track token usage
            usage = getattr(response, "usage", None)
            if usage:
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                _token_usage.add_usage(model_name, prompt_tokens, completion_tokens)

            content = _extract_choice_text(response.choices[0])
            if not content:
                raw_content = _extract_choice_content(response.choices[0])
                if isinstance(raw_content, dict):
                    if response_schema is not None:
                        return response_schema.model_validate(raw_content).model_dump(mode="python")
                    return raw_content

            if not content:
                raise ValueError("Empty response from LLM")

            json_str = _extract_json(content)
            if response_schema is not None:
                return response_schema.model_validate_json(json_str).model_dump(mode="python")
            return json.loads(json_str)

        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(f"JSON parse failed (attempt {attempt + 1}): {e}")
            if attempt < retries:
                messages[-1]["content"] = (
                    prompt
                    + "\n\nIMPORTANT: Output ONLY a valid JSON object. Start with { and end with }."
                )
                continue
            raise ValueError(f"Failed to parse JSON after {retries + 1} attempts: {e}")

        except ValidationError as e:
            last_error = e
            logger.warning(f"JSON schema validation failed (attempt {attempt + 1}): {e}")
            if attempt < retries:
                messages[-1]["content"] = (
                    prompt
                    + "\n\nIMPORTANT: Output ONLY valid JSON matching the required schema."
                )
                continue
            raise ValueError(f"Failed schema validation after {retries + 1} attempts: {e}")

        except Exception as e:
            last_error = e
            logger.warning(f"LLM call failed (attempt {attempt + 1}): {e}")
            if attempt < retries:
                err_text = str(e).lower()
                if "ratelimit" in err_text or "rate limit" in err_text or "tpm" in err_text or "429" in err_text:
                    await asyncio.sleep(min(2 ** attempt, 8))
                continue
            raise

    raise ValueError(f"Failed after {retries + 1} attempts: {last_error}")
