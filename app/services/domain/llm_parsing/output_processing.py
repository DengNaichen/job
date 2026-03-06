"""Domain helpers for LLM JD payload parsing and post-processing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.schemas.structured_jd import StructuredJD
from app.services.domain.rule_parsing import extract_rule_based_fields


def parse_llm_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize compact/full LLM payloads into canonical JD fields.

    Note:
        ``key_responsibilities`` and ``keywords`` are intentionally excluded
        from the LLM parsing contract.
    """
    if "required_skills" in payload or "job_domain_normalized" in payload:
        required_skills = payload.get("required_skills", [])
        preferred_skills = payload.get("preferred_skills", [])
        job_domain_raw = payload.get("job_domain_raw")
        job_domain_normalized = payload.get("job_domain_normalized", "unknown")
    else:
        required_skills = payload.get("s", [])
        preferred_skills = []
        job_domain_raw = None
        job_domain_normalized = payload.get("d", "unknown")

    return {
        "required_skills": required_skills,
        "preferred_skills": preferred_skills,
        "job_domain_raw": job_domain_raw,
        "job_domain_normalized": job_domain_normalized,
    }


def parse_llm_payload_batch(
    payloads_by_alias: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Normalize a batch of LLM payloads keyed by alias."""
    return {alias: parse_llm_payload(payload) for alias, payload in payloads_by_alias.items()}


def _build_structured_jd(
    *,
    llm_fields: Mapping[str, Any],
    rule_fields: Mapping[str, object],
) -> StructuredJD:
    merged = {
        "required_skills": llm_fields["required_skills"],
        "preferred_skills": llm_fields["preferred_skills"],
        "experience_requirements": rule_fields.get("experience_requirements", []),
        "education_requirements": rule_fields.get("education_requirements", []),
        "experience_years": rule_fields.get("experience_years"),
        "seniority_level": rule_fields.get("seniority_level"),
        "sponsorship_not_available": rule_fields.get("sponsorship_not_available", "unknown"),
        "job_domain_raw": llm_fields["job_domain_raw"],
        "job_domain_normalized": llm_fields["job_domain_normalized"],
        "min_degree_level": rule_fields.get("min_degree_level", "unknown"),
    }
    return StructuredJD.model_validate(merged)


def merge_llm_and_rule_fields(
    *,
    llm_payload: Mapping[str, Any],
    description: str,
    title: str | None,
) -> StructuredJD:
    """Merge single-item LLM payload with deterministic rule fields."""
    llm_fields = parse_llm_payload(llm_payload)
    rule_fields = extract_rule_based_fields(description, title=title)
    return _build_structured_jd(llm_fields=llm_fields, rule_fields=rule_fields)


def merge_llm_and_rule_fields_batch(
    *,
    llm_payloads_by_alias: Mapping[str, Mapping[str, Any]],
    normalized_inputs_by_alias: Mapping[str, Mapping[str, str | None]],
    input_aliases: Sequence[str],
) -> dict[str, StructuredJD]:
    """Merge batch LLM payloads with deterministic rule fields per alias."""
    parsed_llm_by_alias = parse_llm_payload_batch(llm_payloads_by_alias)
    merged_by_alias: dict[str, StructuredJD] = {}

    for alias in input_aliases:
        llm_fields = parsed_llm_by_alias.get(alias)
        if llm_fields is None:
            continue

        normalized = normalized_inputs_by_alias.get(alias)
        if normalized is None:
            continue

        description = str(normalized.get("description") or "")
        raw_title = normalized.get("title")
        title = raw_title if isinstance(raw_title, str) else None
        rule_fields = extract_rule_based_fields(description, title=title)
        merged_by_alias[alias] = _build_structured_jd(
            llm_fields=llm_fields,
            rule_fields=rule_fields,
        )

    return merged_by_alias


__all__ = [
    "parse_llm_payload",
    "parse_llm_payload_batch",
    "merge_llm_and_rule_fields",
    "merge_llm_and_rule_fields_batch",
]
