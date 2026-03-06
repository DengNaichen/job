"""Single JD parsing workflow."""

from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas.structured_jd import CompactStructuredJD, StructuredJD
from app.services.infra.llm import complete_json

from app.services.domain.llm_parsing import merge_llm_and_rule_fields
from .llm_jd_input import prepare_job_description
from .prompts import EXTRACT_KEYWORDS_PROMPT, MAX_JD_PARSE_CHARS

CompleteJSONFn = Callable[..., Awaitable[dict[str, Any]]]


async def parse_jd(
    job_description: str,
    is_html: bool = False,
    *,
    title: str | None = None,
    complete_json_fn: CompleteJSONFn | None = None,
) -> StructuredJD:
    """Parse a JD and return normalized structured fields."""
    complete_json_impl = complete_json_fn or complete_json
    normalized_description = prepare_job_description(
        job_description,
        is_html=is_html,
        max_chars=None,
    )
    llm_description = normalized_description[:MAX_JD_PARSE_CHARS]
    prompt = EXTRACT_KEYWORDS_PROMPT.format(
        job_title=title or "Unknown",
        job_description=llm_description,
    )

    result = await complete_json_impl(
        prompt=prompt,
        system_prompt="You are an expert job description analyzer.",
        max_tokens=1200,
        response_schema=CompactStructuredJD,
    )

    return merge_llm_and_rule_fields(
        llm_payload=result,
        description=normalized_description,
        title=title,
    )
