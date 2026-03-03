from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job, Location, PlatformType, Source
from app.services.application.blob.job_blob import JobBlobManager
from app.repositories.job_location import JobLocationRepository
from app.services.domain.job_location import StructuredLocation, sync_job_location
from scripts.backfill_unknown_primary_locations_v4 import (
    apply_unknown_primary_cleanup_to_job_v4,
    run_backfill_v4,
)


@dataclass
class _FakeCityMatch:
    geonames_id: int
    name: str
    country_code: str
    admin1_code: str | None
    population: int


class _InMemoryBlobStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    @property
    def is_enabled(self) -> bool:
        return True

    async def upload_if_missing(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        content_encoding: str = "gzip",
    ) -> bool:
        _ = (content_type, content_encoding)
        already_exists = key in self.objects
        self.objects.setdefault(key, data)
        return not already_exists

    async def download(self, *, key: str) -> bytes:
        return self.objects[key]


async def _create_job_with_unknown_primary(
    session: AsyncSession,
    *,
    source: str,
    external_job_id: str,
    location_text: str | None,
    source_raw: str = "backfill",
    raw_payload: dict | None = None,
    blob_manager: JobBlobManager | None = None,
) -> str:
    platform, identifier = source.split(":", 1)
    source_platform = PlatformType(platform)
    source_row = (
        await session.exec(
            select(Source).where(
                Source.platform == source_platform,
                Source.identifier == identifier,
            )
        )
    ).first()
    if source_row is None:
        source_row = Source(
            name=f"{platform}-{identifier}",
            name_normalized=f"{platform}-{identifier}",
            platform=source_platform,
            identifier=identifier,
        )
        session.add(source_row)
        await session.flush()

    job = Job(
        source_id=str(source_row.id),
        external_job_id=external_job_id,
        title=f"Title {external_job_id}",
        apply_url=f"https://example.com/{external_job_id}",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    if raw_payload is not None and blob_manager is not None:
        await blob_manager.sync_job_blobs(
            job,
            explicit_fields={"raw_payload"},
            raw_payload=raw_payload,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)

    # Seed historical unknown primary link.
    await sync_job_location(
        session=session,
        job_id=job.id,
        structured=StructuredLocation(),
        is_primary=True,
        source_raw=source_raw,
    )
    await session.commit()
    await session.refresh(job)
    return str(job.id)


@pytest.mark.asyncio
async def test_apply_unknown_primary_cleanup_from_location_text(session: AsyncSession) -> None:
    job_id = await _create_job_with_unknown_primary(
        session,
        source="greenhouse:airbnb",
        external_job_id="gh-unknown-1",
        location_text="Toronto, ON, Canada",
        source_raw="Toronto, ON, Canada",
    )
    job = await session.get(Job, job_id)
    assert job is not None

    changed, origin = await apply_unknown_primary_cleanup_to_job_v4(session, job)
    assert changed is True
    assert origin == "legacy_or_text"

    links = await JobLocationRepository(session).list_by_job_id(job.id)
    primary = next(link for link in links if link.is_primary)
    primary_location = await session.get(Location, primary.location_id)
    assert primary_location is not None
    assert primary_location.canonical_key == "ca-on-toronto"

    # Second run should be idempotent (primary already not unknown).
    changed_again, origin_again = await apply_unknown_primary_cleanup_to_job_v4(session, job)
    assert changed_again is False
    assert origin_again is None


@pytest.mark.asyncio
async def test_apply_unknown_primary_cleanup_skips_when_no_promotable_candidate(
    session: AsyncSession,
) -> None:
    job_id = await _create_job_with_unknown_primary(
        session,
        source="greenhouse:airbnb",
        external_job_id="gh-unknown-2",
        location_text="Remote",
        source_raw="Remote",
    )
    job = await session.get(Job, job_id)
    assert job is not None

    changed, origin = await apply_unknown_primary_cleanup_to_job_v4(session, job)
    assert changed is False
    assert origin is None

    links = await JobLocationRepository(session).list_by_job_id(job.id)
    primary = next(link for link in links if link.is_primary)
    primary_location = await session.get(Location, primary.location_id)
    assert primary_location is not None
    assert primary_location.canonical_key == "unknown"


@pytest.mark.asyncio
async def test_apply_unknown_primary_cleanup_from_geonames_city_only(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeResolver:
        def resolve_city(self, *, city: str | None, region: str | None = None, country_code=None):
            _ = (region, country_code)
            if city and city.lower() == "san francisco":
                return _FakeCityMatch(
                    geonames_id=1,
                    name="San Francisco",
                    country_code="US",
                    admin1_code="CA",
                    population=100,
                )
            return None

    monkeypatch.setattr(
        "scripts.backfill_unknown_primary_locations_v4.get_geonames_resolver",
        lambda: _FakeResolver(),
    )

    job_id = await _create_job_with_unknown_primary(
        session,
        source="greenhouse:airbnb",
        external_job_id="gh-unknown-city-only",
        location_text="San Francisco",
        source_raw="San Francisco",
    )
    job = await session.get(Job, job_id)
    assert job is not None

    changed, origin = await apply_unknown_primary_cleanup_to_job_v4(session, job)
    assert changed is True
    assert origin == "geonames_city_only"

    links = await JobLocationRepository(session).list_by_job_id(job.id)
    primary = next(link for link in links if link.is_primary)
    primary_location = await session.get(Location, primary.location_id)
    assert primary_location is not None
    assert primary_location.canonical_key == "us-ca-san-francisco"


@pytest.mark.asyncio
async def test_run_backfill_v4_only_targets_backfill_unknown_links(session: AsyncSession) -> None:
    storage = _InMemoryBlobStorage()
    blob_manager = JobBlobManager(storage)
    target_job_id = await _create_job_with_unknown_primary(
        session,
        source="greenhouse:airbnb",
        external_job_id="gh-unknown-3",
        location_text="Mexico City, Mexico",
        source_raw="backfill",
        raw_payload={
            "id": "gh-unknown-3",
            "title": "Engineer",
            "absolute_url": "https://example.com/gh-unknown-3",
            "location": {"name": "Mexico City, Mexico"},
        },
        blob_manager=blob_manager,
    )
    control_job_id = await _create_job_with_unknown_primary(
        session,
        source="greenhouse:airbnb",
        external_job_id="gh-unknown-4",
        location_text="Mexico City, Mexico",
        source_raw="manual",
        raw_payload={
            "id": "gh-unknown-4",
            "title": "Engineer",
            "absolute_url": "https://example.com/gh-unknown-4",
            "location": {"name": "Mexico City, Mexico"},
        },
        blob_manager=blob_manager,
    )

    stats = await run_backfill_v4(session, batch_size=50, blob_manager=blob_manager)
    assert stats.processed == 1
    assert stats.updated == 1
    assert stats.updated_from_mapper == 1

    target_links = await JobLocationRepository(session).list_by_job_id(target_job_id)
    target_primary = next(link for link in target_links if link.is_primary)
    target_location = await session.get(Location, target_primary.location_id)
    assert target_location is not None
    assert target_location.canonical_key in {"mx-mexico-city", "mx-09-mexico-city"}

    control_links = await JobLocationRepository(session).list_by_job_id(control_job_id)
    control_primary = next(link for link in control_links if link.is_primary)
    control_location = await session.get(Location, control_primary.location_id)
    assert control_location is not None
    assert control_location.canonical_key == "unknown"
