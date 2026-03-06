"""Prepare JD text input for LLM extraction."""

from app.services.infra.text import html_to_text

from .prompts import MAX_JD_PARSE_CHARS


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


__all__ = ["prepare_job_description"]
