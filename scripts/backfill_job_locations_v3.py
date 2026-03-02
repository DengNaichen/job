import logging
import asyncio

from sqlmodel.ext.asyncio.session import AsyncSession

from app.ingest.mappers import (
    AppleMapper,
    AshbyMapper,
    EightfoldMapper,
    GreenhouseMapper,
    LeverMapper,
    SmartRecruitersMapper,
    TikTokMapper,
)
from app.models.job import Job, WorkplaceType
from app.repositories.job import JobRepository
from app.repositories.job_location import JobLocationRepository
from app.services.domain.job_location import (
    parse_location_text,
    sync_job_location,
    sync_primary_to_job,
    StructuredLocation,
)

logger = logging.getLogger(__name__)


async def apply_backfill_to_job_v3(session: AsyncSession, job: Job) -> bool:
    """
    Apply v3 canonical location backfill to a job in-place.
    Populates locations and job_locations, then syncs back to flat fields.
    Returns True if fields or links were actually modified.
    """
    structured_locations: list[StructuredLocation] = []

    # Check if this source is high confidence
    MAPPERS = {
        "apple": AppleMapper(),
        "ashby": AshbyMapper(),
        "eightfold": EightfoldMapper(),
        "greenhouse": GreenhouseMapper(),
        "lever": LeverMapper(),
        "smartrecruiters": SmartRecruitersMapper(),
        "tiktok": TikTokMapper(),
    }

    # 1. Try to extract using the mapper (High Confidence)
    mapper = MAPPERS.get(job.source) if job.source else None
    if mapper and job.raw_payload:
        try:
            mapped = mapper.map(job.raw_payload)
            if mapped.location_hints:
                for hint in mapped.location_hints:
                    loc = StructuredLocation(
                        city=hint.get("city"),
                        region=hint.get("region"),
                        country_code=hint.get("country_code"),
                        workplace_type=hint.get("workplace_type", WorkplaceType.unknown),
                    )
                    structured_locations.append(loc)
        except Exception as e:
            logger.warning(f"Mapper failed for job {job.id}: {e}")

    # 2. Fallback to heuristic interpretation
    if not structured_locations:
        has_existing_city_region = bool(job.location_city or job.location_region)
        from app.services.domain.country_normalization import is_canonical_country_code

        current_canonical_country = is_canonical_country_code(job.location_country_code)

        # If we already have strong data, we should just canonicalize what we have
        # instead of overwriting it via an imperfect text parse
        if has_existing_city_region or current_canonical_country:
            loc = StructuredLocation(
                city=job.location_city,
                region=job.location_region,
                country_code=job.location_country_code,
                workplace_type=job.location_workplace_type,
                remote_scope=job.location_remote_scope,
            )
            # still attempt to patch country if it's missing or non-canonical but we have text
            if not current_canonical_country and job.location_text:
                parsed = parse_location_text(job.location_text)
                if parsed.country_code:
                    loc.country_code = parsed.country_code
                if loc.workplace_type == WorkplaceType.unknown:
                    loc.workplace_type = parsed.workplace_type
            structured_locations.append(loc)
        elif job.location_text:
            parsed = parse_location_text(job.location_text)
            structured_locations.append(parsed)
        elif job.location_remote_scope:
            parsed = parse_location_text(f"Remote - {job.location_remote_scope}")
            structured_locations.append(parsed)

    changed = False

    if not structured_locations:
        return changed

    job_loc_repo = JobLocationRepository(session)
    existing_links = await job_loc_repo.list_by_job_id(job.id) if job.id else []

    # Helper to check if a location matches an existing link
    # For idempotency, we just count created links or field changes
    seen_keys = set()

    for i, structured in enumerate(structured_locations):
        is_primary = i == 0

        # This will create/update the Location and JobLocation link
        location_entity = await sync_job_location(
            session=session,
            job_id=job.id,
            structured=structured,
            is_primary=is_primary,
            source_raw="backfill",
        )
        seen_keys.add(location_entity.canonical_key)

        # Compare if the link already exactly existed
        link_existed = False
        for link in existing_links:
            if link.location_id == location_entity.id and link.is_primary == is_primary:
                link_existed = True
                break

        if not link_existed:
            changed = True

        if is_primary:
            old_city = job.location_city
            old_region = job.location_region
            old_country = job.location_country_code
            old_workplace = job.location_workplace_type

            sync_primary_to_job(
                job=job,
                location=location_entity,
                workplace_type=structured.workplace_type,
                remote_scope=structured.remote_scope,
            )

            if (
                job.location_city != old_city
                or job.location_region != old_region
                or job.location_country_code != old_country
                or job.location_workplace_type != old_workplace
            ):
                changed = True

    return changed


async def run_backfill_v3(session: AsyncSession, batch_size: int = 100) -> int:
    """
    Iterate over all missing canonical location jobs and apply location backfill.
    Returns the number of jobs updated.
    """
    repo = JobRepository(session)
    last_id = None
    total_updated = 0

    while True:
        jobs = await repo.list_jobs_missing_canonical_locations(last_id=last_id, limit=batch_size)
        if not jobs:
            break

        to_update = []
        for job in jobs:
            if await apply_backfill_to_job_v3(session, job):
                to_update.append(job)
            last_id = job.id

        if to_update:
            await repo.save_all(to_update)
            total_updated += len(to_update)
            logger.info(f"Updated {len(to_update)} jobs in this batch.")

    return total_updated


if __name__ == "__main__":
    from app.core.database import get_session

    async def main():
        logging.basicConfig(level=logging.INFO)
        async for session in get_session():
            updated = await run_backfill_v3(session)
            print(f"Backfill complete! Updated {updated} jobs.")
            break

    asyncio.run(main())
