from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.contracts.sync import SourceSyncResult, SourceSyncStats
from app.ingest.fetchers.base import BaseFetcher
from app.ingest.mappers.base import BaseMapper
from app.models import Job, JobStatus, Source, WorkplaceType, build_source_key
from app.repositories.job import JobRepository
from app.services.domain.job_location import (
    StructuredLocation,
    parse_location_text,
    sync_job_location,
)
from app.services.domain.geonames_resolver import get_geonames_resolver
from app.services.application.job_blob import JobBlobManager, JobBlobPointers


def _to_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _now_naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FullSnapshotSyncError(Exception):
    """Raised when one source snapshot cannot be fully reconciled."""


class FullSnapshotSyncService:
    """Same-source full snapshot reconcile service."""

    _LOCATION_COMPAT_FIELDS = {
        "location_text",
        "location_city",
        "location_region",
        "location_country_code",
        "location_workplace_type",
        "location_remote_scope",
    }

    def __init__(
        self,
        session: AsyncSession,
        job_repository: JobRepository | None = None,
        blob_manager: JobBlobManager | None = None,
    ):
        self.session = session
        self.job_repository = job_repository or JobRepository(session)
        self.blob_manager = blob_manager or JobBlobManager()

    async def sync_source(
        self,
        *,
        source: Source,
        fetcher: BaseFetcher,
        mapper: BaseMapper,
        include_content: bool = True,
        dry_run: bool = False,
    ) -> SourceSyncResult:
        source_key = build_source_key(source.platform, source.identifier)
        source_id = str(source.id)
        stats = SourceSyncStats()

        try:
            raw_jobs = await fetcher.fetch(source.identifier, include_content=include_content)
            stats.fetched_count = len(raw_jobs)

            mapped_payloads: list[dict[str, Any]] = []
            for raw_job in raw_jobs:
                mapped = mapper.map(raw_job)
                payload = mapped.model_dump()
                external_job_id = str(payload.get("external_job_id") or "").strip()
                if not external_job_id:
                    raise FullSnapshotSyncError("Mapped job is missing external_job_id")
                payload["external_job_id"] = external_job_id
                # Authoritative write: source_id only.
                payload["source_id"] = source_id
                mapped_payloads.append(payload)

            stats.mapped_count = len(mapped_payloads)
            unique_payloads = self._dedupe_by_external_job_id(mapped_payloads)
            stats.unique_count = len(unique_payloads)
            stats.deduped_by_external_id = stats.mapped_count - stats.unique_count

            sync_started_at = _now_naive_utc()
            existing_rows = await self.job_repository.list_by_source_id_and_external_ids(
                source_id=source_id,
                external_job_ids=[payload["external_job_id"] for payload in unique_payloads],
            )
            existing_map = {str(job.external_job_id): job for job in existing_rows}

            staged_jobs: list[Job] = []
            for payload in unique_payloads:
                existing = existing_map.get(str(payload["external_job_id"]))
                if existing is None:
                    job = self._build_new_job(payload, sync_started_at)
                    await self.blob_manager.sync_job_blobs(job)
                    staged_jobs.append(job)
                    stats.inserted_count += 1
                    continue

                existing_pointers = JobBlobPointers.from_job(existing)
                self._update_existing_job(existing, payload, sync_started_at)
                await self.blob_manager.sync_job_blobs(
                    existing,
                    existing_pointers=existing_pointers,
                )
                staged_jobs.append(existing)
                stats.updated_count += 1

            if staged_jobs:
                await self.job_repository.save_all_no_commit(staged_jobs)
                await self.job_repository.flush()

                # Phase 2: Persist normalized locations after jobs are flushed (IDs exist)
                for job in staged_jobs:
                    # Find the corresponding payload to get hints
                    payload = next(
                        (
                            p
                            for p in unique_payloads
                            if str(p["external_job_id"]) == str(job.external_job_id)
                        ),
                        None,
                    )
                    if not payload:
                        continue

                    structured_locations = self._build_structured_locations(payload)
                    for i, structured in enumerate(structured_locations):
                        is_primary = i == 0
                        await sync_job_location(
                            session=self.session,
                            job_id=str(job.id),
                            structured=structured,
                            is_primary=is_primary,
                            source_raw=payload.get("location_text"),
                        )

            if dry_run:
                await self.session.rollback()
                stats.closed_count = 0
            else:
                stats.closed_count = await self.job_repository.bulk_close_missing_for_source_id(
                    source_id=source_id,
                    seen_at_before=sync_started_at,
                    updated_at=_now_naive_utc(),
                )
                await self.session.commit()

            return SourceSyncResult(
                source_id=source_id,
                source_key=source_key,
                ok=True,
                stats=stats,
            )
        except Exception as exc:
            await self.session.rollback()
            stats.failed_count = max(
                stats.unique_count,
                stats.mapped_count,
                stats.fetched_count,
                1,
            )
            return SourceSyncResult(
                source_id=source_id,
                source_key=source_key,
                ok=False,
                stats=stats,
                error=str(exc),
            )

    @staticmethod
    def _dedupe_by_external_job_id(mapped_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for payload in mapped_payloads:
            deduped[str(payload["external_job_id"])] = payload
        return list(deduped.values())

    @staticmethod
    def _clean_optional_str(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        text = value.strip()
        return text or None

    @staticmethod
    def _coerce_workplace_type(value: object) -> WorkplaceType:
        if isinstance(value, WorkplaceType):
            return value
        if isinstance(value, str):
            try:
                return WorkplaceType(value)
            except ValueError:
                return WorkplaceType.unknown
        return WorkplaceType.unknown

    @staticmethod
    def _is_structured_location_usable(location: StructuredLocation) -> bool:
        return bool(location.city or location.region or location.country_code)

    @staticmethod
    def _build_structured_locations(payload: dict[str, Any]) -> list[StructuredLocation]:
        hints = payload.get("location_hints")
        structured_locations: list[StructuredLocation] = []

        if isinstance(hints, list):
            for hint in hints:
                if not isinstance(hint, dict):
                    continue
                structured = StructuredLocation(
                    city=FullSnapshotSyncService._clean_optional_str(hint.get("city")),
                    region=FullSnapshotSyncService._clean_optional_str(hint.get("region")),
                    country_code=FullSnapshotSyncService._clean_optional_str(hint.get("country_code")),
                    workplace_type=FullSnapshotSyncService._coerce_workplace_type(
                        hint.get("workplace_type")
                    ),
                    remote_scope=FullSnapshotSyncService._clean_optional_str(hint.get("remote_scope")),
                )
                if FullSnapshotSyncService._is_structured_location_usable(structured):
                    structured_locations.append(structured)

        if structured_locations:
            return structured_locations

        # Compatibility fallback for mappers that still emit job-level location fields.
        location_text = FullSnapshotSyncService._clean_optional_str(payload.get("location_text"))
        fallback = StructuredLocation(
            city=FullSnapshotSyncService._clean_optional_str(payload.get("location_city")),
            region=FullSnapshotSyncService._clean_optional_str(payload.get("location_region")),
            country_code=FullSnapshotSyncService._clean_optional_str(
                payload.get("location_country_code")
            ),
            workplace_type=FullSnapshotSyncService._coerce_workplace_type(
                payload.get("location_workplace_type")
            ),
            remote_scope=FullSnapshotSyncService._clean_optional_str(payload.get("location_remote_scope")),
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
            city_match = get_geonames_resolver().resolve_city(
                city=fallback.city,
                region=fallback.region,
            )
            if city_match:
                fallback.country_code = city_match.country_code
                fallback.region = fallback.region or city_match.admin1_code

        if FullSnapshotSyncService._is_structured_location_usable(fallback):
            return [fallback]

        return []

    @staticmethod
    def _build_new_job(payload: dict[str, Any], sync_started_at: datetime) -> Job:
        data = dict(payload)
        data["published_at"] = _to_naive_utc(data.get("published_at"))
        data["source_updated_at"] = _to_naive_utc(data.get("source_updated_at"))
        data["status"] = JobStatus.open
        data["ingested_at"] = sync_started_at
        data["last_seen_at"] = sync_started_at
        data["created_at"] = sync_started_at
        data["updated_at"] = sync_started_at
        data.pop("source", None)
        data.pop("location_hints", None)
        for field in FullSnapshotSyncService._LOCATION_COMPAT_FIELDS:
            data.pop(field, None)
        return Job(**data)

    @staticmethod
    def _update_existing_job(
        job: Job,
        payload: dict[str, Any],
        sync_started_at: datetime,
    ) -> None:
        normalized_payload = dict(payload)
        normalized_payload["published_at"] = _to_naive_utc(normalized_payload.get("published_at"))
        normalized_payload["source_updated_at"] = _to_naive_utc(
            normalized_payload.get("source_updated_at")
        )
        # Overwriting source_id on existing rows is intentional: it self-heals any row
        # that was written before the Phase 2 backfill ran (source_id was NULL or wrong).
        # that was written before the Phase 2 backfill ran (source_id was NULL or wrong).
        normalized_payload.pop("source", None)
        normalized_payload.pop("location_hints", None)
        for field in FullSnapshotSyncService._LOCATION_COMPAT_FIELDS:
            normalized_payload.pop(field, None)
        for key, value in normalized_payload.items():
            setattr(job, key, value)
        job.status = JobStatus.open
        job.last_seen_at = sync_started_at
        job.updated_at = sync_started_at
