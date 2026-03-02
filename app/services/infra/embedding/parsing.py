"""Embedding response parsing."""

from __future__ import annotations

from typing import Any


def _extract_vector(
    item: Any,
    *,
    index: int | None = None,
    expected_dimensions: int | None = None,
) -> list[float]:
    """Extract embedding vector from LiteLLM response item."""
    if isinstance(item, dict):
        values = item.get("embedding")
    else:
        values = getattr(item, "embedding", None)

    if not isinstance(values, list) or not values:
        location = f" at index {index}" if index is not None else ""
        raise ValueError(
            f"Invalid embedding response item{location}: missing non-empty embedding list"
        )

    try:
        vector = [float(v) for v in values]
    except (TypeError, ValueError) as exc:
        location = f" at index {index}" if index is not None else ""
        raise ValueError(
            f"Invalid embedding response item{location}: embedding contains non-numeric values"
        ) from exc

    if expected_dimensions is not None and len(vector) != expected_dimensions:
        location = f" at index {index}" if index is not None else ""
        raise ValueError(
            f"Invalid embedding response item{location}: expected {expected_dimensions} values, got {len(vector)}"
        )

    return vector


def _extract_data_list(response: Any) -> list[Any]:
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        raise ValueError("Invalid embedding response: missing data list")
    if not data:
        raise ValueError("Invalid embedding response: data list is empty")
    return data


def extract_vectors_from_response(
    response: Any,
    *,
    expected_count: int | None = None,
    expected_dimensions: int | None = None,
) -> list[list[float]]:
    """Extract and validate embedding vectors from provider response."""
    data = _extract_data_list(response)
    vectors = [
        _extract_vector(item, index=index, expected_dimensions=expected_dimensions)
        for index, item in enumerate(data)
    ]

    if expected_count is not None and len(vectors) != expected_count:
        raise ValueError(
            f"Invalid embedding response: expected {expected_count} vectors, got {len(vectors)}"
        )

    return vectors
