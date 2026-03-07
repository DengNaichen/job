"""Exact-alias skills alignment helpers."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .normalization import normalize_skill_text

ALIGNED_SKILL_FIELDNAMES = [
    "raw_skill",
    "normalized_skill",
    "canonical_uri",
    "canonical_label",
    "status",
]


@dataclass(frozen=True)
class AlignmentStats:
    """Output stats for skills alignment runs."""

    input_skills: int
    mapped: int
    unknown: int
    output_path: Path


def load_alias_table(path: Path) -> dict[str, tuple[str, str]]:
    """Load alias table as normalized alias -> canonical tuple."""
    table: dict[str, tuple[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"alias", "canonical_uri", "canonical_label"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Alias table missing required columns: {sorted(missing)}")

        for row in reader:
            alias = normalize_skill_text(row.get("alias"))
            uri = (row.get("canonical_uri") or "").strip()
            label = (row.get("canonical_label") or "").strip()
            if not alias or not uri:
                continue
            # First-hit wins to keep behavior deterministic if collisions exist.
            table.setdefault(alias, (uri, label))
    return table


def read_raw_skills(path: Path) -> list[str]:
    """Read one raw skill per line from text input file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def align_skill_entries(
    raw_skills: Iterable[str],
    *,
    alias_map: dict[str, tuple[str, str]],
) -> tuple[list[dict[str, str]], int, int]:
    """Align raw skills with exact normalized alias matching."""
    rows: list[dict[str, str]] = []
    mapped = 0
    unknown = 0

    for raw in raw_skills:
        normalized = normalize_skill_text(raw)
        entry = alias_map.get(normalized)
        if entry is None:
            rows.append(
                {
                    "raw_skill": raw,
                    "normalized_skill": normalized,
                    "canonical_uri": "",
                    "canonical_label": "",
                    "status": "unknown",
                }
            )
            unknown += 1
            continue

        canonical_uri, canonical_label = entry
        rows.append(
            {
                "raw_skill": raw,
                "normalized_skill": normalized,
                "canonical_uri": canonical_uri,
                "canonical_label": canonical_label,
                "status": "mapped",
            }
        )
        mapped += 1

    return rows, mapped, unknown


def write_aligned_skill_entries(rows: Iterable[dict[str, str]], *, output_path: Path) -> None:
    """Write aligned skill rows as CSV output."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ALIGNED_SKILL_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def align_skills_from_files(
    *,
    alias_table_path: Path,
    alias_patch_path: Path | None,
    raw_skills_path: Path,
    output_path: Path,
) -> AlignmentStats:
    """Align raw skills from text file and persist aligned CSV output."""
    alias_map = load_alias_table(alias_table_path)
    if alias_patch_path is not None:
        patch_map = load_alias_table(alias_patch_path)
        # Patch aliases intentionally override base aliases for local tuning.
        alias_map.update(patch_map)

    raw_skills = read_raw_skills(raw_skills_path)
    rows, mapped, unknown = align_skill_entries(raw_skills, alias_map=alias_map)
    write_aligned_skill_entries(rows, output_path=output_path)
    return AlignmentStats(
        input_skills=len(raw_skills),
        mapped=mapped,
        unknown=unknown,
        output_path=output_path,
    )


__all__ = [
    "ALIGNED_SKILL_FIELDNAMES",
    "AlignmentStats",
    "align_skill_entries",
    "align_skills_from_files",
    "load_alias_table",
    "read_raw_skills",
    "write_aligned_skill_entries",
]

