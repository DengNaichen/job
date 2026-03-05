"""Rule-based extraction helpers for low-cost JD parsing."""

from __future__ import annotations

import re

from app.schemas.structured_jd import normalize_job_domain_name, normalize_sponsorship
from app.services.domain.rule_parsing.education import extract_min_degree_level

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

def normalize_text(text: str) -> str:
    """Collapse whitespace for regex parsing."""
    return re.sub(r"\s+", " ", text).strip()


def split_nonempty_lines(text: str) -> list[str]:
    """Split text into trimmed non-empty lines."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract_sponsorship(text: str) -> str:
    """Extract sponsorship availability from raw JD text."""
    return normalize_sponsorship(text)


def extract_experience(text: str) -> tuple[int | None, list[str]]:
    """Extract minimum experience years and source lines."""
    years: list[int] = []
    matched_lines: list[str] = []
    for line in split_nonempty_lines(text):
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


def infer_seniority_level(title: str | None, experience_years: int | None = None) -> str | None:
    """Infer seniority from title first, then years fallback."""
    lowered = (title or "").strip().lower()

    if lowered:
        patterns: list[tuple[str, tuple[str, ...]]] = [
            ("intern", ("intern", "internship")),
            ("principal", ("principal", "staff", "architect")),
            ("director", ("director", "head", "vice president", "vp", "chief")),
            ("manager", ("manager", "mgr")),
            ("lead", ("lead",)),
            ("senior", ("senior", "sr ", "sr.", "staff engineer")),
            ("junior", ("junior", "jr ", "jr.", "associate", "coordinator", "assistant")),
        ]
        for level, markers in patterns:
            if any(marker in lowered for marker in markers):
                return level

    if experience_years is None:
        return None
    if experience_years <= 1:
        return "junior"
    if experience_years >= 8:
        return "senior"
    if experience_years >= 5:
        return "mid"
    return "mid"


def extract_rule_based_fields(text: str, *, title: str | None = None) -> dict[str, object]:
    """Extract deterministic JD fields with regex/rules."""
    normalized = normalize_text(text)
    experience_years, experience_requirements = extract_experience(text)
    min_degree_level, education_requirements = extract_min_degree_level(text)

    return {
        "sponsorship_not_available": extract_sponsorship(normalized),
        "experience_years": experience_years,
        "experience_requirements": experience_requirements,
        "education_requirements": education_requirements,
        "min_degree_level": min_degree_level,
        "seniority_level": infer_seniority_level(title, experience_years),
    }


def fallback_job_domain(title: str | None, text: str) -> str:
    """Cheap fallback for role domain when LLM returns unknown."""
    seed = " ".join(part for part in (title or "", text[:800]) if part).strip()
    return normalize_job_domain_name(seed)
