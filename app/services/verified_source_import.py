from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import engine
from app.models import PlatformType, Source, normalize_name


@dataclass(frozen=True)
class EligibleSourceCandidate:
    platform: PlatformType
    name: str
    identifier: str
    url: str
    job_count: int


@dataclass(frozen=True)
class OverlapResolution:
    identifier: str
    winner_platform: PlatformType
    reason: str


OVERLAP_RESOLUTIONS: dict[str, OverlapResolution] = {
    "aleph": OverlapResolution("aleph", PlatformType.LEVER, "much_higher_job_count_equal_sample_richness"),
    "antimetal": OverlapResolution("antimetal", PlatformType.ASHBY, "higher_job_count_and_richer_sample"),
    "baton": OverlapResolution("baton", PlatformType.ASHBY, "near_tie_prefer_richer_sample"),
    "extend": OverlapResolution("extend", PlatformType.ASHBY, "near_tie_prefer_richer_sample"),
    "finch": OverlapResolution("finch", PlatformType.LEVER, "much_higher_job_count"),
    "found": OverlapResolution("found", PlatformType.ASHBY, "higher_job_count_and_richer_sample"),
    "glide": OverlapResolution("glide", PlatformType.LEVER, "highest_job_count_equal_top_sample_richness"),
    "harmonic": OverlapResolution("harmonic", PlatformType.GREENHOUSE, "materially_higher_job_count_with_acceptable_sample_quality"),
    "hive": OverlapResolution("hive", PlatformType.LEVER, "much_higher_job_count_and_richer_sample"),
    "hook": OverlapResolution("hook", PlatformType.ASHBY, "near_tie_prefer_richer_sample"),
    "knock": OverlapResolution("knock", PlatformType.ASHBY, "equal_job_count_prefer_richer_sample"),
    "known": OverlapResolution("known", PlatformType.GREENHOUSE, "materially_higher_job_count_with_acceptable_sample_quality"),
    "latitude": OverlapResolution("latitude", PlatformType.GREENHOUSE, "much_higher_job_count"),
    "ledger": OverlapResolution("ledger", PlatformType.ASHBY, "much_higher_job_count_and_richer_sample"),
    "range": OverlapResolution("range", PlatformType.ASHBY, "much_higher_job_count_and_richer_sample"),
    "reach": OverlapResolution("reach", PlatformType.ASHBY, "equal_job_count_prefer_richer_sample"),
    "sesame": OverlapResolution("sesame", PlatformType.ASHBY, "much_higher_job_count_and_richer_sample"),
    "stackblitz": OverlapResolution("stackblitz", PlatformType.GREENHOUSE, "much_higher_job_count"),
}


def default_verification_report_paths() -> list[Path]:
    return [
        Path("reports/greenhouse_verification_report.csv"),
        Path("reports/lever_verification_report.csv"),
        Path("reports/ashby_verification_report.csv"),
        Path("reports/smartrecruiters_verification_report.csv"),
    ]


def load_eligible_candidates(paths: list[Path]) -> list[EligibleSourceCandidate]:
    candidates: list[EligibleSourceCandidate] = []
    for path in paths:
        inferred_platform = PlatformType(path.name.split("_", 1)[0])
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("eligible") != "True":
                    continue
                platform_value = str(row.get("platform") or inferred_platform.value).strip()
                candidates.append(
                    EligibleSourceCandidate(
                        platform=PlatformType(platform_value),
                        name=str(row["name"]).strip(),
                        identifier=str(row["identifier"]).strip(),
                        url=str(row["url"]).strip(),
                        job_count=int(row["job_count"]),
                    )
                )
    return candidates


def resolve_overlap_candidates(
    candidates: list[EligibleSourceCandidate],
) -> tuple[list[EligibleSourceCandidate], list[dict[str, str | int]]]:
    by_identifier: dict[str, list[EligibleSourceCandidate]] = {}
    for candidate in candidates:
        by_identifier.setdefault(candidate.identifier.casefold(), []).append(candidate)

    selected: list[EligibleSourceCandidate] = []
    overlap_rows: list[dict[str, str | int]] = []

    for identifier_key, group in sorted(by_identifier.items()):
        if len(group) == 1:
            selected.append(group[0])
            continue

        resolution = OVERLAP_RESOLUTIONS.get(identifier_key)
        if resolution is None:
            raise ValueError(f"Missing overlap resolution for identifier: {identifier_key}")

        winner = next(
            (candidate for candidate in group if candidate.platform == resolution.winner_platform),
            None,
        )
        if winner is None:
            raise ValueError(
                f"Resolved winner {resolution.winner_platform.value} not present for identifier {identifier_key}"
            )

        selected.append(winner)
        for candidate in sorted(group, key=lambda item: (item.platform.value, item.identifier.casefold())):
            overlap_rows.append(
                {
                    "identifier": candidate.identifier,
                    "platform": candidate.platform.value,
                    "name": candidate.name,
                    "job_count": candidate.job_count,
                    "selected": "True" if candidate == winner else "False",
                    "selection_reason": resolution.reason,
                    "url": candidate.url,
                }
            )

    selected.sort(key=lambda item: (item.platform.value, item.identifier.casefold()))
    return selected, overlap_rows


def write_candidates_csv(path: Path, candidates: list[EligibleSourceCandidate]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["platform", "name", "identifier", "url", "job_count"],
        )
        writer.writeheader()
        for candidate in candidates:
            writer.writerow(
                {
                    "platform": candidate.platform.value,
                    "name": candidate.name,
                    "identifier": candidate.identifier,
                    "url": candidate.url,
                    "job_count": candidate.job_count,
                }
            )


def write_overlap_resolution_csv(path: Path, rows: list[dict[str, str | int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "identifier",
                "platform",
                "name",
                "job_count",
                "selected",
                "selection_reason",
                "url",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


async def import_candidates(
    candidates: list[EligibleSourceCandidate],
    *,
    notes_prefix: str,
) -> tuple[int, int]:
    async with AsyncSession(engine) as session:
        existing_rows = await session.exec(select(Source))
        existing_sources = list(existing_rows.all())
        existing_by_identifier = {
            (
                source.platform.value if isinstance(source.platform, PlatformType) else str(source.platform).strip(),
                source.identifier.strip().casefold(),
            ): source
            for source in existing_sources
        }
        existing_by_name = {
            (
                source.platform.value if isinstance(source.platform, PlatformType) else str(source.platform).strip(),
                normalize_name(source.name),
            ): source
            for source in existing_sources
        }

        inserted = 0
        skipped = 0
        for candidate in candidates:
            identifier_key = (candidate.platform.value, candidate.identifier.strip().casefold())
            if identifier_key in existing_by_identifier:
                skipped += 1
                continue

            name_key = (candidate.platform.value, normalize_name(candidate.name))
            if name_key in existing_by_name:
                skipped += 1
                continue

            source = Source(
                name=candidate.name,
                name_normalized=normalize_name(candidate.name),
                platform=candidate.platform,
                identifier=candidate.identifier,
                enabled=True,
                notes=f"{notes_prefix} ({candidate.url})",
            )
            session.add(source)
            existing_by_identifier[identifier_key] = source
            existing_by_name[name_key] = source
            inserted += 1

        await session.commit()
        return inserted, skipped
