from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import engine
from app.ingest.fetchers.greenhouse import GreenhouseFetcher
from app.ingest.mappers.greenhouse import GreenhouseMapper
from app.models import PlatformType, Source, normalize_name


GREENHOUSE_COMPANIES_CSV = Path("greenhouse/greenhouse_companies.csv")


@dataclass(frozen=True)
class GreenhouseCandidate:
    name: str
    identifier: str
    url: str


@dataclass
class GreenhouseCandidateSummary:
    csv_rows: int = 0
    valid_candidates: int = 0
    duplicate_identifiers: int = 0
    duplicate_names: int = 0
    existing_in_db: int = 0
    name_collisions: int = 0
    missing_in_db: int = 0


@dataclass
class GreenhouseVerificationResult:
    candidate: GreenhouseCandidate
    name_ok: bool
    identifier_ok: bool
    fetch_ok: bool
    map_ok: bool | None
    job_count: int
    eligible: bool
    reasons: list[str] = field(default_factory=list)


@dataclass
class GreenhouseVerificationSummary:
    checked: int = 0
    eligible: int = 0
    invalid_name: int = 0
    invalid_identifier: int = 0
    fetch_failed: int = 0
    empty_results: int = 0
    sample_map_failed: int = 0


def default_stapply_clone_path() -> Path | None:
    marker = Path("/tmp/ats-scrapers-path.txt")
    if not marker.exists():
        return None
    candidate = Path(marker.read_text(encoding="utf-8").strip())
    return candidate if candidate.exists() else None


def greenhouse_companies_csv_path(clone_path: Path) -> Path:
    return clone_path / GREENHOUSE_COMPANIES_CSV


def extract_greenhouse_identifier(url: str) -> str | None:
    parsed = urlparse(url.strip())
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return None
    identifier = path_parts[0].strip()
    return identifier or None


def load_greenhouse_candidates(
    clone_path: Path,
) -> tuple[list[GreenhouseCandidate], GreenhouseCandidateSummary]:
    candidates: list[GreenhouseCandidate] = []
    summary = GreenhouseCandidateSummary()
    seen_identifiers: set[str] = set()
    seen_names: set[str] = set()

    csv_path = greenhouse_companies_csv_path(clone_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Missing Greenhouse CSV: {csv_path}")

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            summary.csv_rows += 1
            name = str(row.get("name") or "").strip()
            url = str(row.get("url") or "").strip()
            identifier = (extract_greenhouse_identifier(url) or "").strip()
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
                GreenhouseCandidate(
                    name=name,
                    identifier=identifier,
                    url=url,
                )
            )

    return candidates, summary


async def load_existing_greenhouse_sources() -> list[Source]:
    async with AsyncSession(engine) as session:
        rows = await session.exec(select(Source).where(Source.platform == PlatformType.GREENHOUSE))
        return list(rows.all())


def filter_missing_greenhouse_candidates(
    candidates: list[GreenhouseCandidate],
    existing_sources: list[Source],
    summary: GreenhouseCandidateSummary,
) -> list[GreenhouseCandidate]:
    existing_identifiers = {source.identifier.strip().casefold() for source in existing_sources}
    existing_names = {normalize_name(source.name) for source in existing_sources}

    missing: list[GreenhouseCandidate] = []
    for candidate in candidates:
        identifier_key = candidate.identifier.strip().casefold()
        if identifier_key in existing_identifiers:
            summary.existing_in_db += 1
            continue

        name_key = normalize_name(candidate.name)
        if name_key in existing_names:
            summary.name_collisions += 1
            continue

        summary.missing_in_db += 1
        missing.append(candidate)

    return missing


async def find_missing_greenhouse_candidates(
    candidates: list[GreenhouseCandidate],
    summary: GreenhouseCandidateSummary,
) -> list[GreenhouseCandidate]:
    existing_sources = await load_existing_greenhouse_sources()
    return filter_missing_greenhouse_candidates(candidates, existing_sources, summary)


def validate_candidate_name(candidate: GreenhouseCandidate) -> list[str]:
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


def validate_candidate_identifier(candidate: GreenhouseCandidate) -> list[str]:
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


async def verify_greenhouse_candidate(
    candidate: GreenhouseCandidate,
    *,
    client: httpx.AsyncClient,
    mapper: GreenhouseMapper | None = None,
) -> GreenhouseVerificationResult:
    reasons: list[str] = []
    mapper = mapper or GreenhouseMapper()

    name_reasons = validate_candidate_name(candidate)
    identifier_reasons = validate_candidate_identifier(candidate)
    reasons.extend(name_reasons)
    reasons.extend(identifier_reasons)

    name_ok = not name_reasons
    identifier_ok = not identifier_reasons
    if not identifier_ok:
        return GreenhouseVerificationResult(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=False,
            fetch_ok=False,
            map_ok=None,
            job_count=0,
            eligible=False,
            reasons=reasons,
        )

    try:
        response = await client.get(
            f"{GreenhouseFetcher.BASE_URL}/{candidate.identifier}/jobs",
            params={"content": "false"},
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        reasons.append(f"http_status:{exc.response.status_code}")
        return GreenhouseVerificationResult(
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
        return GreenhouseVerificationResult(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=True,
            fetch_ok=False,
            map_ok=None,
            job_count=0,
            eligible=False,
            reasons=reasons,
        )

    raw_jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    if not isinstance(raw_jobs, list):
        raw_jobs = []
    if not raw_jobs:
        reasons.append("no_jobs_returned")
        return GreenhouseVerificationResult(
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
        return GreenhouseVerificationResult(
            candidate=candidate,
            name_ok=name_ok,
            identifier_ok=True,
            fetch_ok=True,
            map_ok=False,
            job_count=len(raw_jobs),
            eligible=False,
            reasons=reasons,
        )

    return GreenhouseVerificationResult(
        candidate=candidate,
        name_ok=name_ok,
        identifier_ok=True,
        fetch_ok=True,
        map_ok=True,
        job_count=len(raw_jobs),
        eligible=name_ok,
        reasons=reasons,
    )


async def verify_greenhouse_candidates(
    candidates: list[GreenhouseCandidate],
    *,
    concurrency: int = 10,
    limit: int | None = None,
    timeout_seconds: float = 20.0,
) -> tuple[list[GreenhouseVerificationResult], GreenhouseVerificationSummary]:
    selected = candidates[:limit] if limit is not None else candidates
    summary = GreenhouseVerificationSummary()
    if not selected:
        return [], summary

    semaphore = asyncio.Semaphore(concurrency)
    mapper = GreenhouseMapper()

    async with httpx.AsyncClient(
        timeout=timeout_seconds,
        headers={"User-Agent": "job-greenhouse-audit/1.0"},
    ) as client:

        async def run_one(candidate: GreenhouseCandidate) -> GreenhouseVerificationResult:
            async with semaphore:
                return await verify_greenhouse_candidate(candidate, client=client, mapper=mapper)

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


def read_candidates_csv(path: Path) -> list[GreenhouseCandidate]:
    candidates: list[GreenhouseCandidate] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            candidates.append(
                GreenhouseCandidate(
                    name=str(row.get("name") or "").strip(),
                    identifier=str(row.get("identifier") or "").strip(),
                    url=str(row.get("url") or "").strip(),
                )
            )
    return candidates


def write_candidates_csv(path: Path, candidates: list[GreenhouseCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "identifier", "url"])
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "name": candidate.name,
                    "identifier": candidate.identifier,
                    "url": candidate.url,
                }
            )


def write_verification_csv(path: Path, results: list[GreenhouseVerificationResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
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
