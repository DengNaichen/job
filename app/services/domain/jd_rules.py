"""Rule-based extraction helpers for low-cost JD parsing."""

from __future__ import annotations

import re

from app.schemas.structured_jd import normalize_job_domain_name
from app.services.domain.rule_parsing.education import extract_min_degree_level
from app.services.domain.rule_parsing.experience import extract_experience
from app.services.domain.rule_parsing.seniority import infer_seniority_level
from app.services.domain.rule_parsing.sponsorship import extract_sponsorship

def normalize_text(text: str) -> str:
    """Collapse whitespace for regex parsing."""
    return re.sub(r"\s+", " ", text).strip()


def split_nonempty_lines(text: str) -> list[str]:
    """Split text into trimmed non-empty lines."""
    return [line.strip() for line in text.splitlines() if line.strip()]


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
