"""Batch JD parsing workflow."""

from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas.structured_jd import BatchStructuredJD, BatchStructuredJDItem, CompactBatchStructuredJD
from app.services.infra.llm import complete_json, get_llm_config
from app.services.infra.llm.types import LLMConfig

from .helpers import merge_llm_and_rule_fields, prepare_job_description
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
    complete_json_fn: CompleteJSONFn = complete_json,
    get_llm_config_fn: GetLLMConfigFn = get_llm_config,
) -> BatchStructuredJD:
    """Batch parse multiple JDs and return ordered results."""
    if not jobs:
        return BatchStructuredJD(jobs=[])

    input_job_ids = [job["job_id"] for job in jobs]
    duplicate_input_job_ids = sorted(
        job_id for job_id, count in Counter(input_job_ids).items() if count > 1
    )
    if duplicate_input_job_ids:
        raise ValueError("Duplicate job_id in input jobs: " + ", ".join(duplicate_input_job_ids))

    jobs_parts: list[str] = []
    normalized_inputs: dict[str, dict[str, str | None]] = {}
    for job in jobs:
        job_id = job["job_id"]
        title = str(job.get("title") or "").strip()
        description = prepare_job_description(job["description"], is_html=is_html)
        title_line = f"TITLE: {title}\n" if title else ""
        jobs_parts.append(f"--- JOB ID: {job_id} ---\n{title_line}{description}\n")
        normalized_inputs[job_id] = {
            "title": title or None,
            "description": description,
        }

    jobs_text = "\n".join(jobs_parts)
    prompt = BATCH_EXTRACT_PROMPT.format(count=len(jobs), jobs_text=jobs_text)

    config = get_llm_config_fn()
    batch_max_tokens = (
        GEMINI_BATCH_MAX_TOKENS if config.provider == "gemini" else DEFAULT_BATCH_MAX_TOKENS
    )

    result = await complete_json_fn(
        prompt=prompt,
        system_prompt="You are an expert job description analyzer. Process all jobs accurately.",
        config=config,
        max_tokens=batch_max_tokens,
        response_schema=CompactBatchStructuredJD,
    )

    raw_jobs = result.get("jobs", []) if isinstance(result, dict) else []
    raw_items_by_id: dict[str, dict[str, Any]] = {}
    duplicate_output_job_ids: list[str] = []
    for raw_item in raw_jobs:
        if not isinstance(raw_item, dict):
            continue
        raw_id = raw_item.get("i") or raw_item.get("job_id")
        if not isinstance(raw_id, str):
            continue
        if raw_id in raw_items_by_id:
            duplicate_output_job_ids.append(raw_id)
            continue
        raw_items_by_id[raw_id] = raw_item

    merged_items: list[BatchStructuredJDItem] = []
    output_job_ids: list[str] = []
    for job_id in input_job_ids:
        raw_item = raw_items_by_id.get(job_id)
        if raw_item is None:
            continue

        normalized = normalized_inputs[job_id]
        merged = merge_llm_and_rule_fields(
            llm_payload=raw_item,
            description=str(normalized["description"]),
            title=normalized["title"],
        )
        merged_items.append(
            BatchStructuredJDItem(
                job_id=job_id,
                **merged.model_dump(mode="python"),
            )
        )
        output_job_ids.append(job_id)

    input_job_id_set = set(input_job_ids)
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
        job_id for job_id in raw_items_by_id if job_id not in input_job_id_set
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
