"""Batch JD parsing workflow."""

from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas.structured_jd import BatchStructuredJD, BatchStructuredJDItem, CompactBatchStructuredJD
from app.services.infra.llm import complete_json, get_llm_config
from app.services.infra.llm.types import LLMConfig

from app.services.domain.llm_parsing import merge_llm_and_rule_fields_batch
from .llm_jd_input import build_batch_llm_jd_input
from .prompts import (
    BATCH_EXTRACT_PROMPT,
    DEFAULT_BATCH_MAX_TOKENS,
    GEMINI_BATCH_MAX_TOKENS,
)

CompleteJSONFn = Callable[..., Awaitable[dict[str, Any]]]
GetLLMConfigFn = Callable[[], LLMConfig]


async def parse_jd_batch(
    jobs: list[dict[str, str]],
    is_html: bool = False,
    *,
    complete_json_fn: CompleteJSONFn | None = None,
    get_llm_config_fn: GetLLMConfigFn | None = None,
) -> BatchStructuredJD:
    """Batch parse multiple JDs and return ordered results."""
    complete_json_impl = complete_json_fn or complete_json
    get_llm_config_impl = get_llm_config_fn or get_llm_config

    if not jobs:
        return BatchStructuredJD(jobs=[])

    input_job_ids = [job["job_id"] for job in jobs]
    duplicate_input_job_ids = sorted(
        job_id for job_id, count in Counter(input_job_ids).items() if count > 1
    )
    if duplicate_input_job_ids:
        raise ValueError("Duplicate job_id in input jobs: " + ", ".join(duplicate_input_job_ids))

    batch_input = build_batch_llm_jd_input(jobs, is_html=is_html)
    input_alias_set = set(batch_input.input_aliases)

    prompt = BATCH_EXTRACT_PROMPT.format(count=batch_input.job_count, jobs_text=batch_input.jobs_text)

    config = get_llm_config_impl()
    batch_max_tokens = (
        GEMINI_BATCH_MAX_TOKENS if config.provider == "gemini" else DEFAULT_BATCH_MAX_TOKENS
    )

    result = await complete_json_impl(
        prompt=prompt,
        system_prompt="You are an expert job description analyzer. Process all jobs accurately.",
        config=config,
        max_tokens=batch_max_tokens,
        response_schema=CompactBatchStructuredJD,
    )

    raw_jobs = result.get("jobs", []) if isinstance(result, dict) else []
    raw_items_by_alias: dict[str, dict[str, Any]] = {}
    duplicate_output_job_ids: list[str] = []
    for raw_item in raw_jobs:
        if not isinstance(raw_item, dict):
            continue
        raw_id = raw_item.get("i") or raw_item.get("job_id")
        if not isinstance(raw_id, str):
            continue
        if raw_id in raw_items_by_alias:
            duplicate_output_job_ids.append(raw_id)
            continue
        raw_items_by_alias[raw_id] = raw_item

    merged_by_alias = merge_llm_and_rule_fields_batch(
        llm_payloads_by_alias=raw_items_by_alias,
        normalized_inputs_by_alias=batch_input.normalized_inputs,
        input_aliases=batch_input.input_aliases,
    )

    merged_items: list[BatchStructuredJDItem] = []
    output_job_ids: list[str] = []
    for alias in batch_input.input_aliases:
        merged = merged_by_alias.get(alias)
        if merged is None:
            continue

        job_id = batch_input.alias_to_job_id[alias]
        merged_items.append(
            BatchStructuredJDItem(
                job_id=job_id,
                **merged.model_dump(mode="python"),
            )
        )
        output_job_ids.append(job_id)

    output_job_id_set = set(output_job_ids)

    duplicate_output_job_ids = sorted(
        set(duplicate_output_job_ids)
        | {
            job_id
            for job_id, count in Counter(output_job_ids).items()
            if count > 1
        }
    )
    missing_job_ids = [job_id for job_id in input_job_ids if job_id not in output_job_id_set]
    unexpected_job_ids = sorted(
        raw_id for raw_id in raw_items_by_alias if raw_id not in input_alias_set
    )

    if (
        duplicate_output_job_ids
        or missing_job_ids
        or unexpected_job_ids
        or len(output_job_ids) != len(input_job_ids)
    ):
        raise ValueError(
            "Batch JD parse returned inconsistent jobs. "
            f"expected_count={len(input_job_ids)}, actual_count={len(output_job_ids)}, "
            f"duplicate_output_job_ids={duplicate_output_job_ids}, "
            f"missing_job_ids={missing_job_ids}, "
            f"unexpected_job_ids={unexpected_job_ids}"
        )

    output_items_by_id = {item.job_id: item for item in merged_items}
    ordered_jobs = [output_items_by_id[job_id] for job_id in input_job_ids]
    return BatchStructuredJD(jobs=ordered_jobs)
