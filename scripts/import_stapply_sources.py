#!/usr/bin/env python3
"""Import missing ATS sources from stapply-ai/ats-scrapers company CSV files.

Default behavior is a dry run that compares CSV-derived identifiers with the
current `sources` table and prints a summary. Pass `--apply` to insert missing
rows for currently supported platforms.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import engine
from app.ingest.fetchers import (
    AshbyFetcher,
    GreenhouseFetcher,
    LeverFetcher,
    SmartRecruitersFetcher,
)
from app.ingest.mappers import AshbyMapper, GreenhouseMapper, LeverMapper, SmartRecruitersMapper
from app.models import PlatformType, Source, normalize_name


SUPPORTED_PLATFORMS: tuple[PlatformType, ...] = (
    PlatformType.ASHBY,
    PlatformType.GREENHOUSE,
    PlatformType.LEVER,
    PlatformType.SMARTRECRUITERS,
)


@dataclass(frozen=True)
class PlatformCSVConfig:
    platform: PlatformType
    relative_path: str
    identifier_from_url: Callable[[str], str | None]


@dataclass(frozen=True)
class SourceCandidate:
    platform: PlatformType
    name: str
    identifier: str
    url: str


@dataclass
class CompareSummary:
    csv_rows: int = 0
    valid_candidates: int = 0
    csv_duplicates: int = 0
    csv_name_duplicates: int = 0
    existing_in_db: int = 0
    name_collisions: int = 0
    insertable_missing: int = 0
    inserted: int = 0


@dataclass
class VerificationSummary:
    checked: int = 0
    eligible_for_apply: int = 0
    invalid_name: int = 0
    invalid_identifier: int = 0
    fetch_failed: int = 0
    empty_results: int = 0
    sample_map_failed: int = 0


@dataclass
class CandidateVerification:
    candidate: SourceCandidate
    name_ok: bool
    identifier_ok: bool
    fetch_ok: bool
    map_ok: bool | None
    job_count: int
    eligible_for_apply: bool
    reasons: list[str] = field(default_factory=list)


PLATFORM_CONFIGS: tuple[PlatformCSVConfig, ...] = (
    PlatformCSVConfig(
        platform=PlatformType.ASHBY,
        relative_path="ashby/companies.csv",
        identifier_from_url=lambda url: _first_path_segment(url),
    ),
    PlatformCSVConfig(
        platform=PlatformType.GREENHOUSE,
        relative_path="greenhouse/greenhouse_companies.csv",
        identifier_from_url=lambda url: _first_path_segment(url),
    ),
    PlatformCSVConfig(
        platform=PlatformType.LEVER,
        relative_path="lever/lever_companies.csv",
        identifier_from_url=lambda url: _first_path_segment(url),
    ),
    PlatformCSVConfig(
        platform=PlatformType.SMARTRECRUITERS,
        relative_path="smartrecruiters/companies.csv",
        identifier_from_url=lambda url: _first_path_segment(url),
    ),
)


FETCHER_FACTORIES = {
    PlatformType.ASHBY: AshbyFetcher,
    PlatformType.GREENHOUSE: GreenhouseFetcher,
    PlatformType.LEVER: LeverFetcher,
    PlatformType.SMARTRECRUITERS: SmartRecruitersFetcher,
}


MAPPER_FACTORIES = {
    PlatformType.ASHBY: AshbyMapper,
    PlatformType.GREENHOUSE: GreenhouseMapper,
    PlatformType.LEVER: LeverMapper,
    PlatformType.SMARTRECRUITERS: SmartRecruitersMapper,
}


def _first_path_segment(url: str) -> str | None:
    parsed = urlparse(url.strip())
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return None
    return path_parts[0].strip() or None


def _candidate_key(platform: PlatformType, identifier: str) -> tuple[str, str]:
    platform_value = platform.value if isinstance(platform, PlatformType) else str(platform).strip()
    return (platform_value, identifier.strip().casefold())


def _source_name_key(platform: PlatformType, name: str) -> tuple[str, str]:
    platform_value = platform.value if isinstance(platform, PlatformType) else str(platform).strip()
    return (platform_value, normalize_name(name))


def load_candidates(
    clone_path: Path,
    *,
    platform_filter: set[PlatformType] | None = None,
) -> tuple[list[SourceCandidate], dict[str, CompareSummary]]:
    candidates: list[SourceCandidate] = []
    summaries: dict[str, CompareSummary] = defaultdict(CompareSummary)
    seen_identifier_keys: set[tuple[str, str]] = set()
    seen_name_keys: set[tuple[str, str]] = set()

    for config in PLATFORM_CONFIGS:
        if platform_filter and config.platform not in platform_filter:
            continue

        csv_path = clone_path / config.relative_path
        if not csv_path.exists():
            continue

        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                summaries[config.platform.value].csv_rows += 1

                name = str(row.get("name") or "").strip()
                url = str(row.get("url") or "").strip()
                identifier = (config.identifier_from_url(url) or "").strip()

                if not name or not url or not identifier:
                    continue

                key = _candidate_key(config.platform, identifier)
                if key in seen_identifier_keys:
                    summaries[config.platform.value].csv_duplicates += 1
                    continue

                name_key = _source_name_key(config.platform, name)
                if name_key in seen_name_keys:
                    summaries[config.platform.value].csv_name_duplicates += 1
                    continue

                seen_identifier_keys.add(key)
                seen_name_keys.add(name_key)
                summaries[config.platform.value].valid_candidates += 1
                candidates.append(
                    SourceCandidate(
                        platform=config.platform,
                        name=name,
                        identifier=identifier,
                        url=url,
                    )
                )

    return candidates, summaries


async def compare_candidates(
    *,
    candidates: list[SourceCandidate],
    summaries: dict[str, CompareSummary],
) -> list[SourceCandidate]:
    if not candidates:
        return []

    async with AsyncSession(engine) as session:
        existing_sources = await session.exec(
            select(Source).where(Source.platform.in_([candidate.platform for candidate in candidates]))
        )
        existing_rows = list(existing_sources.all())

        existing_by_identifier = {
            _candidate_key(source.platform, source.identifier): source
            for source in existing_rows
        }
        existing_by_name = {
            _source_name_key(source.platform, source.name): source
            for source in existing_rows
        }

        insertable: list[SourceCandidate] = []

        for candidate in candidates:
            platform_key = candidate.platform.value
            identifier_key = _candidate_key(candidate.platform, candidate.identifier)
            if identifier_key in existing_by_identifier:
                summaries[platform_key].existing_in_db += 1
                continue

            name_key = _source_name_key(candidate.platform, candidate.name)
            if name_key in existing_by_name:
                summaries[platform_key].name_collisions += 1
                continue

            summaries[platform_key].insertable_missing += 1
            insertable.append(candidate)

        return insertable


def validate_candidate_name(candidate: SourceCandidate) -> list[str]:
    reasons: list[str] = []
    name = candidate.name.strip()
    normalized = normalize_name(name)
    if not name:
        reasons.append("blank_name")
    if not normalized:
        reasons.append("normalized_name_empty")
    if name.lower().startswith(("http://", "https://")):
        reasons.append("name_looks_like_url")
    if name.isdigit():
        reasons.append("name_is_numeric_only")
    if normalized == candidate.identifier.strip().casefold() and candidate.identifier.strip().isdigit():
        reasons.append("name_matches_numeric_identifier")
    return reasons


def validate_candidate_identifier(candidate: SourceCandidate) -> list[str]:
    reasons: list[str] = []
    identifier = candidate.identifier.strip()
    if not identifier:
        reasons.append("blank_identifier")
    if "/" in identifier:
        reasons.append("identifier_contains_slash")
    if identifier.lower().startswith(("http://", "https://")):
        reasons.append("identifier_is_url")
    if any(char.isspace() for char in identifier):
        reasons.append("identifier_contains_whitespace")
    return reasons


async def verify_candidate(candidate: SourceCandidate) -> CandidateVerification:
    reasons: list[str] = []
    name_reasons = validate_candidate_name(candidate)
    identifier_reasons = validate_candidate_identifier(candidate)
    reasons.extend(name_reasons)
    reasons.extend(identifier_reasons)

    name_ok = not name_reasons
    identifier_ok = not identifier_reasons
    if not identifier_ok:
        return CandidateVerification(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=False,
            fetch_ok=False,
            map_ok=None,
            job_count=0,
            eligible_for_apply=False,
            reasons=reasons,
        )

    fetcher = FETCHER_FACTORIES[candidate.platform]()
    mapper = MAPPER_FACTORIES[candidate.platform]()
    try:
        raw_jobs = await fetcher.fetch(candidate.identifier, include_content=False)
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"fetch_failed:{type(exc).__name__}")
        return CandidateVerification(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=True,
            fetch_ok=False,
            map_ok=None,
            job_count=0,
            eligible_for_apply=False,
            reasons=reasons,
        )

    job_count = len(raw_jobs)
    if not raw_jobs:
        reasons.append("no_jobs_returned")
        return CandidateVerification(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=True,
            fetch_ok=True,
            map_ok=None,
            job_count=0,
            eligible_for_apply=False,
            reasons=reasons,
        )

    try:
        mapper.map(raw_jobs[0])
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"sample_map_failed:{type(exc).__name__}")
        return CandidateVerification(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=True,
            fetch_ok=True,
            map_ok=False,
            job_count=job_count,
            eligible_for_apply=False,
            reasons=reasons,
        )

    return CandidateVerification(
        candidate=candidate,
        name_ok=name_ok,
        identifier_ok=True,
        fetch_ok=True,
        map_ok=True,
        job_count=job_count,
        eligible_for_apply=name_ok,
        reasons=reasons,
    )


async def verify_candidates(
    candidates: list[SourceCandidate],
    *,
    limit: int | None,
    concurrency: int,
) -> tuple[list[CandidateVerification], VerificationSummary]:
    selected = candidates[:limit] if limit is not None else candidates
    summary = VerificationSummary()
    if not selected:
        return [], summary

    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(candidate: SourceCandidate) -> CandidateVerification:
        async with semaphore:
            return await verify_candidate(candidate)

    results = await asyncio.gather(*(run_one(candidate) for candidate in selected))

    for result in results:
        summary.checked += 1
        if not result.name_ok:
            summary.invalid_name += 1
        if not result.identifier_ok:
            summary.invalid_identifier += 1
        elif not result.fetch_ok:
            summary.fetch_failed += 1
        elif result.job_count == 0:
            summary.empty_results += 1
        elif result.map_ok is False:
            summary.sample_map_failed += 1
        if result.eligible_for_apply:
            summary.eligible_for_apply += 1

    return results, summary


async def apply_candidates(
    verifications: list[CandidateVerification],
    summaries: dict[str, CompareSummary],
) -> int:
    eligible = [result.candidate for result in verifications if result.eligible_for_apply]
    if not eligible:
        return 0

    async with AsyncSession(engine) as session:
        for candidate in eligible:
            session.add(
                Source(
                    name=candidate.name.strip(),
                    name_normalized=normalize_name(candidate.name),
                    platform=candidate.platform,
                    identifier=candidate.identifier.strip(),
                    enabled=True,
                    notes=(
                        "Imported from stapply-ai/ats-scrapers company CSV "
                        f"({candidate.url})"
                    ),
                )
            )
            summaries[candidate.platform.value].inserted += 1
        await session.commit()
    return len(eligible)


def _parse_platforms(values: list[str] | None) -> set[PlatformType] | None:
    if not values:
        return None
    return {PlatformType(value) for value in values}


def _default_clone_path() -> Path | None:
    marker = Path("/tmp/ats-scrapers-path.txt")
    if marker.exists():
        candidate = Path(marker.read_text(encoding="utf-8").strip())
        if candidate.exists():
            return candidate
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare stapply-ai/ats-scrapers company CSVs against the local sources table.",
    )
    parser.add_argument(
        "--clone-path",
        default=str(_default_clone_path()) if _default_clone_path() else None,
        help="Path to a local clone of stapply-ai/ats-scrapers.",
    )
    parser.add_argument(
        "--platform",
        action="append",
        choices=[platform.value for platform in SUPPORTED_PLATFORMS],
        help="Limit import to one or more supported platforms.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Insert missing sources into the database. This always performs live verification first.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run live fetcher/mapper verification for missing sources without inserting them.",
    )
    parser.add_argument(
        "--verify-limit",
        type=int,
        default=None,
        help="Only verify the first N missing sources after diffing.",
    )
    parser.add_argument(
        "--verify-concurrency",
        type=int,
        default=10,
        help="Concurrent live verification requests.",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    if not args.clone_path:
        raise SystemExit(
            "Missing --clone-path. Clone stapply-ai/ats-scrapers locally first."
        )

    clone_path = Path(args.clone_path).expanduser().resolve()
    if not clone_path.exists():
        raise SystemExit(f"Clone path does not exist: {clone_path}")

    platform_filter = _parse_platforms(args.platform)
    candidates, summaries = load_candidates(clone_path, platform_filter=platform_filter)

    print(f"clone_path={clone_path}")
    print(f"candidate_rows={len(candidates)}")
    mode = "apply" if args.apply else "dry-run"
    if args.verify and not args.apply:
        mode = "verify"
    print(f"mode={mode}")

    insertable = await compare_candidates(
        candidates=candidates,
        summaries=summaries,
    )

    print("=== PLATFORM SUMMARY ===")
    for platform in sorted(summaries):
        summary = summaries[platform]
        print(
            f"{platform}: csv_rows={summary.csv_rows}, "
            f"valid_candidates={summary.valid_candidates}, "
            f"csv_duplicates={summary.csv_duplicates}, "
            f"csv_name_duplicates={summary.csv_name_duplicates}, "
            f"existing_in_db={summary.existing_in_db}, "
            f"name_collisions={summary.name_collisions}, "
            f"insertable_missing={summary.insertable_missing}, "
            f"inserted={summary.inserted}"
        )

    print(f"missing_total={len(insertable)}")
    if insertable:
        print("sample_missing=")
        for candidate in insertable[:20]:
            print(
                f"  - {candidate.platform.value}: "
                f"{candidate.identifier} ({candidate.name})"
            )

    if args.verify or args.apply:
        print("=== LIVE VERIFICATION ===")
        verifications, verification_summary = await verify_candidates(
            insertable,
            limit=args.verify_limit,
            concurrency=args.verify_concurrency,
        )
        print(
            f"checked={verification_summary.checked}, "
            f"eligible_for_apply={verification_summary.eligible_for_apply}, "
            f"invalid_name={verification_summary.invalid_name}, "
            f"invalid_identifier={verification_summary.invalid_identifier}, "
            f"fetch_failed={verification_summary.fetch_failed}, "
            f"empty_results={verification_summary.empty_results}, "
            f"sample_map_failed={verification_summary.sample_map_failed}"
        )
        for result in verifications[:20]:
            print(
                f"  - {result.candidate.platform.value}: {result.candidate.identifier} "
                f"name_ok={result.name_ok} fetch_ok={result.fetch_ok} "
                f"map_ok={result.map_ok} jobs={result.job_count} "
                f"eligible={result.eligible_for_apply} reasons={','.join(result.reasons) or '-'}"
            )

        if args.apply:
            inserted = await apply_candidates(verifications, summaries)
            print(f"inserted_after_verification={inserted}")

    return 0


def main() -> None:
    args = build_parser().parse_args()
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
