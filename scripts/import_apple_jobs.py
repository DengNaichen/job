#!/usr/bin/env python3
"""Import Apple jobs with same-source full snapshot reconcile.

Create the source manually via ``POST /api/v1/sources`` before running this script.

Apple:
    {"name": "Apple", "platform": "apple", "identifier": "apple"}
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import engine
from app.ingest.fetchers.apple import AppleFetcher
from app.ingest.mappers.apple import AppleMapper
from app.models import PlatformType, Source
from app.services.application.full_snapshot_sync import FullSnapshotSyncService, SourceSyncResult


@dataclass
class RunSummary:
    source_identifier: str
    result: SourceSyncResult


async def _load_apple_sources(
    *,
    slug: str | None,
    limit: int | None,
) -> list[Source]:
    async with AsyncSession(engine) as session:
        statement = (
            select(Source)
            .where(
                Source.platform == PlatformType.APPLE,
                Source.enabled.is_(True),
            )
            .order_by(Source.identifier)
        )
        if slug is not None:
            statement = statement.where(Source.identifier == slug)
        elif limit is not None:
            statement = statement.limit(limit)
        rows = await session.exec(statement)
        return list(rows.all())


async def _sync_source(
    *,
    source: Source,
    include_content: bool,
    fetcher: AppleFetcher,
    mapper: AppleMapper,
    dry_run: bool,
) -> SourceSyncResult:
    async with AsyncSession(engine) as session:
        service = FullSnapshotSyncService(session)
        return await service.sync_source(
            source=source,
            fetcher=fetcher,
            mapper=mapper,
            include_content=include_content,
            dry_run=dry_run,
        )


async def run(args: argparse.Namespace) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    sources = await _load_apple_sources(slug=args.slug, limit=args.limit)
    fetcher = AppleFetcher()
    mapper = AppleMapper()

    print(f"target_sources={len(sources)}")
    print(f"include_content={args.include_content}")
    print(f"dry_run={args.dry_run}")

    summaries: list[RunSummary] = []
    failures: list[RunSummary] = []
    totals = {
        "fetched": 0,
        "mapped": 0,
        "unique": 0,
        "deduped_by_external_id": 0,
        "inserted": 0,
        "updated": 0,
        "closed": 0,
    }

    for idx, source in enumerate(sources, start=1):
        result = await _sync_source(
            source=source,
            include_content=args.include_content,
            fetcher=fetcher,
            mapper=mapper,
            dry_run=args.dry_run,
        )
        summary = RunSummary(source_identifier=source.identifier, result=result)
        if result.ok:
            summaries.append(summary)
        else:
            failures.append(summary)

        stats = result.stats
        totals["fetched"] += stats.fetched_count
        totals["mapped"] += stats.mapped_count
        totals["unique"] += stats.unique_count
        totals["deduped_by_external_id"] += stats.deduped_by_external_id
        totals["inserted"] += stats.inserted_count
        totals["updated"] += stats.updated_count
        totals["closed"] += stats.closed_count

        prefix = f"[{idx}/{len(sources)}] {source.identifier} ({result.source_key})"
        if result.ok:
            print(
                f"{prefix}: fetched={stats.fetched_count}, unique={stats.unique_count}, "
                f"deduped_by_external_id={stats.deduped_by_external_id}, "
                f"inserted={stats.inserted_count}, updated={stats.updated_count}, "
                f"closed={stats.closed_count}"
            )
        else:
            print(f"{prefix}: FAILED: {result.error}")

    print("=== SUMMARY ===")
    print(f"sources_total={len(sources)}")
    print(f"sources_success={len(summaries)}")
    print(f"sources_failed={len(failures)}")
    print(f"jobs_fetched_total={totals['fetched']}")
    print(f"jobs_mapped_total={totals['mapped']}")
    print(f"jobs_unique_total={totals['unique']}")
    print(f"jobs_deduped_by_external_id_total={totals['deduped_by_external_id']}")
    print(f"jobs_inserted_total={totals['inserted']}")
    print(f"jobs_updated_total={totals['updated']}")
    print(f"jobs_closed_total={totals['closed']}")
    if failures:
        print("failed_sources=" + ",".join(summary.source_identifier for summary in failures))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Apple jobs for one or all enabled source slugs."
    )
    parser.add_argument(
        "--slug",
        default=None,
        help="Exact Source.identifier to import. Defaults to all enabled Apple sources.",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Limit number of sources when running all."
    )
    parser.add_argument(
        "--include-content",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fetch job detail payloads to populate descriptions and qualification sections.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Process all records but rollback writes."
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
