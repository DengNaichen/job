"""LLM-based recommendation layer for late-stage match reranking."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.services.jd_rules import infer_seniority_level
from app.services.llm import LLMConfig, complete_json, get_llm_config, get_token_usage
from app.services.matching import (
    infer_user_degree_rank,
    infer_user_job_domain,
    infer_user_seniority_level,
    to_optional_int,
)

logger = logging.getLogger(__name__)

LLM_ADJUSTMENT_MAP: dict[str, float] = {
    "strong_yes": 0.03,
    "yes": 0.015,
    "maybe": 0.0,
    "stretch": -0.015,
    "no": -0.03,
}

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(all\s+)?above",
    r"forget\s+(everything|all)",
    r"new\s+instructions?:",
    r"system\s*:",
    r"<\s*/?\s*system\s*>",
    r"\[\s*INST\s*\]",
    r"\[\s*/\s*INST\s*\]",
]

_MAX_SUMMARY_CHARS = 500
_MAX_SKILLS = 20
_MAX_WORK_HISTORY = 3
_MAX_BULLETS_PER_JOB = 2
_MAX_BULLET_CHARS = 160
_MAX_TITLE_CHARS = 120
_MAX_COMPANY_CHARS = 120
_MAX_REQUIRED_SKILLS = 8
_MAX_PREFERRED_SKILLS = 8
_MAX_RESPONSIBILITIES = 4
_MAX_LIST_ITEM_CHARS = 160

LLM_MATCH_SYSTEM_PROMPT = """You are a conservative job-fit reviewer.

The candidate has already passed hard filters. Use only the provided JSON input.
Do not invent candidate experience, skills, degrees, responsibilities, or job requirements.
Choose recommendation from exactly one of:
- strong_yes
- yes
- maybe
- stretch
- no

Recommendation meanings:
- strong_yes: highly aligned, prioritize applying
- yes: solid fit, worth applying
- maybe: mixed signals, possible but not obvious
- stretch: possible reach, materially challenging
- no: not recommended

Return valid JSON only. Keep reasons, gaps, and resume_focus_points short, factual, and grounded in the input."""


class LLMRecommendationEnum(str, Enum):
    """Discrete recommendation labels for top-N reranking."""

    STRONG_YES = "strong_yes"
    YES = "yes"
    MAYBE = "maybe"
    STRETCH = "stretch"
    NO = "no"


def _normalize_output_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]

    normalized: list[str] = []
    for item in value:
        text = re.sub(r"\s+", " ", str(item or "")).strip()
        if not text:
            continue
        normalized.append(text[:_MAX_LIST_ITEM_CHARS])
        if len(normalized) == 3:
            break
    return normalized


class LLMMatchRecommendation(BaseModel):
    """Structured recommendation returned by the LLM."""

    recommendation: LLMRecommendationEnum
    reasons: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    resume_focus_points: list[str] = Field(default_factory=list)

    @field_validator("reasons", "gaps", "resume_focus_points", mode="before")
    @classmethod
    def _validate_short_lists(cls, value: object) -> list[str]:
        return _normalize_output_list(value)


def _empty_token_usage_summary() -> dict[str, Any]:
    return {
        "total_requests": 0,
        "total_tokens": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "by_model": {},
    }


def build_disabled_llm_rerank_summary() -> dict[str, Any]:
    """Return a stable summary payload when LLM reranking is disabled."""

    return {
        "enabled": False,
        "window_size": 0,
        "attempted_count": 0,
        "succeeded_count": 0,
        "failed_count": 0,
        "concurrency": 0,
        "reorder_applied": False,
        "adjustment_map": dict(LLM_ADJUSTMENT_MAP),
        "token_usage": _empty_token_usage_summary(),
    }


def _sanitize_free_text(value: object, *, max_chars: int) -> str:
    text = str(value or "")
    for pattern in _INJECTION_PATTERNS:
        text = re.sub(pattern, "[REDACTED]", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def _coerce_string_list(
    value: object,
    *,
    limit: int,
    item_max_chars: int,
    sanitize: bool,
) -> list[str]:
    if not isinstance(value, list):
        return []

    items: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            continue
        item = (
            _sanitize_free_text(raw, max_chars=item_max_chars)
            if sanitize
            else re.sub(r"\s+", " ", raw).strip()[:item_max_chars]
        )
        if not item:
            continue
        items.append(item)
        if len(items) == limit:
            break
    return items


def _parse_structured_jd(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _extract_recent_work_history(user_data: dict[str, Any]) -> list[dict[str, Any]]:
    work_history = user_data.get("workHistory")
    if not isinstance(work_history, list):
        return []

    items: list[dict[str, Any]] = []
    for entry in work_history:
        if not isinstance(entry, dict):
            continue

        bullets_source = entry.get("bullets")
        if not isinstance(bullets_source, list):
            bullets_source = entry.get("achievements")
        if not isinstance(bullets_source, list):
            description = entry.get("description")
            bullets_source = [description] if isinstance(description, str) and description.strip() else []

        item = {
            "title": _sanitize_free_text(entry.get("title"), max_chars=_MAX_TITLE_CHARS),
            "company": _sanitize_free_text(entry.get("company"), max_chars=_MAX_COMPANY_CHARS),
            "bullets": _coerce_string_list(
                bullets_source,
                limit=_MAX_BULLETS_PER_JOB,
                item_max_chars=_MAX_BULLET_CHARS,
                sanitize=True,
            ),
        }
        items.append(item)
        if len(items) == _MAX_WORK_HISTORY:
            break

    return items


def _build_job_profile(context_row: dict[str, Any]) -> dict[str, Any]:
    structured_jd = _parse_structured_jd(context_row.get("structured_jd"))
    jd_years = to_optional_int(context_row.get("jd_experience_years"))
    seniority = structured_jd.get("seniority_level")
    if not isinstance(seniority, str) or not seniority.strip():
        seniority = infer_seniority_level(str(context_row.get("title") or "").strip(), jd_years)

    responsibilities = _coerce_string_list(
        structured_jd.get("key_responsibilities"),
        limit=_MAX_RESPONSIBILITIES,
        item_max_chars=_MAX_LIST_ITEM_CHARS,
        sanitize=True,
    )

    return {
        "title": _sanitize_free_text(context_row.get("title"), max_chars=_MAX_TITLE_CHARS),
        "location_text": _sanitize_free_text(context_row.get("location_text"), max_chars=_MAX_TITLE_CHARS),
        "employment_type": _sanitize_free_text(context_row.get("employment_type"), max_chars=_MAX_TITLE_CHARS),
        "department": _sanitize_free_text(context_row.get("department"), max_chars=_MAX_TITLE_CHARS),
        "team": _sanitize_free_text(context_row.get("team"), max_chars=_MAX_TITLE_CHARS),
        "job_domain_normalized": str(context_row.get("job_domain_normalized") or "unknown"),
        "min_degree_level": str(context_row.get("min_degree_level") or "unknown"),
        "structured_jd": {
            "required_skills": _coerce_string_list(
                structured_jd.get("required_skills"),
                limit=_MAX_REQUIRED_SKILLS,
                item_max_chars=_MAX_LIST_ITEM_CHARS,
                sanitize=False,
            ),
            "preferred_skills": _coerce_string_list(
                structured_jd.get("preferred_skills"),
                limit=_MAX_PREFERRED_SKILLS,
                item_max_chars=_MAX_LIST_ITEM_CHARS,
                sanitize=False,
            ),
            "experience_years": jd_years,
            "seniority_level": seniority or None,
            "key_responsibilities": responsibilities,
        },
    }


def _build_deterministic_match(ranked_row: dict[str, Any]) -> dict[str, Any]:
    return {
        "final_score": float(ranked_row.get("final_score") or 0.0),
        "cosine_score": float(ranked_row.get("cosine_score") or 0.0),
        "skill_overlap_score": float(ranked_row.get("skill_overlap_score") or 0.0),
        "domain_match_score": float(ranked_row.get("domain_match_score") or 0.0),
        "seniority_match_score": float(ranked_row.get("seniority_match_score") or 0.0),
        "experience_gap": to_optional_int(ranked_row.get("experience_gap")),
        "education_gap": to_optional_int(ranked_row.get("education_gap")),
    }


def build_llm_match_payload(
    user_data: dict[str, Any],
    ranked_row: dict[str, Any],
    context_row: dict[str, Any],
) -> dict[str, Any]:
    """Build a compact, grounded payload for LLM recommendation."""

    skills = _coerce_string_list(
        user_data.get("skills"),
        limit=_MAX_SKILLS,
        item_max_chars=_MAX_LIST_ITEM_CHARS,
        sanitize=False,
    )
    return {
        "candidate_profile": {
            "summary": _sanitize_free_text(user_data.get("summary"), max_chars=_MAX_SUMMARY_CHARS),
            "skills": skills,
            "total_years_experience": to_optional_int(user_data.get("totalYearsExperience")),
            "highest_degree_rank": infer_user_degree_rank(user_data),
            "inferred_domain": infer_user_job_domain(user_data),
            "inferred_seniority": infer_user_seniority_level(user_data),
            "recent_work_history": _extract_recent_work_history(user_data),
        },
        "job_profile": _build_job_profile(context_row),
        "deterministic_match": _build_deterministic_match(ranked_row),
    }


def get_llm_adjustment(recommendation: LLMRecommendationEnum | str | None) -> float:
    """Map recommendation enum to a small reranking adjustment."""

    if recommendation is None:
        return 0.0
    key = recommendation.value if isinstance(recommendation, LLMRecommendationEnum) else str(recommendation)
    return LLM_ADJUSTMENT_MAP.get(key, 0.0)


def attach_default_llm_fields(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return row copies with stable LLM output fields present."""

    prepared: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        base_score = float(item.get("final_score") or 0.0)
        item["llm_recommendation"] = None
        item["llm_reasons"] = []
        item["llm_gaps"] = []
        item["llm_resume_focus_points"] = []
        item["llm_adjustment"] = 0.0
        item["llm_adjusted_score"] = round(base_score, 6)
        item["llm_enriched"] = False
        prepared.append(item)
    return prepared


async def get_llm_match_recommendation(
    user_data: dict[str, Any],
    ranked_row: dict[str, Any],
    context_row: dict[str, Any],
    *,
    config: LLMConfig | None = None,
) -> LLMMatchRecommendation:
    """Get a discrete LLM recommendation for a single user-job pair."""

    config = config or get_llm_config()
    if config.provider != "ollama" and not config.api_key:
        raise ValueError("LLM rerank requested but LLM is not configured")

    payload = build_llm_match_payload(user_data, ranked_row, context_row)
    prompt = (
        "Evaluate this candidate-job pair using only the JSON below.\n"
        "Return a recommendation and short, factual explanations.\n\n"
        f"Input JSON:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    result = await complete_json(
        prompt=prompt,
        system_prompt=LLM_MATCH_SYSTEM_PROMPT,
        config=config,
        max_tokens=800,
        response_schema=LLMMatchRecommendation,
    )
    return LLMMatchRecommendation.model_validate(result)


async def apply_llm_rerank(
    rows: list[dict[str, Any]],
    *,
    user_data: dict[str, Any],
    context_by_job_id: dict[str, dict[str, Any]],
    llm_top_n: int,
    concurrency: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply LLM recommendation and light reranking to a top-N window."""

    if llm_top_n < 1:
        raise ValueError("llm_top_n must be >= 1")
    if concurrency < 1:
        raise ValueError("concurrency must be >= 1")

    config = get_llm_config()
    if config.provider != "ollama" and not config.api_key:
        raise ValueError("LLM rerank requested but LLM is not configured")

    prepared_rows = attach_default_llm_fields(rows)
    window_size = min(llm_top_n, len(prepared_rows))
    token_usage = get_token_usage()
    token_usage.reset()

    if window_size == 0:
        summary = {
            "enabled": True,
            "window_size": 0,
            "attempted_count": 0,
            "succeeded_count": 0,
            "failed_count": 0,
            "concurrency": concurrency,
            "reorder_applied": False,
            "adjustment_map": dict(LLM_ADJUSTMENT_MAP),
            "token_usage": _empty_token_usage_summary(),
        }
        return prepared_rows, summary

    semaphore = asyncio.Semaphore(concurrency)
    llm_window = prepared_rows[:window_size]

    async def _process_one(index: int, row: dict[str, Any]) -> tuple[int, dict[str, Any], bool]:
        job_id = str(row.get("job_id") or "")
        context_row = context_by_job_id.get(job_id, {})
        async with semaphore:
            try:
                recommendation = await get_llm_match_recommendation(
                    user_data,
                    row,
                    context_row,
                    config=config,
                )
            except Exception as exc:
                logger.warning(
                    "LLM match recommendation failed for job_id=%s: %s",
                    job_id or "<unknown>",
                    exc,
                )
                return index, row, False

        adjustment = get_llm_adjustment(recommendation.recommendation)
        base_score = float(row.get("final_score") or 0.0)
        enriched = dict(row)
        enriched["llm_recommendation"] = recommendation.recommendation.value
        enriched["llm_reasons"] = recommendation.reasons
        enriched["llm_gaps"] = recommendation.gaps
        enriched["llm_resume_focus_points"] = recommendation.resume_focus_points
        enriched["llm_adjustment"] = round(adjustment, 6)
        enriched["llm_adjusted_score"] = round(base_score + adjustment, 6)
        enriched["llm_enriched"] = True
        return index, enriched, True

    results = await asyncio.gather(
        *(_process_one(index, row) for index, row in enumerate(llm_window))
    )

    succeeded_count = 0
    failed_count = 0
    ordered_window = list(llm_window)
    for index, row, succeeded in results:
        ordered_window[index] = row
        if succeeded:
            succeeded_count += 1
        else:
            failed_count += 1

    original_order = [str(row.get("job_id") or "") for row in ordered_window]
    reordered_window = sorted(
        ordered_window,
        key=lambda item: (
            float(item.get("llm_adjusted_score") or 0.0),
            float(item.get("final_score") or 0.0),
        ),
        reverse=True,
    )
    reorder_applied = [str(row.get("job_id") or "") for row in reordered_window] != original_order
    token_summary = token_usage.summary()
    token_usage.reset()

    summary = {
        "enabled": True,
        "window_size": window_size,
        "attempted_count": window_size,
        "succeeded_count": succeeded_count,
        "failed_count": failed_count,
        "concurrency": concurrency,
        "reorder_applied": reorder_applied,
        "adjustment_map": dict(LLM_ADJUSTMENT_MAP),
        "token_usage": token_summary,
    }
    return reordered_window + prepared_rows[window_size:], summary
