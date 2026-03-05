"""Deterministic experience requirement extraction rules for JD parsing."""

from __future__ import annotations

import re

_YEAR_PATTERN = re.compile(
    r"(?P<low>\d{1,2})\s*(?:\+|plus)?\s*(?:[-–—to]{1,3}\s*(?P<high>\d{1,2}))?\s+years?",
    re.IGNORECASE,
)

_EXPERIENCE_CONTEXT_MARKERS = (
    "experience",
    "experienced",
    "work experience",
    "relevant",
    "background",
)


def _split_nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract_experience(text: str) -> tuple[int | None, list[str]]:
    """Extract minimum experience years and source lines."""
    years: list[int] = []
    matched_lines: list[str] = []
    for line in _split_nonempty_lines(text):
        lowered = line.lower()
        if not any(marker in lowered for marker in _EXPERIENCE_CONTEXT_MARKERS):
            continue
        matches = list(_YEAR_PATTERN.finditer(line))
        if not matches:
            continue
        lows = [int(match.group("low")) for match in matches]
        years.extend(lows)
        if line not in matched_lines:
            matched_lines.append(line)

    return (max(years) if years else None, matched_lines[:2])


__all__ = ["extract_experience"]
