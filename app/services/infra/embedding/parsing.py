"""Embedding response parsing."""

from __future__ import annotations

from typing import Any


def _extract_vector(item: Any) -> list[float]:
    """Extract embedding vector from LiteLLM response item."""
    if isinstance(item, dict):
        values = item.get("embedding")
    else:
        values = getattr(item, "embedding", None)

    if not isinstance(values, list) or not values:
        raise ValueError("Invalid embedding response item")

    return [float(v) for v in values]
