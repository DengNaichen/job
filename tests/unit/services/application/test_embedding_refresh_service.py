from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job, JobEmbedding, JobStatus, PlatformType, Source
from app.services.application.embedding_refresh import EmbeddingRefreshService
from app.services.domain.job_embedding_text import build_job_embedding_text
from app.services.infra.embedding import EmbeddingConfig, EmbeddingTargetDescriptor

EMBEDDING_DIM = 768


def _make_source(identifier: str) -> Source:
    return Source(
        name=identifier.title(),
        name_normalized=identifier,
        platform=PlatformType.GREENHOUSE,
        identifier=identifier,
    )


def _make_job(
    *,
    job_id: str,
    source_id: str,
    status: JobStatus = JobStatus.open,
    description: str = "Build resilient pipelines",
    fingerprint: str | None = None,
    structured_jd: dict[str, object] | None = None,
) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        id=job_id,
        source_id=source_id,
        external_job_id=f"ext-{job_id}",
        title=f"Job {job_id}",
        apply_url=f"https://example.com/{job_id}",
        description_plain=description,
        structured_jd=structured_jd,
        content_fingerprint=fingerprint,
        status=status,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )


def _target() -> EmbeddingTargetDescriptor:
    return EmbeddingTargetDescriptor(
        embedding_kind="job_description",
        embedding_target_revision=2,
        embedding_model="gemini/gemini-embedding-001",
        embedding_dim=EMBEDDING_DIM,
    )


@pytest.mark.asyncio
async def test_embedding_refresh_service_skips_when_runtime_flag_disabled(
    session: AsyncSession,
) -> None:
    service = EmbeddingRefreshService(
        session=session,
        settings_provider=lambda: SimpleNamespace(
            embedding_refresh_enabled=False,
            embedding_refresh_batch_size=2,
            embedding_dim=EMBEDDING_DIM,
        ),
        embedding_config_provider=lambda: EmbeddingConfig(
            provider="gemini",
            model="gemini-embedding-001",
        ),
        target_resolver=lambda **_: _target(),
    )

    result = await service.refresh_for_source(source_id="source-disabled", snapshot_run_id="run-1")

    assert result.triggered is False
    assert result.selected_jobs == 0
    assert result.refreshed_jobs == 0
    assert result.error is None


@pytest.mark.asyncio
async def test_embedding_refresh_service_refreshes_only_open_source_jobs(
    session: AsyncSession,
) -> None:
    source = _make_source("airbnb")
    other_source = _make_source("stripe")
    session.add(source)
    session.add(other_source)
    await session.flush()

    source_id = str(source.id)
    other_source_id = str(other_source.id)
    open_job = _make_job(
        job_id="job-open",
        source_id=source_id,
        status=JobStatus.open,
        fingerprint="fp-open",
        structured_jd={
            "required_skills": ["Python"],
            "job_domain_normalized": "software_engineering",
            "seniority_level": "mid",
        },
    )
    second_open_job = _make_job(
        job_id="job-open-2",
        source_id=source_id,
        status=JobStatus.open,
        fingerprint="fp-open-2",
    )
    closed_job = _make_job(
        job_id="job-closed",
        source_id=source_id,
        status=JobStatus.closed,
        fingerprint="fp-closed",
    )
    other_source_job = _make_job(
        job_id="job-other-source",
        source_id=other_source_id,
        status=JobStatus.open,
        fingerprint="fp-other",
    )
    session.add(open_job)
    session.add(second_open_job)
    session.add(closed_job)
    session.add(other_source_job)
    await session.commit()

    calls: list[list[str]] = []

    async def fake_embed_texts(texts: list[str], **_kwargs):  # noqa: ANN003
        calls.append(texts)
        return [[0.1] * EMBEDDING_DIM for _ in texts]

    service = EmbeddingRefreshService(
        session=session,
        embedding_fn=fake_embed_texts,
        settings_provider=lambda: SimpleNamespace(
            embedding_refresh_enabled=True,
            embedding_refresh_batch_size=2,
            embedding_dim=EMBEDDING_DIM,
        ),
        embedding_config_provider=lambda: EmbeddingConfig(
            provider="gemini",
            model="gemini-embedding-001",
        ),
        target_resolver=lambda **_: _target(),
    )

    result = await service.refresh_for_source(source_id=source_id, snapshot_run_id="run-2")

    rows = (
        await session.exec(
            select(JobEmbedding).where(
                JobEmbedding.embedding_kind == "job_description",
                JobEmbedding.embedding_target_revision == 2,
                JobEmbedding.embedding_model == "gemini/gemini-embedding-001",
                JobEmbedding.embedding_dim == EMBEDDING_DIM,
            )
        )
    ).all()
    embedded_job_ids = {row.job_id for row in rows}

    assert result.triggered is True
    assert result.selected_jobs == 2
    assert result.attempted_jobs == 2
    assert result.refreshed_jobs == 2
    assert result.failed_jobs == 0
    assert calls == [[
        build_job_embedding_text(
            title="Job job-open",
            description="Build resilient pipelines",
            structured_jd={
                "required_skills": ["Python"],
                "job_domain_normalized": "software_engineering",
                "seniority_level": "mid",
            },
        ),
        build_job_embedding_text(
            title="Job job-open-2",
            description="Build resilient pipelines",
            structured_jd=None,
        ),
    ]]
    assert embedded_job_ids == {"job-open", "job-open-2"}
    assert "job-closed" not in embedded_job_ids
    assert "job-other-source" not in embedded_job_ids


@pytest.mark.asyncio
async def test_embedding_refresh_service_reports_embedding_failures(
    session: AsyncSession,
) -> None:
    source = _make_source("failing")
    session.add(source)
    await session.flush()
    source_id = str(source.id)
    session.add(
        _make_job(
            job_id="job-fail",
            source_id=source_id,
            status=JobStatus.open,
            fingerprint="fp-fail",
        )
    )
    await session.commit()

    async def failing_embed_texts(_texts: list[str], **_kwargs):  # noqa: ANN003
        raise RuntimeError("embedding provider unavailable")

    service = EmbeddingRefreshService(
        session=session,
        embedding_fn=failing_embed_texts,
        settings_provider=lambda: SimpleNamespace(
            embedding_refresh_enabled=True,
            embedding_refresh_batch_size=1,
            embedding_dim=EMBEDDING_DIM,
        ),
        embedding_config_provider=lambda: EmbeddingConfig(
            provider="gemini",
            model="gemini-embedding-001",
        ),
        target_resolver=lambda **_: _target(),
    )

    result = await service.refresh_for_source(source_id=source_id, snapshot_run_id="run-failed")
    rows = (await session.exec(select(JobEmbedding))).all()

    assert result.triggered is True
    assert result.selected_jobs == 1
    assert result.attempted_jobs == 1
    assert result.refreshed_jobs == 0
    assert result.failed_jobs == 1
    assert result.error == "embedding provider unavailable"
    assert rows == []
