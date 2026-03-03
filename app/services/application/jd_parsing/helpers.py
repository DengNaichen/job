"""Shared helpers for single/batch JD parsing."""

from collections.abc import Mapping
from typing import Any

from app.schemas.structured_jd import StructuredJD
from app.services.domain.jd_rules import extract_rule_based_fields, fallback_job_domain
from app.services.infra.html_utils import html_to_text

from .prompts import MAX_JD_PARSE_CHARS


def prepare_job_description(job_description: str, *, is_html: bool) -> str:
    """Normalize raw JD content before parsing."""
    if is_html:
        job_description = html_to_text(job_description)
    if len(job_description) > MAX_JD_PARSE_CHARS:
        job_description = job_description[:MAX_JD_PARSE_CHARS]
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

    if str(job_domain_normalized or "unknown") == "unknown":
        job_domain_normalized = fallback_job_domain(title, description)

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
