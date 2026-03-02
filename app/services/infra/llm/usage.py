"""Token usage tracking for LLM integration."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from .types import TokenUsage

# Fallback tracker for legacy call sites that rely on process-wide counters.
_global_token_usage = TokenUsage()
_usage_scope_var: ContextVar[TokenUsage | None] = ContextVar("llm_usage_scope", default=None)


def _current_usage() -> TokenUsage:
    scoped = _usage_scope_var.get()
    if scoped is not None:
        return scoped
    return _global_token_usage


def get_token_usage() -> TokenUsage:
    """Get the current token usage tracker (scoped when available)."""
    return _current_usage()


def add_usage(model: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Add token usage to the active usage scope."""
    _current_usage().add_usage(model, prompt_tokens, completion_tokens)


def snapshot_usage() -> dict[str, Any]:
    """Return usage summary for the active usage scope."""
    return _current_usage().summary()


@contextmanager
def start_usage_scope() -> Iterator[TokenUsage]:
    """Create an isolated request-local token usage scope."""
    scope_usage = TokenUsage()
    token = _usage_scope_var.set(scope_usage)
    try:
        yield scope_usage
    finally:
        _usage_scope_var.reset(token)
