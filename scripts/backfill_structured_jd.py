#!/usr/bin/env python3
"""Backfill structured_jd with concurrent single-job parsing."""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import litellm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import get_settings
from app.models import Job
from app.schemas.structured_jd import (
    build_structured_jd_projection,
    build_structured_jd_storage_payload,
)
from app.services.jd_parser import parse_jd
from app.services.llm import get_token_usage

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
litellm.set_verbose = False


@dataclass
class ParseResult:
    job_id: str
    structured: dict | None
    error: str | None


async def _parse_one(
    semaphore: asyncio.Semaphore,
    *,
    job_id: str,
    title: str | None,
    description: str,
    is_html: bool,
) -> ParseResult:
    async with semaphore:
        try:
            parsed = await parse_jd(description, is_html=is_html, title=title)
            return ParseResult(job_id=job_id, structured=parsed.model_dump(mode="python"), error=None)
        except Exception as exc:  # noqa: BLE001
            return ParseResult(job_id=job_id, structured=None, error=str(exc))


async def _fetch_pending_jobs(
    session: AsyncSession,
    limit: int,
    *,
    version_only: bool,
) -> list[Job]:
    version_filter = Job.structured_jd_version < 3
    if version_only:
        pending_filter = Job.structured_jd.is_not(None) & version_filter
    else:
        pending_filter = (Job.structured_jd.is_(None)) | version_filter

    result = await session.execute(
        select(Job)
        .where(pending_filter)
        .where((Job.description_html.is_not(None)) | (Job.description_plain.is_not(None)))
        .order_by(Job.updated_at, Job.id)
        .limit(limit)
    )
    return list(result.scalars().all())


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=settings.debug)

    target = args.limit
    chunk_size = args.chunk_size
    concurrency = args.concurrency

    if target <= 0:
        raise ValueError("limit must be > 0")
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if concurrency <= 0:
        raise ValueError("concurrency must be > 0")

    semaphore = asyncio.Semaphore(concurrency)
    get_token_usage().reset()

    success_total = 0
    failure_total = 0
    attempted_total = 0

    async with AsyncSession(engine) as session:
        while success_total < target:
            remaining = target - success_total
            jobs = await _fetch_pending_jobs(
                session,
                min(chunk_size, remaining),
                version_only=args.version_only,
            )
            if not jobs:
                logger.info("No more pending jobs to parse.")
                break

            job_payloads = []
            for job in jobs:
                if job.description_plain:
                    job_payloads.append((job.id, job.description_plain, False))
                elif job.description_html:
                    job_payloads.append((job.id, job.description_html, True))
                else:
                    # Shouldn't happen due SQL filter, but keep safe.
                    job_payloads.append((job.id, "", False))

            by_id = {job.id: job for job in jobs}
            tasks = [
                _parse_one(
                    semaphore,
                    job_id=job_id,
                    title=by_id[job_id].title if job_id in by_id else None,
                    description=description,
                    is_html=is_html,
                )
                for job_id, description, is_html in job_payloads
            ]
            results = await asyncio.gather(*tasks)
            attempted_total += len(results)

            now_tz = datetime.now(timezone.utc)
            now_naive = now_tz.replace(tzinfo=None)

            batch_success = 0
            batch_fail = 0
            for result in results:
                if result.structured is None:
                    batch_fail += 1
                    continue
                job = by_id.get(result.job_id)
                if job is None:
                    batch_fail += 1
                    continue
                job.structured_jd = build_structured_jd_storage_payload(result.structured)
                projection = build_structured_jd_projection(result.structured)
                job.sponsorship_not_available = str(projection["sponsorship_not_available"])
                job.job_domain_raw = projection["job_domain_raw"] if isinstance(projection["job_domain_raw"], str) else None
                job.job_domain_normalized = str(projection["job_domain_normalized"])
                job.min_degree_level = str(projection["min_degree_level"])
                job.min_degree_rank = int(projection["min_degree_rank"])
                job.structured_jd_version = int(projection["structured_jd_version"])
                job.structured_jd_updated_at = now_tz
                job.updated_at = now_naive
                session.add(job)
                batch_success += 1

            await session.commit()

            success_total += batch_success
            failure_total += batch_fail
            logger.info(
                "Structured JD progress success=%s/%s attempted=%s batch_success=%s batch_fail=%s total_fail=%s",
                success_total,
                target,
                attempted_total,
                batch_success,
                batch_fail,
                failure_total,
            )

    usage = get_token_usage()
    logger.info(
        "Done structured_jd backfill: success=%s attempted=%s failed=%s tokens_total=%s",
        success_total,
        attempted_total,
        failure_total,
        usage.total_tokens,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill structured_jd with concurrent single-job parsing")
    parser.add_argument("--limit", type=int, default=5000, help="Target number of successfully parsed jobs")
    parser.add_argument("--chunk-size", type=int, default=20, help="DB fetch size per loop")
    parser.add_argument("--concurrency", type=int, default=20, help="Concurrent parse_jd calls")
    parser.add_argument(
        "--version-only",
        action="store_true",
        help="Only reparse jobs with structured_jd_version < 3 and existing structured_jd.",
    )
    return parser.parse_args()


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
