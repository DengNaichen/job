"""Token usage tracking for LLM integration."""

import logging
from typing import Any

import litellm

from .types import TokenUsage

logger = logging.getLogger(__name__)

# Global token tracker instance
_token_usage = TokenUsage()


def get_token_usage() -> TokenUsage:
    """Get the global token usage tracker."""
    return _token_usage


def _track_usage(kwargs: dict[str, Any], response: Any, start_time: float, end_time: float) -> None:
    """Callback to track token usage after each LLM call."""
    _ = (start_time, end_time)
    try:
        usage = getattr(response, "usage", None)
        if usage:
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            model = kwargs.get("model", "unknown")
            _token_usage.add_usage(model, prompt_tokens, completion_tokens)
            logger.debug(
                "Token usage: %s - prompt=%s, completion=%s",
                model,
                prompt_tokens,
                completion_tokens,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to track token usage: %s", exc)


# Register callback with LiteLLM.
litellm.success_callback = [_track_usage]
