from __future__ import annotations

import argparse
import asyncio
import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx
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


@dataclass(frozen=True)
class PlatformAuditConfig:
    platform: PlatformType
    relative_csv_path: str
    identifier_from_url: Callable[[str], str | None]
    fetcher_factory: Callable[[], Any]
    mapper_factory: Callable[[], Any]
    include_content: bool = False
    default_verify_concurrency: int = 10


@dataclass(frozen=True)
class SourceCandidate:
    platform: PlatformType
    name: str
    identifier: str
    url: str


@dataclass
class CandidateSummary:
    csv_rows: int = 0
    valid_candidates: int = 0
    duplicate_identifiers: int = 0
    duplicate_names: int = 0
    existing_in_db: int = 0
    name_collisions: int = 0
    missing_in_db: int = 0


@dataclass
class VerificationResult:
    candidate: SourceCandidate
    name_ok: bool
    identifier_ok: bool
    fetch_ok: bool
    map_ok: bool | None
    job_count: int
    eligible: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class VerificationSummary:
    checked: int = 0
    eligible: int = 0
    invalid_name: int = 0
    invalid_identifier: int = 0
    fetch_failed: int = 0
    empty_results: int = 0
    sample_map_failed: int = 0


def _first_path_segment(url: str) -> str | None:
    parts = [part for part in urlparse(url.strip()).path.split("/") if part]
    if not parts:
        return None
    return parts[0].strip() or None


def _smartrecruiters_identifier(url: str) -> str | None:
    parts = [part for part in urlparse(url.strip()).path.split("/") if part]
    if len(parts) >= 3 and parts[1] == "company":
        return parts[2].strip() or None
    if not parts:
        return None
    return parts[0].strip() or None


PLATFORM_AUDIT_CONFIGS: dict[PlatformType, PlatformAuditConfig] = {
    PlatformType.GREENHOUSE: PlatformAuditConfig(
        platform=PlatformType.GREENHOUSE,
        relative_csv_path="greenhouse/greenhouse_companies.csv",
        identifier_from_url=_first_path_segment,
        fetcher_factory=GreenhouseFetcher,
        mapper_factory=GreenhouseMapper,
        include_content=False,
        default_verify_concurrency=15,
    ),
    PlatformType.LEVER: PlatformAuditConfig(
        platform=PlatformType.LEVER,
        relative_csv_path="lever/lever_companies.csv",
        identifier_from_url=_first_path_segment,
        fetcher_factory=LeverFetcher,
        mapper_factory=LeverMapper,
        include_content=False,
        default_verify_concurrency=12,
    ),
    PlatformType.ASHBY: PlatformAuditConfig(
        platform=PlatformType.ASHBY,
        relative_csv_path="ashby/companies.csv",
        identifier_from_url=_first_path_segment,
        fetcher_factory=AshbyFetcher,
        mapper_factory=AshbyMapper,
        include_content=False,
        default_verify_concurrency=10,
    ),
    PlatformType.SMARTRECRUITERS: PlatformAuditConfig(
        platform=PlatformType.SMARTRECRUITERS,
        relative_csv_path="smartrecruiters/companies.csv",
        identifier_from_url=_smartrecruiters_identifier,
        fetcher_factory=SmartRecruitersFetcher,
        mapper_factory=SmartRecruitersMapper,
        include_content=False,
        default_verify_concurrency=3,
    ),
}


def default_stapply_clone_path() -> Path | None:
    marker = Path("/tmp/ats-scrapers-path.txt")
    if not marker.exists():
        return None
    candidate = Path(marker.read_text(encoding="utf-8").strip())
    return candidate if candidate.exists() else None


def platform_choices() -> list[str]:
    return [platform.value for platform in PLATFORM_AUDIT_CONFIGS]


def parse_platform(value: str) -> PlatformType:
    return PlatformType(value)


def load_candidates(
    clone_path: Path,
    platform: PlatformType,
) -> tuple[list[SourceCandidate], CandidateSummary]:
    config = PLATFORM_AUDIT_CONFIGS[platform]
    csv_path = clone_path / config.relative_csv_path
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing CSV for {platform.value}: {csv_path}")

    candidates: list[SourceCandidate] = []
    summary = CandidateSummary()
    seen_identifiers: set[str] = set()
    seen_names: set[str] = set()

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            summary.csv_rows += 1
            name = str(row.get("name") or "").strip()
            url = str(row.get("url") or "").strip()
            identifier = (config.identifier_from_url(url) or "").strip()
            if not name or not url or not identifier:
                continue

            identifier_key = identifier.casefold()
            if identifier_key in seen_identifiers:
                summary.duplicate_identifiers += 1
                continue

            name_key = normalize_name(name)
            if name_key in seen_names:
                summary.duplicate_names += 1
                continue

            seen_identifiers.add(identifier_key)
            seen_names.add(name_key)
            summary.valid_candidates += 1
            candidates.append(
                SourceCandidate(
                    platform=platform,
                    name=name,
                    identifier=identifier,
                    url=url,
                )
            )

    return candidates, summary


async def load_existing_sources(platform: PlatformType) -> list[Source]:
    async with AsyncSession(engine) as session:
        rows = await session.exec(select(Source).where(Source.platform == platform))
        return list(rows.all())


def filter_missing_candidates(
    candidates: list[SourceCandidate],
    existing_sources: list[Source],
    summary: CandidateSummary,
) -> list[SourceCandidate]:
    existing_identifiers = {source.identifier.strip().casefold() for source in existing_sources}
    existing_names = {normalize_name(source.name) for source in existing_sources}

    missing: list[SourceCandidate] = []
    for candidate in candidates:
        if candidate.identifier.strip().casefold() in existing_identifiers:
            summary.existing_in_db += 1
            continue

        if normalize_name(candidate.name) in existing_names:
            summary.name_collisions += 1
            continue

        summary.missing_in_db += 1
        missing.append(candidate)

    return missing


async def find_missing_candidates(
    clone_path: Path,
    platform: PlatformType,
) -> tuple[list[SourceCandidate], CandidateSummary]:
    candidates, summary = load_candidates(clone_path, platform)
    existing_sources = await load_existing_sources(platform)
    missing = filter_missing_candidates(candidates, existing_sources, summary)
    return missing, summary


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
    if (
        normalized == candidate.identifier.strip().casefold()
        and candidate.identifier.strip().isdigit()
    ):
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


async def verify_candidate(candidate: SourceCandidate) -> VerificationResult:
    config = PLATFORM_AUDIT_CONFIGS[candidate.platform]
    reasons: list[str] = []
    name_reasons = validate_candidate_name(candidate)
    identifier_reasons = validate_candidate_identifier(candidate)
    reasons.extend(name_reasons)
    reasons.extend(identifier_reasons)

    name_ok = not name_reasons
    identifier_ok = not identifier_reasons
    if not identifier_ok:
        return VerificationResult(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=False,
            fetch_ok=False,
            map_ok=None,
            job_count=0,
            eligible=False,
            reasons=reasons,
        )

    if candidate.platform == PlatformType.SMARTRECRUITERS:
        return await _verify_smartrecruiters_candidate(
            candidate,
            name_ok=name_ok,
            reasons=reasons,
        )

    return await _verify_standard_candidate(
        candidate,
        config=config,
        name_ok=name_ok,
        reasons=reasons,
    )


async def _verify_standard_candidate(
    candidate: SourceCandidate,
    *,
    config: PlatformAuditConfig,
    name_ok: bool,
    reasons: list[str],
) -> VerificationResult:
    fetcher = config.fetcher_factory()
    mapper = config.mapper_factory()

    try:
        raw_jobs = await fetcher.fetch(candidate.identifier, include_content=config.include_content)
    except httpx.HTTPStatusError as exc:
        reasons.append(f"http_status:{exc.response.status_code}")
        return VerificationResult(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=True,
            fetch_ok=False,
            map_ok=None,
            job_count=0,
            eligible=False,
            reasons=reasons,
        )
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"fetch_failed:{type(exc).__name__}")
        return VerificationResult(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=True,
            fetch_ok=False,
            map_ok=None,
            job_count=0,
            eligible=False,
            reasons=reasons,
        )

    job_count = len(raw_jobs) if isinstance(raw_jobs, list) else 0
    if not job_count:
        reasons.append("no_jobs_returned")
        return VerificationResult(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=True,
            fetch_ok=True,
            map_ok=None,
            job_count=0,
            eligible=False,
            reasons=reasons,
        )

    try:
        mapper.map(raw_jobs[0])
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"sample_map_failed:{type(exc).__name__}")
        return VerificationResult(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=True,
            fetch_ok=True,
            map_ok=False,
            job_count=job_count,
            eligible=False,
            reasons=reasons,
        )

    return VerificationResult(
        candidate=candidate,
        name_ok=name_ok,
        identifier_ok=True,
        fetch_ok=True,
        map_ok=True,
        job_count=job_count,
        eligible=name_ok,
        reasons=reasons,
    )


async def _verify_smartrecruiters_candidate(
    candidate: SourceCandidate,
    *,
    name_ok: bool,
    reasons: list[str],
) -> VerificationResult:
    mapper = SmartRecruitersMapper()
    timeout = httpx.Timeout(SmartRecruitersFetcher.REQUEST_TIMEOUT_SECONDS)
    list_url = f"{SmartRecruitersFetcher.BASE_URL}/{candidate.identifier}/postings"
    params = {"limit": 5, "offset": 0}

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(list_url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            reasons.append(f"http_status:{exc.response.status_code}")
            return VerificationResult(
                candidate=candidate,
                name_ok=name_ok,
                identifier_ok=True,
                fetch_ok=False,
                map_ok=None,
                job_count=0,
                eligible=False,
                reasons=reasons,
            )
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"fetch_failed:{type(exc).__name__}")
            return VerificationResult(
                candidate=candidate,
                name_ok=name_ok,
                identifier_ok=True,
                fetch_ok=False,
                map_ok=None,
                job_count=0,
                eligible=False,
                reasons=reasons,
            )

        payload = response.json()
        if not isinstance(payload, dict):
            reasons.append("invalid_list_payload")
            return VerificationResult(
                candidate=candidate,
                name_ok=name_ok,
                identifier_ok=True,
                fetch_ok=False,
                map_ok=None,
                job_count=0,
                eligible=False,
                reasons=reasons,
            )

        content = payload.get("content", [])
        if not isinstance(content, list):
            content = []

        total_found = SmartRecruitersFetcher._to_int_or_none(payload.get("totalFound")) or len(
            content
        )
        if total_found == 0 or not content:
            reasons.append("no_jobs_returned")
            return VerificationResult(
                candidate=candidate,
                name_ok=name_ok,
                identifier_ok=True,
                fetch_ok=True,
                map_ok=None,
                job_count=0,
                eligible=False,
                reasons=reasons,
            )

        detail_statuses: list[str] = []
        for summary in content:
            if not isinstance(summary, dict):
                continue
            detail_url = SmartRecruitersFetcher._detail_url(summary, candidate.identifier)
            try:
                detail_response = await client.get(detail_url)
                if detail_response.status_code == 404:
                    detail_statuses.append("http_status:404")
                    continue
                detail_response.raise_for_status()
                detail = detail_response.json()
                if not isinstance(detail, dict):
                    detail_statuses.append("invalid_detail_payload")
                    continue
                merged = dict(summary)
                merged.update(detail)
                mapper.map(merged)
                return VerificationResult(
                    candidate=candidate,
                    name_ok=name_ok,
                    identifier_ok=True,
                    fetch_ok=True,
                    map_ok=True,
                    job_count=total_found,
                    eligible=name_ok,
                    reasons=reasons,
                )
            except httpx.HTTPStatusError as exc:
                detail_statuses.append(f"http_status:{exc.response.status_code}")
            except Exception as exc:  # noqa: BLE001
                detail_statuses.append(f"sample_map_failed:{type(exc).__name__}")

        if detail_statuses:
            reasons.append(detail_statuses[0])
        else:
            reasons.append("sample_map_failed:NoUsableDetail")

        return VerificationResult(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=True,
            fetch_ok=True,
            map_ok=False,
            job_count=total_found,
            eligible=False,
            reasons=reasons,
        )


async def verify_candidates(
    candidates: list[SourceCandidate],
    *,
    concurrency: int,
    limit: int | None = None,
) -> tuple[list[VerificationResult], VerificationSummary]:
    selected = candidates[:limit] if limit is not None else candidates
    summary = VerificationSummary()
    if not selected:
        return [], summary

    semaphore = asyncio.Semaphore(concurrency)

    async def run_one(candidate: SourceCandidate) -> VerificationResult:
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
        if result.eligible:
            summary.eligible += 1

    return results, summary


def write_candidates_csv(path: Path, candidates: list[SourceCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["platform", "name", "identifier", "url"])
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "platform": candidate.platform.value,
                    "name": candidate.name,
                    "identifier": candidate.identifier,
                    "url": candidate.url,
                }
            )


def read_candidates_csv(path: Path) -> list[SourceCandidate]:
    candidates: list[SourceCandidate] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            platform_value = str(row.get("platform") or "").strip()
            if not platform_value:
                raise ValueError("Input CSV is missing platform values")
            candidates.append(
                SourceCandidate(
                    platform=PlatformType(platform_value),
                    name=str(row.get("name") or "").strip(),
                    identifier=str(row.get("identifier") or "").strip(),
                    url=str(row.get("url") or "").strip(),
                )
            )
    return candidates


def write_verification_csv(path: Path, results: list[VerificationResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "platform",
                "name",
                "identifier",
                "url",
                "name_ok",
                "identifier_ok",
                "fetch_ok",
                "map_ok",
                "job_count",
                "eligible",
                "reasons",
            ],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "platform": result.candidate.platform.value,
                    "name": result.candidate.name,
                    "identifier": result.candidate.identifier,
                    "url": result.candidate.url,
                    "name_ok": result.name_ok,
                    "identifier_ok": result.identifier_ok,
                    "fetch_ok": result.fetch_ok,
                    "map_ok": result.map_ok,
                    "job_count": result.job_count,
                    "eligible": result.eligible,
                    "reasons": ";".join(result.reasons),
                }
            )


def default_missing_report_path(platform: PlatformType) -> Path:
    return Path(f"reports/{platform.value}_missing_identifiers.csv")


def default_verification_report_path(platform: PlatformType) -> Path:
    return Path(f"reports/{platform.value}_verification_report.csv")


def build_platform_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--platform",
        required=True,
        choices=platform_choices(),
        help="ATS platform to audit.",
    )
