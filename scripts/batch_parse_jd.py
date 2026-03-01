"""Batch parse pending JDs and persist structured_jd.

Usage:
    ./.venv/bin/python scripts/batch_parse_jd.py --limit 100 --batch-size 10 --concurrency 5
"""

import argparse
import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models import Job
from app.core.config import get_settings
from app.schemas.structured_jd import BatchStructuredJD
from app.services.application.jd_batch_parse import JDBatchParseService
from app.services.infra.llm import get_token_usage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@dataclass
class ParsedBatchResult:
    """Result for one parsed batch."""

    jobs: list[Job]
    parsed: BatchStructuredJD | None = None
    error: str | None = None


@dataclass
class RoundSummary:
    """Summary for a single concurrent batch round."""

    batch_count: int = 0
    success_batches: int = 0
    failed_batches: int = 0
    success_jobs: int = 0
    failed_jobs: int = 0
    failed_job_ids: list[str] = field(default_factory=list)


def _chunk_jobs(jobs: Sequence[Job], batch_size: int) -> list[list[Job]]:
    """Split fetched jobs into fixed-size batches."""
    return [list(jobs[index : index + batch_size]) for index in range(0, len(jobs), batch_size)]


async def _parse_batch(
    service: JDBatchParseService,
    jobs: list[Job],
) -> ParsedBatchResult:
    """Parse one batch without persisting so requests can run concurrently."""
    try:
        parsed = await service.parse_jobs(jobs, persist=False)
        return ParsedBatchResult(
            jobs=jobs,
            parsed=parsed,
        )
    except Exception as exc:  # noqa: BLE001
        return ParsedBatchResult(jobs=jobs, error=str(exc))


async def _process_round(
    service: JDBatchParseService,
    jobs: list[Job],
    *,
    batch_size: int,
) -> RoundSummary:
    """Parse a fetched job window concurrently and persist successful batches."""
    batches = _chunk_jobs(jobs, batch_size)
    summary = RoundSummary(batch_count=len(batches))
    batch_job_ids_list = [[str(job.id) for job in batch] for batch in batches]
    results = await asyncio.gather(*[_parse_batch(service, batch) for batch in batches])

    for batch_jobs, batch_job_ids, result in zip(batches, batch_job_ids_list, results):
        if result.error is not None:
            summary.failed_batches += 1
            summary.failed_jobs += len(batch_jobs)
            summary.failed_job_ids.extend(batch_job_ids)
            logger.error("Batch parse failed jobs=%s error=%s", batch_job_ids, result.error)
            continue

        try:
            if result.parsed is None:
                raise ValueError("parsed batch result is missing")
            await service.persist_jobs_by_ids(batch_job_ids, result.parsed.jobs)
        except Exception as exc:  # noqa: BLE001
            summary.failed_batches += 1
            summary.failed_jobs += len(batch_jobs)
            summary.failed_job_ids.extend(batch_job_ids)
            logger.error("Batch persist failed jobs=%s error=%s", batch_job_ids, str(exc))
            continue

        summary.success_batches += 1
        summary.success_jobs += len(batch_jobs)

    return summary


async def batch_parse(
    limit: int = 100,
    batch_size: int = 10,
    concurrency: int = 1,
    version_only: bool = False,
) -> None:
    """Batch parse jobs and persist structured_jd in chunks."""
    if limit <= 0:
        raise ValueError("limit must be > 0")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")
    if concurrency <= 0:
        raise ValueError("concurrency must be > 0")

    engine = create_async_engine(settings.database_url, echo=settings.debug)
    success_total = 0
    attempted_total = 0
    failed_total = 0
    failed_job_ids: set[str] = set()
    started_at = perf_counter()

    # Reset token usage before run.
    get_token_usage().reset()

    try:
        async with AsyncSession(engine) as session:
            service = JDBatchParseService(session)

            while success_total < limit:
                remaining = limit - success_total
                fetch_limit = min(remaining, batch_size * concurrency)
                round_started_at = perf_counter()
                jobs = await service.fetch_pending_jobs(
                    limit=fetch_limit,
                    version_only=version_only,
                    exclude_job_ids=failed_job_ids,
                )
                if not jobs:
                    logger.info("No more eligible pending jobs to parse.")
                    break

                attempted_total += len(jobs)
                summary = await _process_round(
                    service,
                    jobs,
                    batch_size=batch_size,
                )
                failed_job_ids.update(summary.failed_job_ids)
                success_total += summary.success_jobs
                failed_total += summary.failed_jobs

                usage = get_token_usage()
                logger.info(
                    (
                        "Structured JD batch progress success=%s/%s fetched=%s "
                        "batch_success=%s batch_fail=%s job_success=%s job_fail=%s "
                        "prompt_tokens=%s completion_tokens=%s total_tokens=%s round_elapsed=%.2fs"
                    ),
                    success_total,
                    limit,
                    len(jobs),
                    summary.success_batches,
                    summary.failed_batches,
                    summary.success_jobs,
                    summary.failed_jobs,
                    usage.total_prompt_tokens,
                    usage.total_completion_tokens,
                    usage.total_tokens,
                    perf_counter() - round_started_at,
                )
    finally:
        await engine.dispose()

    usage = get_token_usage()
    elapsed = perf_counter() - started_at
    avg_tokens_per_job = usage.total_tokens / success_total if success_total else 0.0
    avg_seconds_per_job = elapsed / success_total if success_total else 0.0
    logger.info(
        (
            "Done. success=%s attempted=%s failed=%s prompt_tokens=%s "
            "completion_tokens=%s total_tokens=%s avg_tokens_per_job=%.2f "
            "avg_seconds_per_job=%.2f elapsed=%.2fs"
        ),
        success_total,
        attempted_total,
        failed_total,
        usage.total_prompt_tokens,
        usage.total_completion_tokens,
        usage.total_tokens,
        avg_tokens_per_job,
        avg_seconds_per_job,
        elapsed,
    )
    if failed_job_ids:
        logger.warning(
            "Failed jobs excluded from rerun count=%s sample_ids=%s",
            len(failed_job_ids),
            sorted(failed_job_ids)[:10],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch parse JDs and persist structured_jd")
    parser.add_argument("--limit", type=int, default=100, help="Max jobs to process")
    parser.add_argument("--batch-size", type=int, default=10, help="Jobs per LLM batch")
    parser.add_argument(
        "--concurrency", type=int, default=1, help="Concurrent batch parse requests"
    )
    parser.add_argument(
        "--version-only",
        action="store_true",
        help="Only reparse jobs with structured_jd_version < 3 and existing structured_jd.",
    )
    args = parser.parse_args()

    asyncio.run(
        batch_parse(
            limit=args.limit,
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            version_only=args.version_only,
        )
    )


if __name__ == "__main__":
    main()
