"""Types for LLM integration."""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


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


class LLMConfig(BaseModel):
    """LLM configuration model."""

    provider: str
    model: str
    api_key: str | None = None
    api_base: str | None = None
