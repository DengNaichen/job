from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job, JobStatus
from app.repositories.job import JobRepository


def _make_job(
    *,
    source: str,
    external_job_id: str,
    status: JobStatus = JobStatus.open,
    last_seen_at: datetime | None = None,
) -> Job:
    ts = last_seen_at or datetime.now(timezone.utc)
    return Job(
        source=source,
        external_job_id=external_job_id,
        title=f"Job {external_job_id}",
        apply_url=f"https://example.com/{external_job_id}",
        status=status,
        last_seen_at=ts,
        ingested_at=ts,
        created_at=ts,
        updated_at=ts,
    )


@pytest.mark.asyncio
async def test_list_by_source_and_external_ids_filters_to_same_source(session: AsyncSession) -> None:
    target = _make_job(source="greenhouse:airbnb", external_job_id="123")
    other_source = _make_job(source="greenhouse:stripe", external_job_id="123")
    other_id = _make_job(source="greenhouse:airbnb", external_job_id="456")
    session.add(target)
    session.add(other_source)
    session.add(other_id)
    await session.commit()

    repository = JobRepository(session)
    rows = await repository.list_by_source_and_external_ids(
        source="greenhouse:airbnb",
        external_job_ids=["123", "999"],
    )

    assert [row.external_job_id for row in rows] == ["123"]
    assert rows[0].source == "greenhouse:airbnb"


@pytest.mark.asyncio
async def test_bulk_close_missing_for_source_only_closes_stale_open_rows(session: AsyncSession) -> None:
    cutoff = datetime.now(timezone.utc)
    stale_open = _make_job(
        source="greenhouse:airbnb",
        external_job_id="stale-open",
        last_seen_at=cutoff - timedelta(hours=1),
    )
    fresh_open = _make_job(
        source="greenhouse:airbnb",
        external_job_id="fresh-open",
        last_seen_at=cutoff + timedelta(minutes=5),
    )
    stale_closed = _make_job(
        source="greenhouse:airbnb",
        external_job_id="stale-closed",
        status=JobStatus.closed,
        last_seen_at=cutoff - timedelta(hours=1),
    )
    other_source = _make_job(
        source="greenhouse:stripe",
        external_job_id="other-source",
        last_seen_at=cutoff - timedelta(hours=1),
    )
    session.add(stale_open)
    session.add(fresh_open)
    session.add(stale_closed)
    session.add(other_source)
    await session.commit()

    repository = JobRepository(session)
    closed_count = await repository.bulk_close_missing_for_source(
        source="greenhouse:airbnb",
        seen_at_before=cutoff,
        updated_at=cutoff,
    )
    await session.commit()

    rows = {
        row.external_job_id: row
        for row in (await session.exec(select(Job).order_by(Job.external_job_id))).all()
    }

    assert closed_count == 1
    assert rows["stale-open"].status == JobStatus.closed
    assert rows["fresh-open"].status == JobStatus.open
    assert rows["stale-closed"].status == JobStatus.closed
    assert rows["other-source"].status == JobStatus.open
