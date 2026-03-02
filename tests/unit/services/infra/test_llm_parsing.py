"""Unit tests for LLM response parsing helpers."""

import pytest

from app.services.infra.llm.parsing import (
    MAX_JSON_CONTENT_SIZE,
    _extract_choice_content,
    _extract_choice_text,
    _extract_json,
)


def test_extract_json_handles_markdown_json_fence() -> None:
    content = 'Some preface\n```json\n{"a": 1, "b": [1,2,3]}\n```\nignored'
    assert _extract_json(content) == '{"a": 1, "b": [1,2,3]}'


def test_extract_json_handles_nested_objects_and_escaped_quotes() -> None:
    content = (
        '{"outer": {"text": "hello \\\\\\"world\\\\\\"", "items": [{"k": 1}]}, "ok": true}'
        "\nextra trailing text"
    )
    assert _extract_json(content) == (
        '{"outer": {"text": "hello \\\\\\"world\\\\\\"", "items": [{"k": 1}]}, "ok": true}'
    )


def test_extract_json_rejects_missing_or_incomplete_json() -> None:
    with pytest.raises(ValueError, match="No JSON found"):
        _extract_json("no object here")

    with pytest.raises(ValueError, match="Incomplete JSON"):
        _extract_json('{"a": 1')


def test_extract_json_rejects_oversized_content() -> None:
    oversized = "x" * (MAX_JSON_CONTENT_SIZE + 1)
    with pytest.raises(ValueError, match="Content too large"):
        _extract_json(oversized)


def test_extract_choice_helpers_support_dict_and_structured_content() -> None:
    choice = {
        "message": {
            "content": [
                {"text": "first line"},
                {"content": [{"value": "second line"}]},
            ]
        }
    }
    assert _extract_choice_text(choice) == "first line\nsecond line"
    assert isinstance(_extract_choice_content(choice), list)
