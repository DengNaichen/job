"""Unit tests for scripts/batch_parse_jd.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.models import Job
from app.schemas.structured_jd import BatchStructuredJD, BatchStructuredJDItem


def _load_batch_parse_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "batch_parse_jd.py"
    spec = importlib.util.spec_from_file_location("batch_parse_jd_test_module", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover - importlib guard
        raise RuntimeError("Unable to load batch_parse_jd.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_job(job_id: str) -> Job:
    return Job(
        id=job_id,
        source="greenhouse",
        external_job_id=f"ext-{job_id}",
        title=f"Job {job_id}",
        apply_url="https://example.com/apply",
        raw_payload={},
    )


class FakeBatchService:
    def __init__(
        self,
        *,
        parse_fail_job_ids: set[str] | None = None,
        persist_fail_job_ids: set[str] | None = None,
    ) -> None:
        self.parse_fail_job_ids = parse_fail_job_ids or set()
        self.persist_fail_job_ids = persist_fail_job_ids or set()
        self.persisted_batches: list[list[str]] = []

    async def parse_jobs(self, jobs: list[Job], persist: bool = False) -> BatchStructuredJD:
        assert persist is False
        job_ids = [str(job.id) for job in jobs]
        if set(job_ids) & self.parse_fail_job_ids:
            raise RuntimeError("parse failed")
        return BatchStructuredJD(
            jobs=[
                BatchStructuredJDItem(
                    job_id=job_id,
                    required_skills=["python"],
                    job_domain_normalized="software_engineering",
                )
                for job_id in job_ids
            ]
        )

    async def persist_jobs_by_ids(
        self,
        job_ids: list[str],
        parsed_items: list[BatchStructuredJDItem],
    ) -> None:
        if set(job_ids) & self.persist_fail_job_ids:
            raise RuntimeError("persist failed")
        self.persisted_batches.append(job_ids)
        assert [item.job_id for item in parsed_items] == job_ids


def test_chunk_jobs_splits_tail_batch() -> None:
    module = _load_batch_parse_module()
    jobs = [_build_job(f"job-{index}") for index in range(23)]

    batches = module._chunk_jobs(jobs, 10)

    assert [len(batch) for batch in batches] == [10, 10, 3]
    assert [str(job.id) for job in batches[-1]] == ["job-20", "job-21", "job-22"]


@pytest.mark.asyncio
async def test_process_round_persists_successful_batches_only() -> None:
    module = _load_batch_parse_module()
    jobs = [_build_job(f"job-{index}") for index in range(30)]
    service = FakeBatchService(parse_fail_job_ids={f"job-{index}" for index in range(10, 20)})

    summary = await module._process_round(service, jobs, batch_size=10)

    assert summary.batch_count == 3
    assert summary.success_batches == 2
    assert summary.failed_batches == 1
    assert summary.success_jobs == 20
    assert summary.failed_jobs == 10
    assert summary.failed_job_ids == [f"job-{index}" for index in range(10, 20)]
    assert service.persisted_batches == [
        [f"job-{index}" for index in range(0, 10)],
        [f"job-{index}" for index in range(20, 30)],
    ]


@pytest.mark.asyncio
async def test_process_round_counts_persist_failures_as_failed_jobs() -> None:
    module = _load_batch_parse_module()
    jobs = [_build_job(f"job-{index}") for index in range(20)]
    service = FakeBatchService(persist_fail_job_ids={f"job-{index}" for index in range(10, 20)})

    summary = await module._process_round(service, jobs, batch_size=10)

    assert summary.success_batches == 1
    assert summary.failed_batches == 1
    assert summary.success_jobs == 10
    assert summary.failed_jobs == 10
    assert summary.failed_job_ids == [f"job-{index}" for index in range(10, 20)]
    assert service.persisted_batches == [[f"job-{index}" for index in range(0, 10)]]
