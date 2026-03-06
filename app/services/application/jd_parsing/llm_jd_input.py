"""Prepare JD text input for LLM extraction."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.infra.text import html_to_text

from .prompts import MAX_JD_PARSE_CHARS


@dataclass(frozen=True)
class BatchLLMJDInput:
    """Pre-built batch input payload for LLM extraction."""

    jobs_text: str
    input_aliases: list[str]
    alias_to_job_id: dict[str, str]
    normalized_inputs: dict[str, dict[str, str | None]]

    @property
    def job_count(self) -> int:
        """Number of jobs included in this batch payload."""
        return len(self.input_aliases)


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


def build_batch_llm_jd_input(
    jobs: list[dict[str, str]],
    *,
    is_html: bool,
    max_jobs: int = 40,
) -> BatchLLMJDInput:
    """Build the concatenated batch prompt text and normalized job inputs.

    Note:
        The caller controls how many jobs are processed by deciding how many
        items to pass in ``jobs``. ``max_jobs`` is a safety guard only.
    """
    if max_jobs <= 0:
        raise ValueError("max_jobs must be > 0")
    if len(jobs) > max_jobs:
        raise ValueError(f"Batch size exceeds max_jobs: {len(jobs)} > {max_jobs}")

    jobs_parts: list[str] = []
    input_aliases: list[str] = []
    alias_to_job_id: dict[str, str] = {}
    normalized_inputs: dict[str, dict[str, str | None]] = {}

    for i, job in enumerate(jobs, start=1):
        alias = f"j{i}"
        job_id = job["job_id"]
        title = str(job.get("title") or "").strip()
        full_description = prepare_job_description(
            job["description"],
            is_html=is_html,
            max_chars=None,
        )
        llm_description = full_description[:MAX_JD_PARSE_CHARS]
        title_line = f"TITLE: {title}\n" if title else ""

        jobs_parts.append(f"--- JOB ID: {alias} ---\n{title_line}{llm_description}\n")
        input_aliases.append(alias)
        alias_to_job_id[alias] = job_id
        normalized_inputs[alias] = {
            "title": title or None,
            "description": full_description,
        }

    return BatchLLMJDInput(
        jobs_text="\n".join(jobs_parts),
        input_aliases=input_aliases,
        alias_to_job_id=alias_to_job_id,
        normalized_inputs=normalized_inputs,
    )


__all__ = ["BatchLLMJDInput", "prepare_job_description", "build_batch_llm_jd_input"]
