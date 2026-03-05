from __future__ import annotations

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job, JobEmbedding
from app.repositories.job_embedding import JobEmbeddingRepository


EMBEDDING_DIM = 768
ACTIVE_TARGET_MODEL = "gemini/gemini-embedding-001"
OTHER_TARGET_MODEL = "openai/text-embedding-3-large"


def _vec(value: float) -> list[float]:
    return [value] * EMBEDDING_DIM


def _build_job(
    *,
    job_id: str,
    content_fingerprint: str | None = None,
) -> Job:
    return Job(
        id=job_id,
        source="greenhouse:acme",
        external_job_id=f"ext-{job_id}",
        title="Engineer",
        apply_url=f"https://example.com/{job_id}",
        description_plain="Build systems",
        content_fingerprint=content_fingerprint,
    )


@pytest.mark.asyncio
async def test_upsert_for_target_creates_and_refreshes_one_active_row(
    session: AsyncSession,
) -> None:
    job = _build_job(job_id="job-1", content_fingerprint="fp-1")
    job_id = job.id
    session.add(job)
    await session.commit()

    repo = JobEmbeddingRepository(session)
    created = await repo.upsert_for_target(
        job_id=job_id,
        embedding=_vec(0.1),
        content_fingerprint="fp-1",
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model=ACTIVE_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )
    await session.commit()

    refreshed = await repo.upsert_for_target(
        job_id=job_id,
        embedding=_vec(0.9),
        content_fingerprint="fp-2",
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model=ACTIVE_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )
    await session.commit()

    all_rows = (await session.exec(select(JobEmbedding))).all()
    assert len(all_rows) == 1
    assert created.id == refreshed.id
    assert all_rows[0].content_fingerprint == "fp-2"
    assert list(all_rows[0].embedding) == _vec(0.9)


@pytest.mark.asyncio
async def test_list_fresh_job_ids_for_target_uses_content_fingerprint(
    session: AsyncSession,
) -> None:
    job_fresh = _build_job(job_id="job-fresh", content_fingerprint="fresh-fp")
    job_stale = _build_job(job_id="job-stale", content_fingerprint="new-fp")
    fresh_job_id = job_fresh.id
    stale_job_id = job_stale.id
    session.add(job_fresh)
    session.add(job_stale)
    await session.commit()

    repo = JobEmbeddingRepository(session)
    await repo.upsert_for_target(
        job_id=fresh_job_id,
        embedding=_vec(0.1),
        content_fingerprint="fresh-fp",
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model=ACTIVE_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )
    await repo.upsert_for_target(
        job_id=stale_job_id,
        embedding=_vec(0.3),
        content_fingerprint="old-fp",
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model=ACTIVE_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )
    await session.commit()

    fresh_ids = await repo.list_fresh_job_ids_for_target(
        job_content_fingerprints={
            fresh_job_id: "fresh-fp",
            stale_job_id: "new-fp",
        },
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model=ACTIVE_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )

    assert fresh_ids == {fresh_job_id}


@pytest.mark.asyncio
async def test_get_by_job_and_target_ignores_rows_from_other_targets(
    session: AsyncSession,
) -> None:
    job = _build_job(job_id="job-iso", content_fingerprint="fp-iso")
    job_id = job.id
    session.add(job)
    await session.commit()

    repo = JobEmbeddingRepository(session)
    await repo.upsert_for_target(
        job_id=job_id,
        embedding=_vec(0.2),
        content_fingerprint="fp-iso",
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model=ACTIVE_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )
    await repo.upsert_for_target(
        job_id=job_id,
        embedding=_vec(0.7),
        content_fingerprint="fp-iso",
        embedding_kind="job_description",
        embedding_target_revision=2,
        embedding_model=OTHER_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )
    await session.commit()

    active_row = await repo.get_by_job_and_target(
        job_id=job_id,
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model=ACTIVE_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )
    other_row = await repo.get_by_job_and_target(
        job_id=job_id,
        embedding_kind="job_description",
        embedding_target_revision=2,
        embedding_model=OTHER_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )

    assert active_row is not None
    assert other_row is not None
    assert active_row.embedding_target_revision == 1
    assert other_row.embedding_target_revision == 2
    assert active_row.id != other_row.id


@pytest.mark.asyncio
async def test_list_by_job_ids_and_fresh_ids_only_use_active_target_rows(
    session: AsyncSession,
) -> None:
    active_job = _build_job(job_id="job-active", content_fingerprint="fp-active")
    other_target_job = _build_job(job_id="job-other-target", content_fingerprint="fp-other")
    active_job_id = active_job.id
    other_target_job_id = other_target_job.id
    session.add(active_job)
    session.add(other_target_job)
    await session.commit()

    repo = JobEmbeddingRepository(session)
    await repo.upsert_for_target(
        job_id=active_job_id,
        embedding=_vec(0.2),
        content_fingerprint="fp-active",
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model=ACTIVE_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )
    await repo.upsert_for_target(
        job_id=other_target_job_id,
        embedding=_vec(0.7),
        content_fingerprint="fp-other",
        embedding_kind="job_description",
        embedding_target_revision=2,
        embedding_model=OTHER_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )
    await session.commit()

    rows_by_job = await repo.list_by_job_ids_and_target(
        job_ids=[active_job_id, other_target_job_id],
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model=ACTIVE_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )
    fresh_ids = await repo.list_fresh_job_ids_for_target(
        job_content_fingerprints={
            active_job_id: "fp-active",
            other_target_job_id: "fp-other",
        },
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model=ACTIVE_TARGET_MODEL,
        embedding_dim=EMBEDDING_DIM,
    )

    assert set(rows_by_job) == {active_job_id}
    assert fresh_ids == {active_job_id}
