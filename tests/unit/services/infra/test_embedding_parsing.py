"""Unit tests for embedding response parsing helpers."""

from types import SimpleNamespace

import pytest

from app.services.infra.embedding.parsing import _extract_vector, extract_vectors_from_response


def test_extract_vector_coerces_numeric_values() -> None:
    assert _extract_vector({"embedding": [1, "2", 3.5]}) == [1.0, 2.0, 3.5]


def test_extract_vector_rejects_non_numeric_values() -> None:
    with pytest.raises(ValueError, match="non-numeric"):
        _extract_vector({"embedding": ["nope", object()]}, index=0)


def test_extract_vectors_from_response_supports_dict_and_object_items() -> None:
    response = SimpleNamespace(
        data=[{"embedding": [0.1, 0.2]}, SimpleNamespace(embedding=[0.3, 0.4])]
    )
    vectors = extract_vectors_from_response(response, expected_count=2, expected_dimensions=2)
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


def test_extract_vectors_from_response_rejects_invalid_data_shape() -> None:
    with pytest.raises(ValueError, match="missing data list"):
        extract_vectors_from_response(SimpleNamespace(data=None))

    with pytest.raises(ValueError, match="data list is empty"):
        extract_vectors_from_response(SimpleNamespace(data=[]))


def test_extract_vectors_from_response_rejects_count_mismatch() -> None:
    response = SimpleNamespace(data=[{"embedding": [0.1, 0.2]}])
    with pytest.raises(ValueError, match="expected 2 vectors, got 1"):
        extract_vectors_from_response(response, expected_count=2)


def test_extract_vectors_from_response_rejects_dimension_mismatch() -> None:
    response = SimpleNamespace(data=[{"embedding": [0.1, 0.2, 0.3]}])
    with pytest.raises(ValueError, match="expected 2 values, got 3"):
        extract_vectors_from_response(response, expected_dimensions=2)
