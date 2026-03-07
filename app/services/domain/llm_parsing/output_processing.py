"""Domain helpers for LLM JD payload parsing and post-processing."""

from __future__ import annotations

from functools import lru_cache
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.schemas.structured_jd import StructuredJD
from app.services.domain.rule_parsing import extract_rule_based_fields
from app.services.domain.skills_alignment import load_alias_table, normalize_skill_text

logger = logging.getLogger(__name__)


def _normalize_skill_list(value: object) -> list[str]:
    """Normalize list-like input into deduped list[str]."""
    if value is None:
        return []
    if isinstance(value, list):
        normalized = [str(item).strip() for item in value if str(item).strip()]
    else:
        text = str(value).strip()
        normalized = [text] if text else []

    deduped: list[str] = []
    seen: set[str] = set()
    for item in normalized:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


@lru_cache(maxsize=8)
def _load_alignment_alias_map(
    alias_table_path: str,
    alias_patch_path: str | None,
) -> dict[str, tuple[str, str]]:
    table_path = Path(alias_table_path)
    if not table_path.exists():
        logger.warning("skills alignment alias table not found: %s", table_path)
        return {}

    alias_map = load_alias_table(table_path)
    if alias_patch_path:
        patch_path = Path(alias_patch_path)
        if patch_path.exists():
            alias_map.update(load_alias_table(patch_path))
        else:
            logger.warning("skills alignment alias patch not found: %s", patch_path)
    return alias_map


def _align_required_skills(value: object) -> list[str]:
    """Map required_skills to canonical labels when alias mapping is enabled."""
    raw_skills = _normalize_skill_list(value)
    if not raw_skills:
        return []

    settings = get_settings()
    if not settings.skills_alignment_enabled:
        return raw_skills

    alias_map = _load_alignment_alias_map(
        settings.skills_alias_table_path,
        settings.skills_alias_patch_path,
    )
    if not alias_map:
        return raw_skills

    aligned: list[str] = []
    seen: set[str] = set()
    for raw in raw_skills:
        normalized = normalize_skill_text(raw)
        if not normalized:
            continue
        entry = alias_map.get(normalized)
        mapped_value = (entry[1].strip() if entry else normalized) or normalized
        key = mapped_value.lower()
        if key in seen:
            continue
        seen.add(key)
        aligned.append(mapped_value)
    return aligned


def parse_llm_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize compact/full LLM payloads into canonical JD fields.

    Note:
        ``key_responsibilities`` and ``keywords`` are intentionally excluded
        from the LLM parsing contract.
    """
    if "required_skills" in payload or "job_domain_normalized" in payload:
        required_skills = _align_required_skills(payload.get("required_skills", []))
        preferred_skills = _normalize_skill_list(payload.get("preferred_skills", []))
        job_domain_raw = payload.get("job_domain_raw")
        job_domain_normalized = payload.get("job_domain_normalized", "unknown")
    else:
        required_skills = _align_required_skills(payload.get("s", []))
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
