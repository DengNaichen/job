"""Shared job payload normalization helpers for application services."""

from __future__ import annotations

from typing import Any

from app.services.infra.text import html_to_text


def hydrate_description_plain(
    payload: dict[str, Any],
    *,
    description_html: object,
) -> None:
    """Backfill description_plain from HTML when plain text is absent."""
    if (
        not payload.get("description_plain")
        and isinstance(description_html, str)
        and description_html.strip()
    ):
        payload["description_plain"] = html_to_text(description_html)


def drop_legacy_job_payload_fields(
    payload: dict[str, Any],
    *,
    include_source: bool = False,
) -> None:
    """Remove non-Job columns before constructing/updating Job rows."""
    payload.pop("location_hints", None)
    if include_source:
        payload.pop("source", None)
