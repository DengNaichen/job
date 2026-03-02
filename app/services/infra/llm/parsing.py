"""Response parsing helpers for LLM integration."""

from typing import Any

# JSON extraction safety limits
MAX_JSON_EXTRACTION_RECURSION = 50
MAX_JSON_CONTENT_SIZE = 1024 * 1024  # 1MB


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
    message = (
        getattr(choice, "message", None)
        if hasattr(choice, "message")
        else choice.get("message")
        if isinstance(choice, dict)
        else None
    )

    if message:
        content = (
            getattr(message, "content", None)
            if hasattr(message, "content")
            else message.get("content")
            if isinstance(message, dict)
            else None
        )
        if content:
            parts = _extract_text_parts(content)
            if parts:
                return "\n".join(parts)

    return None


def _extract_choice_content(choice: Any) -> Any:
    """Extract raw content from a LiteLLM choice object."""
    message = (
        getattr(choice, "message", None)
        if hasattr(choice, "message")
        else choice.get("message")
        if isinstance(choice, dict)
        else None
    )
    if not message:
        return None
    return (
        getattr(message, "content", None)
        if hasattr(message, "content")
        else message.get("content")
        if isinstance(message, dict)
        else None
    )


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
