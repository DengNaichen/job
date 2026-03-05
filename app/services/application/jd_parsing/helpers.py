"""Shared helpers for single/batch JD parsing."""

from collections.abc import Mapping
from typing import Any

from app.schemas.structured_jd import StructuredJD
from app.services.domain.jd_rules import extract_rule_based_fields
from app.services.infra.text import html_to_text

from .prompts import MAX_JD_PARSE_CHARS


def prepare_job_description(
    job_description: str,
    *,
    is_html: bool,
    max_chars: int | None = MAX_JD_PARSE_CHARS,
) -> str:
    """Normalize raw JD content before parsing.

    Args:
        job_description: Raw job description input.
        is_html: Whether input is HTML and requires conversion.
        max_chars: Optional truncation limit. ``None`` keeps full text.
    """
    if is_html:
        job_description = html_to_text(job_description)
    if max_chars is not None and len(job_description) > max_chars:
        job_description = job_description[:max_chars]
    return job_description


def merge_llm_and_rule_fields(
    *,
    llm_payload: Mapping[str, Any],
    description: str,
    title: str | None,
) -> StructuredJD:
    """Merge compact LLM output with deterministic rule-based fields."""
    rule_fields = extract_rule_based_fields(description, title=title)

    if "required_skills" in llm_payload or "job_domain_normalized" in llm_payload:
        required_skills = llm_payload.get("required_skills", [])
        preferred_skills = llm_payload.get("preferred_skills", [])
        key_responsibilities = llm_payload.get("key_responsibilities", [])
        keywords = llm_payload.get("keywords", [])
        job_domain_raw = llm_payload.get("job_domain_raw")
        job_domain_normalized = llm_payload.get("job_domain_normalized", "unknown")
    else:
        required_skills = llm_payload.get("s", [])
        preferred_skills = []
        key_responsibilities = []
        keywords = []
        job_domain_raw = None
        job_domain_normalized = llm_payload.get("d", "unknown")

    merged = {
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "experience_requirements": rule_fields.get("experience_requirements", []),
        "education_requirements": rule_fields.get("education_requirements", []),
        "key_responsibilities": key_responsibilities,
        "keywords": keywords,
        "experience_years": rule_fields.get("experience_years"),
        "seniority_level": rule_fields.get("seniority_level"),
        "sponsorship_not_available": rule_fields.get("sponsorship_not_available", "unknown"),
        "job_domain_raw": job_domain_raw,
        "job_domain_normalized": job_domain_normalized,
        "min_degree_level": rule_fields.get("min_degree_level", "unknown"),
    }
    return StructuredJD.model_validate(merged)
