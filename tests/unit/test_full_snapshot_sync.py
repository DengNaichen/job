import asyncio
from typing import Any

from copy import deepcopy

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.ingest.fetchers.base import BaseFetcher
from app.ingest.mappers.base import BaseMapper
from app.models import Job, JobLocation, JobStatus, Location, PlatformType, Source
from app.schemas.job import JobCreate
from app.services.application.full_snapshot_sync import FullSnapshotSyncService
from app.services.infra.blob_storage import JobBlobManager


class _FakeFetcher(BaseFetcher):
    def __init__(self, jobs: list[dict[str, Any]], *, error: Exception | None = None):
        self.jobs = deepcopy(jobs)
        self.error = error

    @property
    def source_name(self) -> str:
        return "greenhouse"

    async def fetch(self, slug: str, **kwargs: Any) -> list[dict[str, Any]]:  # noqa: ANN401
        _ = (slug, kwargs)
        if self.error is not None:
            raise self.error
        return deepcopy(self.jobs)


class _FakeMapper(BaseMapper):
    def __init__(self, *, error_job_id: str | None = None):
        self.error_job_id = error_job_id

    @property
    def source_name(self) -> str:
        return "greenhouse"

    def map(self, raw_job: dict[str, Any]) -> JobCreate:
        if self.error_job_id is not None and str(raw_job["id"]) == self.error_job_id:
            raise ValueError("mapper boom")
        return JobCreate(
            source="greenhouse",
            external_job_id=str(raw_job["id"]),
            title=str(raw_job["title"]),
            apply_url=str(raw_job["absolute_url"]),
            description_html=str(raw_job.get("content") or ""),
            raw_payload=raw_job,
            location_hints=raw_job.get("location_hints") or [],  # type: ignore
        )


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


class _SlowTrackingBlobStorage(_InMemoryBlobStorage):
    def __init__(self, delay_seconds: float = 0.01):
        super().__init__()
        self.delay_seconds = delay_seconds
        self.in_flight = 0
        self.max_in_flight = 0

    async def upload_if_missing(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        content_encoding: str = "gzip",
    ) -> bool:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay_seconds)
            return await super().upload_if_missing(
                key=key,
                data=data,
                content_type=content_type,
                content_encoding=content_encoding,
            )
        finally:
            self.in_flight -= 1


class _FailingBlobStorage(_InMemoryBlobStorage):
    def __init__(self, *, fail_after_calls: int = 3):
        super().__init__()
        self.fail_after_calls = fail_after_calls
        self.upload_calls = 0

    async def upload_if_missing(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        content_encoding: str = "gzip",
    ) -> bool:
        self.upload_calls += 1
        if self.upload_calls >= self.fail_after_calls:
            raise RuntimeError("blob boom")
        return await super().upload_if_missing(
            key=key,
            data=data,
            content_type=content_type,
            content_encoding=content_encoding,
        )


_SOURCE = Source(
    name="Airbnb",
    name_normalized="airbnb",
    platform=PlatformType.GREENHOUSE,
    identifier="airbnb",
)


def _source() -> Source:
    """Return the singleton test source (stable UUID across all calls within this module)."""
    return _SOURCE


def _jobs(ids: list[str]) -> list[dict[str, object]]:
    return [
        {
            "id": job_id,
            "title": f"Job {job_id}",
            "absolute_url": f"https://example.com/{job_id}",
            "content": f"Description {job_id}",
        }
        for job_id in ids
    ]


async def _all_jobs(session: AsyncSession) -> list[Job]:
    rows = await session.exec(select(Job).order_by(Job.external_job_id))
    return list(rows.all())


def _service(session: AsyncSession) -> FullSnapshotSyncService:
    return _service_with_storage(session, _InMemoryBlobStorage())


def _service_with_storage(session: AsyncSession, storage: Any) -> FullSnapshotSyncService:
    return FullSnapshotSyncService(
        session,
        blob_manager=JobBlobManager(storage),
    )


@pytest.mark.asyncio
async def test_full_snapshot_sync_first_import_inserts_all_rows(session: AsyncSession) -> None:
    service = _service(session)
    source = _source()
    result = await service.sync_source(
        source=source,
        fetcher=_FakeFetcher(_jobs(["A", "B", "C"])),
        mapper=_FakeMapper(),
    )

    rows = await _all_jobs(session)

    assert result.ok is True
    assert result.stats.fetched_count == 3
    assert result.stats.unique_count == 3
    assert result.stats.inserted_count == 3
    assert result.stats.updated_count == 0
    assert result.stats.closed_count == 0
    assert [row.external_job_id for row in rows] == ["A", "B", "C"]
    assert all(row.source == "greenhouse:airbnb" for row in rows)
    # Phase 3: source_id must be dual-written alongside legacy source string
    assert all(row.source_id == str(source.id) for row in rows)
    assert all(row.status == JobStatus.open for row in rows)
    assert all(row.description_html_key for row in rows)
    assert all(row.raw_payload_key for row in rows)


@pytest.mark.asyncio
async def test_full_snapshot_sync_second_full_import_updates_without_duplicates(
    session: AsyncSession,
) -> None:
    service = _service(session)
    first_jobs = _jobs(["A", "B", "C"])
    await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(first_jobs),
        mapper=_FakeMapper(),
    )

    result = await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(first_jobs),
        mapper=_FakeMapper(),
    )

    rows = await _all_jobs(session)

    assert result.ok is True
    assert result.stats.inserted_count == 0
    assert result.stats.updated_count == 3
    assert result.stats.closed_count == 0
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_full_snapshot_sync_closes_jobs_missing_from_next_snapshot(
    session: AsyncSession,
) -> None:
    service = _service(session)
    await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(_jobs(["A", "B", "C"])),
        mapper=_FakeMapper(),
    )

    result = await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(_jobs(["A", "B"])),
        mapper=_FakeMapper(),
    )

    rows = {row.external_job_id: row for row in await _all_jobs(session)}

    assert result.ok is True
    assert result.stats.closed_count == 1
    assert rows["A"].status == JobStatus.open
    assert rows["B"].status == JobStatus.open
    assert rows["C"].status == JobStatus.closed


@pytest.mark.asyncio
async def test_full_snapshot_sync_reopens_closed_job_when_it_reappears(
    session: AsyncSession,
) -> None:
    service = _service(session)
    await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(_jobs(["A", "B", "C"])),
        mapper=_FakeMapper(),
    )
    await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(_jobs(["A", "B"])),
        mapper=_FakeMapper(),
    )

    result = await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(_jobs(["A", "B", "C"])),
        mapper=_FakeMapper(),
    )

    rows = {row.external_job_id: row for row in await _all_jobs(session)}

    assert result.ok is True
    assert result.stats.inserted_count == 0
    assert result.stats.updated_count == 3
    assert rows["C"].status == JobStatus.open
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_full_snapshot_sync_dedupes_duplicate_external_job_ids_within_snapshot(
    session: AsyncSession,
) -> None:
    service = _service(session)
    raw_jobs = _jobs(["A", "B"])
    raw_jobs.insert(
        1,
        {
            "id": "A",
            "title": "Job A Updated",
            "absolute_url": "https://example.com/A-latest",
            "content": "Updated Description A",
        },
    )

    result = await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(raw_jobs),
        mapper=_FakeMapper(),
    )

    rows = {row.external_job_id: row for row in await _all_jobs(session)}

    assert result.ok is True
    assert result.stats.mapped_count == 3
    assert result.stats.unique_count == 2
    assert result.stats.deduped_by_external_id == 1
    assert rows["A"].title == "Job A Updated"
    assert rows["A"].apply_url == "https://example.com/A-latest"


@pytest.mark.asyncio
async def test_full_snapshot_sync_fetch_failure_rolls_back_without_closing_jobs(
    session: AsyncSession,
) -> None:
    service = _service(session)
    await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(_jobs(["A", "B", "C"])),
        mapper=_FakeMapper(),
    )

    result = await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher([], error=RuntimeError("fetch boom")),
        mapper=_FakeMapper(),
    )

    rows = {row.external_job_id: row for row in await _all_jobs(session)}

    assert result.ok is False
    assert result.error == "fetch boom"
    assert all(row.status == JobStatus.open for row in rows.values())


@pytest.mark.asyncio
async def test_full_snapshot_sync_mapper_failure_rolls_back_without_closing_jobs(
    session: AsyncSession,
) -> None:
    service = _service(session)
    await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(_jobs(["A", "B", "C"])),
        mapper=_FakeMapper(),
    )

    result = await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(_jobs(["A", "B"])),
        mapper=_FakeMapper(error_job_id="B"),
    )

    rows = {row.external_job_id: row for row in await _all_jobs(session)}

    assert result.ok is False
    assert result.error == "mapper boom"
    assert rows["C"].status == JobStatus.open


@pytest.mark.asyncio
async def test_full_snapshot_sync_dry_run_does_not_persist_or_close_jobs(
    session: AsyncSession,
) -> None:
    service = _service(session)
    result = await service.sync_source(
        source=_source(),
        fetcher=_FakeFetcher(_jobs(["A", "B", "C"])),
        mapper=_FakeMapper(),
        dry_run=True,
    )

    rows = await _all_jobs(session)

    assert result.ok is True
    assert result.stats.inserted_count == 3
    assert result.stats.closed_count == 0
    assert rows == []


@pytest.mark.asyncio
async def test_full_snapshot_sync_persists_canonical_locations(session: AsyncSession) -> None:
    service = _service(session)
    source = _source()
    jobs = [
        {
            "id": "job-1",
            "title": "Engineer in SF",
            "absolute_url": "https://example.com/1",
            "location_hints": [
                {
                    "city": "San Francisco",
                    "region": "CA",
                    "country_code": "US",
                    "workplace_type": "onsite",
                }
            ],
        },
        {
            "id": "job-2",
            "title": "Remote Engineer",
            "absolute_url": "https://example.com/2",
            "location_hints": [
                {"country_code": "CA", "workplace_type": "remote", "remote_scope": "Canada"}
            ],
        },
    ]

    result = await service.sync_source(
        source=source,
        fetcher=_FakeFetcher(jobs),
        mapper=_FakeMapper(),
    )

    assert result.ok is True

    # Verify Job models (compatibility fields)
    job_rows = {j.external_job_id: j for j in await _all_jobs(session)}
    assert job_rows["job-1"].location_city == "San Francisco"
    assert job_rows["job-1"].location_country_code == "US"
    assert job_rows["job-2"].location_country_code == "CA"
    assert job_rows["job-2"].location_workplace_type == "remote"

    # Verify Location models
    loc_rows = (await session.exec(select(Location))).all()
    assert len(loc_rows) == 2
    loc_keys = {loc.canonical_key for loc in loc_rows}
    assert "us-ca-san-francisco" in loc_keys
    assert "ca" in loc_keys

    # Verify JobLocation links
    link_rows = (await session.exec(select(JobLocation))).all()
    assert len(link_rows) == 2
    assert all(link.is_primary is True for link in link_rows)


@pytest.mark.asyncio
async def test_full_snapshot_sync_blob_stage_bounded_to_16(session: AsyncSession) -> None:
    storage = _SlowTrackingBlobStorage(delay_seconds=0.01)
    service = _service_with_storage(session, storage)
    source = _source()

    result = await service.sync_source(
        source=source,
        fetcher=_FakeFetcher(_jobs([f"job-{i}" for i in range(40)])),
        mapper=_FakeMapper(),
    )

    assert result.ok is True
    assert storage.max_in_flight <= 16
    assert storage.max_in_flight > 1


@pytest.mark.asyncio
async def test_full_snapshot_sync_blob_failure_rolls_back_under_parallelism(
    session: AsyncSession,
) -> None:
    storage = _FailingBlobStorage(fail_after_calls=3)
    service = _service_with_storage(session, storage)
    source = _source()

    result = await service.sync_source(
        source=source,
        fetcher=_FakeFetcher(_jobs([f"job-{i}" for i in range(20)])),
        mapper=_FakeMapper(),
    )

    rows = await _all_jobs(session)

    assert result.ok is False
    assert result.error is not None
    assert "blob boom" in result.error
    assert rows == []
