"""Deterministic education requirement extraction rules for JD parsing."""

from __future__ import annotations

import re

from app.schemas.structured_jd import degree_level_to_rank, normalize_degree_level

_DEGREE_CONTEXT_MARKERS = (
    "degree",
    "bachelor",
    "master",
    "phd",
    "doctorate",
    "associate",
    "diploma",
    "undergraduate",
    "education",
    "qualification",
    "university",
    "college",
    "tertiary",
    "post-secondary",
    "4-year",
)

_NONE_DEGREE_PATTERN = re.compile(
    r"\b("
    r"no degree"
    r"|degree not required"
    r"|no formal education"
    r"|equivalent experience"
    r"|experience in lieu of degree"
    r"|degree optional"
    r")\b",
    re.IGNORECASE,
)

_DEGREE_MARKERS: list[tuple[str, tuple[str, ...]]] = [
    (
        "associate",
        (
            "associate degree",
            "community college",
            "advanced diploma",
            "post-secondary diploma",
            "diploma",
        ),
    ),
    (
        "bachelor",
        (
            "bachelor",
            "b.a",
            "ba ",
            "b.s",
            "bs ",
            "undergraduate",
        ),
    ),
    (
        "master",
        (
            "master",
            "m.s",
            "ms ",
            "m.sc",
            "msc",
            "mba",
            "m.a",
            "ma ",
        ),
    ),
    (
        "doctorate",
        (
            "doctorate",
            "doctoral",
            "phd",
            "ph.d",
            "m.d",
            "md ",
            "juris doctor",
        ),
    ),
]

_EXTRA_BACHELOR_PATTERN = re.compile(
    r"\b("
    r"bs/ms"
    r"|ba/bs"
    r"|bs/ba"
    r"|bsc"
    r"|b\.sc"
    r"|4[-\s]?year degree"
    r"|university degree"
    r"|college degree"
    r"|tertiary qualification"
    r"|post[-\s]?secondary (?:education|qualification)"
    r")\b",
    re.IGNORECASE,
)

_EXTRA_MASTER_PATTERN = re.compile(
    r"\b("
    r"msc"
    r"|m\.sc"
    r"|meng"
    r"|m\.eng"
    r"|mba"
    r")\b",
    re.IGNORECASE,
)

_BACHELOR_MASTER_COMBO_PATTERN = re.compile(
    r"\b(?:ba|b\.a|bs|b\.s|bsc|b\.sc)\s*/\s*(?:ms|m\.s|msc|m\.sc|mba|meng|m\.eng)\b",
    re.IGNORECASE,
)


def _split_nonempty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _extract_degree_levels(line: str) -> list[str]:
    if _NONE_DEGREE_PATTERN.search(line):
        levels = ["none"]
    else:
        levels = []

    lowered = line.lower()
    for level, markers in _DEGREE_MARKERS:
        if any(marker in lowered for marker in markers):
            levels.append(level)

    if _EXTRA_BACHELOR_PATTERN.search(line):
        levels.append("bachelor")
    if _EXTRA_MASTER_PATTERN.search(line):
        levels.append("master")
    if _BACHELOR_MASTER_COMBO_PATTERN.search(line):
        levels.extend(["bachelor", "master"])

    return list(dict.fromkeys(levels))


def extract_min_degree_level(text: str) -> tuple[str, list[str]]:
    """Extract minimum degree level and source lines."""
    matched_lines: list[str] = []
    levels: list[str] = []

    for line in _split_nonempty_lines(text):
        lowered = line.lower()
        has_context = any(marker in lowered for marker in _DEGREE_CONTEXT_MARKERS)
        has_extra_hint = bool(
            _EXTRA_BACHELOR_PATTERN.search(line)
            or _EXTRA_MASTER_PATTERN.search(line)
            or _BACHELOR_MASTER_COMBO_PATTERN.search(line)
        )
        if not has_context and not has_extra_hint:
            continue

        line_levels = _extract_degree_levels(line)
        if not line_levels:
            continue
        levels.extend(line_levels)
        if line not in matched_lines:
            matched_lines.append(line)

    if not levels:
        return "unknown", []

    ranked_levels = [
        level for level in levels if level != "none" and degree_level_to_rank(level) >= 0
    ]
    if not ranked_levels:
        if "none" in levels:
            return "none", matched_lines[:2]
        return "unknown", matched_lines[:2]

    min_level = min(ranked_levels, key=degree_level_to_rank)
    return normalize_degree_level(min_level), matched_lines[:2]


__all__ = ["extract_min_degree_level"]
