import argparse
import asyncio
import logging
from dataclasses import dataclass

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ingest.mappers import (
    AppleMapper,
    AshbyMapper,
    EightfoldMapper,
    GreenhouseMapper,
    LeverMapper,
    SmartRecruitersMapper,
    TikTokMapper,
    UberMapper,
)
from app.models import Job, JobLocation, Location, PlatformType, Source, WorkplaceType
from app.repositories.job import JobRepository
from app.repositories.job_location import JobLocationRepository
from app.services.application.blob.job_blob import JobBlobManager
from app.services.infra.blob_storage import BlobNotFoundError, BlobStorageNotConfiguredError
from app.services.domain.canonical_location import build_canonical_key
from app.services.domain.geonames_resolver import get_geonames_resolver
from app.services.domain.job_location import (
    StructuredLocation,
    parse_location_text,
    sync_job_location,
    sync_primary_to_job,
)

logger = logging.getLogger(__name__)

MAPPERS = {
    "apple": AppleMapper(),
    "ashby": AshbyMapper(),
    "eightfold": EightfoldMapper(),
    "greenhouse": GreenhouseMapper(),
    "lever": LeverMapper(),
    "smartrecruiters": SmartRecruitersMapper(),
    "tiktok": TikTokMapper(),
    "uber": UberMapper(),
}


@dataclass
class BackfillV4Stats:
    processed: int = 0
    updated: int = 0
    skipped_no_candidate: int = 0
    updated_from_legacy_or_text: int = 0
    updated_from_geonames_city_only: int = 0
    updated_from_mapper: int = 0


def _clean_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _job_attr(job: Job, field: str, default: object = None) -> object:
    return getattr(job, field, default)


def _effective_location_text(job: Job, primary_source_raw: str | None = None) -> str | None:
    location_text = _clean_optional_str(_job_attr(job, "location_text"))
    if location_text:
        return location_text
    source_raw = _clean_optional_str(primary_source_raw)
    if source_raw and source_raw not in {"backfill", "backfill-v4"}:
        return source_raw
    return None


def _coerce_workplace_type(value: object) -> WorkplaceType:
    if isinstance(value, WorkplaceType):
        return value
    if isinstance(value, str):
        try:
            return WorkplaceType(value)
        except ValueError:
            return WorkplaceType.unknown
    return WorkplaceType.unknown


_SOURCE_PLATFORM_CACHE: dict[str, str | None] = {}


async def _source_platform(session: AsyncSession, *, source_id: str | None) -> str | None:
    if not source_id:
        return None
    if source_id in _SOURCE_PLATFORM_CACHE:
        return _SOURCE_PLATFORM_CACHE[source_id]
    source = await session.get(Source, source_id)
    if source is None:
        platform = None
    elif isinstance(source.platform, PlatformType):
        platform = source.platform.value
    else:
        platform = str(source.platform).strip().lower() or None
    _SOURCE_PLATFORM_CACHE[source_id] = platform
    return platform


def _is_promotable_location(loc: StructuredLocation) -> bool:
    """Second-round cleanup only promotes locations with a country code."""
    if not _clean_optional_str(loc.country_code):
        return False
    key = build_canonical_key(
        city=_clean_optional_str(loc.city),
        region=_clean_optional_str(loc.region),
        country_code=_clean_optional_str(loc.country_code),
    )
    return key != "unknown"


def _candidate_from_legacy_or_text(job: Job, *, location_text_hint: str | None) -> StructuredLocation | None:
    loc = StructuredLocation(
        city=_clean_optional_str(_job_attr(job, "location_city")),
        region=_clean_optional_str(_job_attr(job, "location_region")),
        country_code=_clean_optional_str(_job_attr(job, "location_country_code")),
        workplace_type=_coerce_workplace_type(_job_attr(job, "location_workplace_type")),
        remote_scope=_clean_optional_str(_job_attr(job, "location_remote_scope")),
    )

    location_text = _clean_optional_str(location_text_hint)
    if location_text:
        parsed = parse_location_text(location_text)
        loc.city = loc.city or _clean_optional_str(parsed.city)
        loc.region = loc.region or _clean_optional_str(parsed.region)
        loc.country_code = loc.country_code or _clean_optional_str(parsed.country_code)
        if loc.workplace_type == WorkplaceType.unknown:
            loc.workplace_type = parsed.workplace_type
        loc.remote_scope = loc.remote_scope or _clean_optional_str(parsed.remote_scope)

    if _is_promotable_location(loc):
        return loc
    return None


async def _candidate_from_mapper(
    session: AsyncSession,
    job: Job,
    *,
    blob_manager: JobBlobManager,
) -> StructuredLocation | None:
    try:
        raw_payload = await blob_manager.load_raw_payload(job)
    except (BlobNotFoundError, BlobStorageNotConfiguredError):
        return None

    if not isinstance(raw_payload, dict) or not raw_payload:
        return None

    mapper = MAPPERS.get(await _source_platform(session, source_id=str(job.source_id or "")))
    if mapper is None:
        return None

    try:
        mapped = mapper.map(raw_payload)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mapper parse failed for job %s: %s", job.id, exc)
        return None

    for hint in mapped.location_hints:
        if not isinstance(hint, dict):
            continue
        loc = StructuredLocation(
            city=_clean_optional_str(hint.get("city")),
            region=_clean_optional_str(hint.get("region")),
            country_code=_clean_optional_str(hint.get("country_code")),
            workplace_type=_coerce_workplace_type(hint.get("workplace_type")),
            remote_scope=_clean_optional_str(hint.get("remote_scope")),
        )
        if _is_promotable_location(loc):
            return loc

    mapped_payload = mapped.model_dump()
    fallback = StructuredLocation(
        city=_clean_optional_str(mapped_payload.get("location_city")),
        region=_clean_optional_str(mapped_payload.get("location_region")),
        country_code=_clean_optional_str(mapped_payload.get("location_country_code")),
        workplace_type=_coerce_workplace_type(mapped_payload.get("location_workplace_type")),
        remote_scope=_clean_optional_str(mapped_payload.get("location_remote_scope")),
    )
    if _is_promotable_location(fallback):
        return fallback
    return None


def _candidate_from_geonames_city_only(
    job: Job, *, location_text_hint: str | None
) -> StructuredLocation | None:
    location_text = _clean_optional_str(location_text_hint)
    if not location_text or "," in location_text:
        return None

    parsed = parse_location_text(location_text)
    if _clean_optional_str(parsed.country_code):
        return None

    city_match = get_geonames_resolver().resolve_city(city=location_text)
    if city_match is None:
        return None

    loc = StructuredLocation(
        city=location_text,
        region=city_match.admin1_code,
        country_code=city_match.country_code,
        workplace_type=_coerce_workplace_type(_job_attr(job, "location_workplace_type")),
        remote_scope=_clean_optional_str(_job_attr(job, "location_remote_scope")),
    )
    if loc.workplace_type == WorkplaceType.unknown:
        loc.workplace_type = parsed.workplace_type
    loc.remote_scope = loc.remote_scope or _clean_optional_str(parsed.remote_scope)

    if _is_promotable_location(loc):
        return loc
    return None


async def apply_unknown_primary_cleanup_to_job_v4(
    session: AsyncSession,
    job: Job,
    *,
    blob_manager: JobBlobManager | None = None,
) -> tuple[bool, str | None]:
    """
    Clean one job whose primary location is currently `unknown`.
    Returns (changed, origin) where origin is one of:
    "legacy_or_text", "geonames_city_only", "mapper".
    """
    job_loc_repo = JobLocationRepository(session)
    existing_links = await job_loc_repo.list_by_job_id(job.id)
    existing_primary = next((link for link in existing_links if link.is_primary), None)
    if existing_primary is None:
        return False, None
    blob_manager = blob_manager or JobBlobManager()

    location_text_hint = _effective_location_text(job, existing_primary.source_raw)

    candidate = _candidate_from_legacy_or_text(job, location_text_hint=location_text_hint)
    origin = "legacy_or_text"
    if candidate is None:
        candidate = _candidate_from_geonames_city_only(job, location_text_hint=location_text_hint)
        origin = "geonames_city_only"
    if candidate is None:
        candidate = await _candidate_from_mapper(session, job, blob_manager=blob_manager)
        origin = "mapper"
    if candidate is None:
        return False, None

    old_primary_location_id = existing_primary.location_id
    location_entity = await sync_job_location(
        session=session,
        job_id=job.id,
        structured=candidate,
        is_primary=True,
        source_raw=location_text_hint or _clean_optional_str(existing_primary.source_raw) or "backfill-v4",
    )
    sync_primary_to_job(
        job=job,
        location=location_entity,
        workplace_type=candidate.workplace_type,
        remote_scope=candidate.remote_scope,
    )

    changed = old_primary_location_id != location_entity.id
    return changed, origin if changed else None


async def _list_jobs_with_unknown_primary_backfill(
    session: AsyncSession,
    *,
    last_id: str | None,
    limit: int,
) -> list[Job]:
    statement = (
        select(Job)
        .join(JobLocation, Job.id == JobLocation.job_id)
        .join(Location, Location.id == JobLocation.location_id)
        .where(
            JobLocation.is_primary.is_(True),
            JobLocation.source_raw == "backfill",
            Location.canonical_key == "unknown",
        )
    )
    if last_id:
        statement = statement.where(Job.id > last_id)
    statement = statement.order_by(Job.id).limit(limit)
    result = await session.exec(statement)
    return list(result.all())


async def run_backfill_v4(
    session: AsyncSession,
    *,
    batch_size: int = 500,
    max_jobs: int | None = None,
    dry_run: bool = False,
    blob_manager: JobBlobManager | None = None,
) -> BackfillV4Stats:
    repo = JobRepository(session)
    blob_manager = blob_manager or JobBlobManager()
    stats = BackfillV4Stats()
    last_id: str | None = None

    while True:
        jobs = await _list_jobs_with_unknown_primary_backfill(
            session,
            last_id=last_id,
            limit=batch_size,
        )
        if not jobs:
            break

        to_update: list[Job] = []
        for job in jobs:
            changed, origin = await apply_unknown_primary_cleanup_to_job_v4(
                session,
                job,
                blob_manager=blob_manager,
            )
            stats.processed += 1
            if changed:
                to_update.append(job)
                stats.updated += 1
                if origin == "legacy_or_text":
                    stats.updated_from_legacy_or_text += 1
                elif origin == "geonames_city_only":
                    stats.updated_from_geonames_city_only += 1
                elif origin == "mapper":
                    stats.updated_from_mapper += 1
            else:
                stats.skipped_no_candidate += 1
            last_id = job.id

            if max_jobs is not None and stats.processed >= max_jobs:
                break

        if to_update:
            if dry_run:
                await repo.save_all_no_commit(to_update)
                await repo.flush()
                await session.rollback()
            else:
                await repo.save_all(to_update)

        if max_jobs is not None and stats.processed >= max_jobs:
            break

    return stats


if __name__ == "__main__":
    from app.core.database import get_session

    parser = argparse.ArgumentParser(description="Second-round cleanup for unknown primary locations.")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max-jobs", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    async def main() -> None:
        logging.basicConfig(level=logging.INFO)
        async for session in get_session():
            stats = await run_backfill_v4(
                session,
                batch_size=args.batch_size,
                max_jobs=args.max_jobs,
                dry_run=args.dry_run,
            )
            print(
                "V4 cleanup done:",
                {
                    "processed": stats.processed,
                    "updated": stats.updated,
                    "skipped_no_candidate": stats.skipped_no_candidate,
                    "updated_from_legacy_or_text": stats.updated_from_legacy_or_text,
                    "updated_from_geonames_city_only": stats.updated_from_geonames_city_only,
                    "updated_from_mapper": stats.updated_from_mapper,
                    "dry_run": args.dry_run,
                },
            )
            break

    asyncio.run(main())
