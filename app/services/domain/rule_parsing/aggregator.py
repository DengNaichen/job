"""Aggregate deterministic JD rule parsing fields."""

from __future__ import annotations

import re

from .education import extract_min_degree_level
from .experience import extract_experience
from .seniority import infer_seniority_level
from .sponsorship import extract_sponsorship


def _normalize_text(text: str) -> str:
    """Collapse whitespace for regex parsing."""
    return re.sub(r"\s+", " ", text).strip()


def extract_rule_based_fields(text: str, *, title: str | None = None) -> dict[str, object]:
    """Extract deterministic JD fields with regex/rules."""
    normalized = _normalize_text(text)
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


__all__ = ["extract_rule_based_fields"]
