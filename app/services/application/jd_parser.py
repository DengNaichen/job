"""Backward-compatible facade for JD parsing workflows."""

from collections.abc import Mapping
from typing import Any

from app.schemas.structured_jd import BatchStructuredJD, StructuredJD
from app.services.application.jd_parsing import parse_jd as _parse_jd_impl
from app.services.application.jd_parsing import parse_jd_batch as _parse_jd_batch_impl
from app.services.application.jd_parsing.helpers import (
    merge_llm_and_rule_fields as _merge_llm_and_rule_fields_impl,
)
from app.services.application.jd_parsing.helpers import (
    prepare_job_description as _prepare_job_description_impl,
)
from app.services.application.jd_parsing.prompts import (
    BATCH_EXTRACT_PROMPT,
    DEFAULT_BATCH_MAX_TOKENS,
    EXTRACT_KEYWORDS_PROMPT,
    GEMINI_BATCH_MAX_TOKENS,
    MAX_JD_PARSE_CHARS,
)
from app.services.infra.llm import complete_json, get_llm_config

_prepare_job_description = _prepare_job_description_impl


def _merge_llm_and_rule_fields(
    *,
    llm_payload: Mapping[str, Any],
    description: str,
    title: str | None,
) -> StructuredJD:
    """Compatibility wrapper for previous private helper."""
    return _merge_llm_and_rule_fields_impl(
        llm_payload=llm_payload,
        description=description,
        title=title,
    )


async def parse_jd(
    job_description: str,
    is_html: bool = False,
    *,
    title: str | None = None,
) -> StructuredJD:
    """Parse a single JD and return structured fields."""
    return await _parse_jd_impl(
        job_description=job_description,
        is_html=is_html,
        title=title,
        complete_json_fn=complete_json,
    )


async def parse_jd_batch(
    jobs: list[dict[str, str]],
    is_html: bool = False,
) -> BatchStructuredJD:
    """Batch parse multiple JDs and return ordered structured fields."""
    return await _parse_jd_batch_impl(
        jobs=jobs,
        is_html=is_html,
        complete_json_fn=complete_json,
        get_llm_config_fn=get_llm_config,
    )


__all__ = [
    "BATCH_EXTRACT_PROMPT",
    "DEFAULT_BATCH_MAX_TOKENS",
    "EXTRACT_KEYWORDS_PROMPT",
    "GEMINI_BATCH_MAX_TOKENS",
    "MAX_JD_PARSE_CHARS",
    "_merge_llm_and_rule_fields",
    "_prepare_job_description",
    "parse_jd",
    "parse_jd_batch",
]
