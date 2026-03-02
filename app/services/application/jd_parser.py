"""JD parsing service using LLM.

复用 Resume-Matcher 的 EXTRACT_KEYWORDS_PROMPT，
用 Pydantic 做结构化输出校验。
"""

import logging
from collections import Counter

from app.schemas.structured_jd import (
    BatchStructuredJD,
    BatchStructuredJDItem,
    CompactBatchStructuredJD,
    CompactStructuredJD,
    StructuredJD,
)
from app.services.domain.jd_rules import extract_rule_based_fields, fallback_job_domain
from app.services.infra.text import html_to_text
from app.services.infra.llm import complete_json, get_llm_config

logger = logging.getLogger(__name__)
MAX_JD_PARSE_CHARS = 6000
DEFAULT_BATCH_MAX_TOKENS = 8192
GEMINI_BATCH_MAX_TOKENS = 65536

EXTRACT_KEYWORDS_PROMPT = """Extract only the non-deterministic job fields as compact JSON.

Return EXACTLY:
{{
  "d": "job_domain_normalized",
  "s": ["required_skill_1", "required_skill_2"]
}}

Field meanings:
- d = role/function domain, not employer company sector
- s = required hard skills only

Allowed d values:
software_engineering, data_ai, product_program, design, sales_account_management,
marketing_growth, finance_treasury, operations, customer_support, hr_recruiting,
legal_compliance, cybersecurity, unknown

Rules:
1. Output valid JSON only.
2. Use at most 6 skills in s.
3. Keep skill phrases short, concrete, and deduplicated.
4. Do not output soft skills unless they are core screening criteria.
5. Do not repeat years, degree, sponsorship, responsibilities, or keywords.

Job title:
{job_title}

Job description:
{job_description}"""


def _prepare_job_description(job_description: str, *, is_html: bool) -> str:
    """Normalize raw JD content before parsing."""
    if is_html:
        job_description = html_to_text(job_description)
    if len(job_description) > MAX_JD_PARSE_CHARS:
        job_description = job_description[:MAX_JD_PARSE_CHARS]
    return job_description


def _merge_llm_and_rule_fields(
    *,
    llm_payload: dict[str, object],
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


async def parse_jd(
    job_description: str,
    is_html: bool = False,
    *,
    title: str | None = None,
) -> StructuredJD:
    """解析 JD 并返回结构化数据。

    Args:
        job_description: 原始 JD 文本或 HTML
        is_html: 如果是 HTML，会先转换成纯文本

    Returns:
        StructuredJD: 结构化的 JD 数据

    Raises:
        ValueError: 如果 LLM 输出无法解析为 StructuredJD
    """
    job_description = _prepare_job_description(job_description, is_html=is_html)
    prompt = EXTRACT_KEYWORDS_PROMPT.format(
        job_title=title or "Unknown",
        job_description=job_description,
    )

    result = await complete_json(
        prompt=prompt,
        system_prompt="You are an expert job description analyzer.",
        max_tokens=1200,
        response_schema=CompactStructuredJD,
    )

    return _merge_llm_and_rule_fields(
        llm_payload=result,
        description=job_description,
        title=title,
    )


# 批量解析的 prompt
BATCH_EXTRACT_PROMPT = """Extract only the non-deterministic job fields for ALL jobs below.

Output EXACTLY:
{{
  "jobs": [
    {{"i": "job_id", "d": "job_domain_normalized", "s": ["required_skill_1"]}}
  ]
}}

Field meanings:
- i = exact job_id from input
- d = role/function domain, not employer company sector
- s = required hard skills only

Allowed d values:
software_engineering, data_ai, product_program, design, sales_account_management,
marketing_growth, finance_treasury, operations, customer_support, hr_recruiting,
legal_compliance, cybersecurity, unknown

Rules:
1. Process ALL {count} jobs and include every exact i.
2. Use at most 6 skills in s for each job.
3. Keep skill phrases short, concrete, and deduplicated.
4. Do not output soft skills unless they are core screening criteria.
5. Do not output years, degree, sponsorship, responsibilities, or keywords.

Jobs to process:
{jobs_text}"""


async def parse_jd_batch(
    jobs: list[dict[str, str]],
    is_html: bool = False,
) -> BatchStructuredJD:
    """批量解析多个 JD。

    Args:
        jobs: 列表，每个元素包含 {"job_id": str, "description": str, "title"?: str}
        is_html: 如果描述是 HTML，会先转换成纯文本

    Returns:
        BatchStructuredJD: 批量解析结果

    Raises:
        ValueError: 如果 LLM 输出无法解析
    """
    if not jobs:
        return BatchStructuredJD(jobs=[])

    input_job_ids = [job["job_id"] for job in jobs]
    duplicate_input_job_ids = sorted(
        job_id for job_id, count in Counter(input_job_ids).items() if count > 1
    )
    if duplicate_input_job_ids:
        raise ValueError("Duplicate job_id in input jobs: " + ", ".join(duplicate_input_job_ids))

    # 构建 jobs 文本
    jobs_parts = []
    for job in jobs:
        job_id = job["job_id"]
        title = str(job.get("title") or "").strip()
        description = _prepare_job_description(job["description"], is_html=is_html)
        title_line = f"TITLE: {title}\n" if title else ""
        jobs_parts.append(f"--- JOB ID: {job_id} ---\n{title_line}{description}\n")

    jobs_text = "\n".join(jobs_parts)
    prompt = BATCH_EXTRACT_PROMPT.format(count=len(jobs), jobs_text=jobs_text)

    config = get_llm_config()
    batch_max_tokens = (
        GEMINI_BATCH_MAX_TOKENS if config.provider == "gemini" else DEFAULT_BATCH_MAX_TOKENS
    )

    result = await complete_json(
        prompt=prompt,
        system_prompt="You are an expert job description analyzer. Process all jobs accurately.",
        config=config,
        max_tokens=batch_max_tokens,
        response_schema=CompactBatchStructuredJD,
    )

    raw_jobs = result.get("jobs", []) if isinstance(result, dict) else []
    merged_items: list[BatchStructuredJDItem] = []
    output_job_ids: list[str] = []
    for job in jobs:
        input_job_id = job["job_id"]
        title = str(job.get("title") or "").strip() or None
        description = _prepare_job_description(job["description"], is_html=is_html)

        raw_item = next(
            (
                item
                for item in raw_jobs
                if (
                    isinstance(item, dict)
                    and (item.get("i") == input_job_id or item.get("job_id") == input_job_id)
                )
            ),
            None,
        )
        if raw_item is None:
            continue

        merged = _merge_llm_and_rule_fields(
            llm_payload=raw_item,
            description=description,
            title=title,
        )
        merged_items.append(
            BatchStructuredJDItem(
                job_id=input_job_id,
                **merged.model_dump(mode="python"),
            )
        )
        output_job_ids.append(input_job_id)

    input_job_id_set = set(input_job_ids)
    output_job_id_set = set(output_job_ids)

    duplicate_output_job_ids = sorted(
        job_id for job_id, count in Counter(output_job_ids).items() if count > 1
    )
    missing_job_ids = [job_id for job_id in input_job_ids if job_id not in output_job_id_set]
    unexpected_job_ids = sorted(
        job_id for job_id in output_job_id_set if job_id not in input_job_id_set
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

    # 保持输出顺序与输入一致，便于调用方对齐
    output_items_by_id = {item.job_id: item for item in merged_items}
    ordered_jobs = [output_items_by_id[job_id] for job_id in input_job_ids]
    return BatchStructuredJD(jobs=ordered_jobs)
