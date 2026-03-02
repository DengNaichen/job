"""Unit tests for scoped LLM token usage accounting."""

from __future__ import annotations

import asyncio

import pytest

from app.services.infra.llm import get_token_usage
from app.services.infra.llm.usage import add_usage, snapshot_usage, start_usage_scope


def test_usage_defaults_to_global_tracker() -> None:
    usage = get_token_usage()
    usage.reset()

    add_usage("model-a", 10, 5)
    summary = snapshot_usage()

    assert summary["total_requests"] == 1
    assert summary["prompt_tokens"] == 10
    assert summary["completion_tokens"] == 5
    assert summary["total_tokens"] == 15
    usage.reset()


def test_start_usage_scope_isolated_from_global_tracker() -> None:
    global_usage = get_token_usage()
    global_usage.reset()
    add_usage("global-model", 3, 2)

    with start_usage_scope():
        add_usage("scoped-model", 7, 1)
        scoped_summary = snapshot_usage()
        assert scoped_summary["total_requests"] == 1
        assert scoped_summary["total_tokens"] == 8
        assert "scoped-model" in scoped_summary["by_model"]

    global_summary = get_token_usage().summary()
    assert global_summary["total_requests"] == 1
    assert global_summary["total_tokens"] == 5
    assert "global-model" in global_summary["by_model"]
    assert "scoped-model" not in global_summary["by_model"]
    global_usage.reset()


def test_nested_usage_scope_restores_parent_scope() -> None:
    get_token_usage().reset()

    with start_usage_scope():
        add_usage("outer", 2, 2)
        assert snapshot_usage()["total_tokens"] == 4

        with start_usage_scope():
            add_usage("inner", 1, 1)
            assert snapshot_usage()["total_tokens"] == 2
            assert "inner" in snapshot_usage()["by_model"]

        outer_summary = snapshot_usage()
        assert outer_summary["total_tokens"] == 4
        assert "outer" in outer_summary["by_model"]
        assert "inner" not in outer_summary["by_model"]


@pytest.mark.asyncio
async def test_usage_scope_isolation_for_concurrent_tasks() -> None:
    get_token_usage().reset()

    async def worker(label: str, prompt_tokens: int) -> dict[str, int]:
        with start_usage_scope():
            add_usage(label, prompt_tokens, 1)
            await asyncio.sleep(0)
            add_usage(label, prompt_tokens, 1)
            summary = snapshot_usage()
            return {
                "total_tokens": int(summary["total_tokens"]),
                "prompt_tokens": int(summary["prompt_tokens"]),
            }

    first, second = await asyncio.gather(worker("a", 3), worker("b", 9))

    assert first["prompt_tokens"] == 6
    assert first["total_tokens"] == 8
    assert second["prompt_tokens"] == 18
    assert second["total_tokens"] == 20
    assert get_token_usage().summary()["total_tokens"] == 0
