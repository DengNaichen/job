"""LiteLLM async client wrappers."""

import asyncio
import json
import logging
from typing import Any

import litellm
from pydantic import BaseModel, ValidationError

from .config import (
    _get_model_name,
    _normalize_api_base,
    _supports_json_mode,
    _supports_temperature,
    get_llm_config,
)
from .parsing import _extract_choice_content, _extract_choice_text, _extract_json
from .types import LLMConfig
from .usage import add_usage

logger = logging.getLogger(__name__)

# LLM timeout configuration (seconds)
LLM_TIMEOUT_HEALTH_CHECK = 30
LLM_TIMEOUT_COMPLETION = 120
LLM_TIMEOUT_JSON = 180


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
        except Exception:  # noqa: BLE001
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
                add_usage(model_name, prompt_tokens, completion_tokens)

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

        except json.JSONDecodeError as exc:
            last_error = exc
            logger.warning("JSON parse failed (attempt %s): %s", attempt + 1, exc)
            if attempt < retries:
                messages[-1]["content"] = (
                    prompt
                    + "\n\nIMPORTANT: Output ONLY a valid JSON object. Start with { and end with }."
                )
                continue
            raise ValueError(f"Failed to parse JSON after {retries + 1} attempts: {exc}")

        except ValidationError as exc:
            last_error = exc
            logger.warning("JSON schema validation failed (attempt %s): %s", attempt + 1, exc)
            if attempt < retries:
                messages[-1]["content"] = (
                    prompt + "\n\nIMPORTANT: Output ONLY valid JSON matching the required schema."
                )
                continue
            raise ValueError(f"Failed schema validation after {retries + 1} attempts: {exc}")

        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("LLM call failed (attempt %s): %s", attempt + 1, exc)
            if attempt < retries:
                err_text = str(exc).lower()
                if (
                    "ratelimit" in err_text
                    or "rate limit" in err_text
                    or "tpm" in err_text
                    or "429" in err_text
                ):
                    await asyncio.sleep(min(2**attempt, 8))
                continue
            raise

    raise ValueError(f"Failed after {retries + 1} attempts: {last_error}")
