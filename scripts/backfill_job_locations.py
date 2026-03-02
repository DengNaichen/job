import logging

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
    BaseMapper,
)
from app.models.job import Job, WorkplaceType
from app.repositories.job import JobRepository
from app.services.domain.country_normalization import (
    is_canonical_country_code,
    normalize_country,
)
from app.services.domain.job_location import parse_location_text

logger = logging.getLogger(__name__)

MAPPERS: dict[str, BaseMapper] = {
    "apple": AppleMapper(),
    "ashby": AshbyMapper(),
    "eightfold": EightfoldMapper(),
    "greenhouse": GreenhouseMapper(),
    "lever": LeverMapper(),
    "smartrecruiters": SmartRecruitersMapper(),
    "tiktok": TikTokMapper(),
    "uber": UberMapper(),
}

# Sources that provide explicit structured location fields in their raw payload
HIGH_CONFIDENCE_SOURCES = {"smartrecruiters", "apple", "uber", "tiktok", "eightfold"}


def apply_backfill_to_job(job: Job) -> bool:
    """
    Apply structured location backfill to a job in-place.
    Returns True if fields were actually modified.
    """

    new_city = None
    new_region = None
    new_country = None
    new_workplace = WorkplaceType.unknown

    is_high_confidence = job.source in HIGH_CONFIDENCE_SOURCES

    # 1. Try to extract using the mapper from raw_payload (Explicit Field -> High Confidence)
    mapper = MAPPERS.get(job.source) if job.source else None
    mapped = None
    if mapper and job.raw_payload:
        try:
            mapped = mapper.map(job.raw_payload)
            new_city = mapped.location_city
            new_region = mapped.location_region
            new_country = mapped.location_country_code
            new_workplace = mapped.location_workplace_type
        except Exception as e:
            logger.warning(f"Mapper failed for job {job.id}: {e}")

    # 2. Fallback for COUNTRY specifically: try remote_scope or text (Heuristic -> Lower Confidence)
    # T014: repair from raw_payload first and location_text or location_remote_scope second
    heuristic_country = None
    if not (new_country and is_high_confidence):
        # Try remote_scope first if it exists
        if job.location_remote_scope:
            res = normalize_country(job.location_remote_scope, is_explicit_field=False)
            if res.country_code:
                heuristic_country = res.country_code

        # Then try location_text
        if not heuristic_country and job.location_text:
            parsed = parse_location_text(job.location_text)
            heuristic_country = parsed.country_code

            # Also sync city/region/workplace if they are still missing
            if not (new_city or new_region or new_country):
                new_city = parsed.city
                new_region = parsed.region
                if new_workplace == WorkplaceType.unknown:
                    new_workplace = parsed.workplace_type

    # 3. Apply updates with confidence protection
    changed = False

    # Country update rules
    target_country = new_country or heuristic_country
    if target_country:
        current_canonical = is_canonical_country_code(job.location_country_code)
        # Overwrite if:
        # - Current is not canonical (null or raw string)
        # - OR current is canonical but our new value is high-confidence from mapper
        if not current_canonical or (target_country == new_country and is_high_confidence):
            if job.location_country_code != target_country:
                job.location_country_code = target_country
                changed = True

    # City/Region/Workplace update rules (staying with basic "empty or high confidence" for now)
    has_existing_city_region = bool(job.location_city or job.location_region)
    if not has_existing_city_region or is_high_confidence:
        if new_city and new_city != job.location_city:
            job.location_city = new_city
            changed = True
        if new_region and new_region != job.location_region:
            job.location_region = new_region
            changed = True

    if (
        job.location_workplace_type == WorkplaceType.unknown
        and new_workplace != WorkplaceType.unknown
    ):
        job.location_workplace_type = new_workplace
        changed = True

    return changed


async def run_backfill(session: AsyncSession, batch_size: int = 100) -> int:
    """
    Iterate over all jobs and apply location backfill.
    Returns the number of jobs updated.
    """
    repo = JobRepository(session)
    last_id = None
    total_updated = 0

    while True:
        jobs = await repo.list_jobs_for_country_backfill(last_id=last_id, limit=batch_size)
        if not jobs:
            break

        to_update = []
        for job in jobs:
            if apply_backfill_to_job(job):
                to_update.append(job)
            last_id = job.id

        if to_update:
            await repo.save_all(to_update)
            total_updated += len(to_update)
            logger.info(f"Updated {len(to_update)} jobs in this batch.")

    return total_updated


if __name__ == "__main__":
    import asyncio
    from app.core.database import get_session

    async def main():
        logging.basicConfig(level=logging.INFO)
        async for session in get_session():
            updated = await run_backfill(session)
            print(f"Backfill complete! Updated {updated} jobs.")
            break

    asyncio.run(main())
