from __future__ import annotations

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job, WorkplaceType
from app.services.domain.job_location import (
    StructuredLocation,
    parse_location_text,
    sync_job_location,
    sync_primary_to_job,
)


def _full_snapshot_geonames_resolver() -> Any:
    # Keep geonames lookup behind package export so tests can monkeypatch
    # app.services.application.full_snapshot_sync.get_geonames_resolver.
    import app.services.application.full_snapshot_sync as full_snapshot_sync

    return full_snapshot_sync.get_geonames_resolver()


def _clean_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _coerce_workplace_type(value: object) -> WorkplaceType:
    if isinstance(value, WorkplaceType):
        return value
    if isinstance(value, str):
        try:
            return WorkplaceType(value)
        except ValueError:
            return WorkplaceType.unknown
    return WorkplaceType.unknown


def _is_structured_location_usable(location: StructuredLocation) -> bool:
    return bool(location.city or location.region or location.country_code)


def _build_structured_locations(payload: dict[str, Any]) -> list[StructuredLocation]:
    hints = payload.get("location_hints")
    structured_locations: list[StructuredLocation] = []

    if isinstance(hints, list):
        for hint in hints:
            if not isinstance(hint, dict):
                continue
            structured = StructuredLocation(
                city=_clean_optional_str(hint.get("city")),
                region=_clean_optional_str(hint.get("region")),
                country_code=_clean_optional_str(hint.get("country_code")),
                workplace_type=_coerce_workplace_type(hint.get("workplace_type")),
                remote_scope=_clean_optional_str(hint.get("remote_scope")),
            )
            if _is_structured_location_usable(structured):
                structured_locations.append(structured)

    if structured_locations:
        return structured_locations

    # Compatibility fallback for mappers that still emit job-level location fields.
    location_text = _clean_optional_str(payload.get("location_text"))
    fallback = StructuredLocation(
        city=_clean_optional_str(payload.get("location_city")),
        region=_clean_optional_str(payload.get("location_region")),
        country_code=_clean_optional_str(payload.get("location_country_code")),
        workplace_type=_coerce_workplace_type(payload.get("location_workplace_type")),
        remote_scope=_clean_optional_str(payload.get("location_remote_scope")),
    )

    if location_text:
        parsed = parse_location_text(location_text)
        fallback.city = fallback.city or parsed.city
        fallback.region = fallback.region or parsed.region
        fallback.country_code = fallback.country_code or parsed.country_code
        if fallback.workplace_type == WorkplaceType.unknown:
            fallback.workplace_type = parsed.workplace_type
        fallback.remote_scope = fallback.remote_scope or parsed.remote_scope

    if not fallback.country_code and fallback.city:
        city_match = _full_snapshot_geonames_resolver().resolve_city(
            city=fallback.city,
            region=fallback.region,
        )
        if city_match:
            fallback.country_code = city_match.country_code
            fallback.region = fallback.region or city_match.admin1_code

    if _is_structured_location_usable(fallback):
        return [fallback]

    return []


async def sync_staged_job_locations(
    *,
    session: AsyncSession,
    staged_jobs: list[Job],
    unique_payloads: list[dict[str, Any]],
) -> None:
    payload_by_external_id = {
        str(payload["external_job_id"]): payload for payload in unique_payloads
    }
    for job in staged_jobs:
        payload = payload_by_external_id.get(str(job.external_job_id))
        if not payload:
            continue

        structured_locations = _build_structured_locations(payload)
        for i, structured in enumerate(structured_locations):
            is_primary = i == 0

            location = await sync_job_location(
                session=session,
                job_id=str(job.id),
                structured=structured,
                is_primary=is_primary,
                source_raw=payload.get("location_text"),
            )

            if is_primary:
                sync_primary_to_job(
                    job=job,
                    location=location,
                    workplace_type=structured.workplace_type,
                    remote_scope=structured.remote_scope,
                )
