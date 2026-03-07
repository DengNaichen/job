"""Build normalized alias tables from ESCO-like CSV/TSV exports."""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .normalization import normalize_skill_text

URI_COLUMNS = ("uri", "concepturi", "concept_uri", "skill_uri", "id")
PREFERRED_COLUMNS = (
    "preferredlabel",
    "preferred_label",
    "preferred term",
    "preferred_term",
    "label",
    "skill",
)
ALT_COLUMNS = (
    "altlabels",
    "alt_labels",
    "alternative_labels",
    "non_preferred_labels",
    "nonpreferredlabels",
    "alternativelabels",
)
LANG_COLUMNS = ("language", "lang", "language_code")

# ESCO altLabels are often newline-delimited in a single cell.
ALT_SPLIT_PATTERN = re.compile(r"(?:\r?\n|[|;,])+")


@dataclass(frozen=True)
class AliasBuildStats:
    """Output stats for alias table building."""

    input_rows: int
    alias_rows_written: int
    rows_skipped_missing_required: int
    output_path: Path


def _detect_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as handle:
        sample = handle.read(4096)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        return dialect.delimiter
    except csv.Error:
        return ","


def _find_column(fieldnames: list[str], candidates: Iterable[str]) -> str | None:
    lowered_to_original = {name.strip().lower(): name for name in fieldnames}
    for candidate in candidates:
        if candidate in lowered_to_original:
            return lowered_to_original[candidate]
    return None


def _expand_labels(preferred_label: str, alt_labels_raw: str | None) -> list[str]:
    labels: list[str] = []
    if preferred_label.strip():
        labels.append(preferred_label)
    if alt_labels_raw:
        for token in ALT_SPLIT_PATTERN.split(alt_labels_raw):
            cleaned = token.strip()
            if cleaned:
                labels.append(cleaned)

    # Lightweight shorthand for labels like "Python (computer programming)" -> "Python".
    compact_preferred = re.sub(r"\s*\([^)]*\)\s*", " ", preferred_label).strip()
    if compact_preferred and compact_preferred != preferred_label:
        labels.append(compact_preferred)

    seen: set[str] = set()
    deduped: list[str] = []
    for label in labels:
        key = normalize_skill_text(label)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(label)
    return deduped


def build_alias_table(*, input_path: Path, output_path: Path, language: str) -> AliasBuildStats:
    """Build a normalized alias table from an ESCO-like input export."""
    delimiter = _detect_delimiter(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    read_rows = 0
    written_rows = 0
    skipped_rows = 0
    seen_pairs: set[tuple[str, str]] = set()

    with input_path.open("r", encoding="utf-8", newline="") as in_handle:
        reader = csv.DictReader(in_handle, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError("Input file has no header row")

        uri_col = _find_column(reader.fieldnames, URI_COLUMNS)
        preferred_col = _find_column(reader.fieldnames, PREFERRED_COLUMNS)
        alt_col = _find_column(reader.fieldnames, ALT_COLUMNS)
        lang_col = _find_column(reader.fieldnames, LANG_COLUMNS)

        if uri_col is None:
            raise ValueError(f"Could not find URI column. Tried: {URI_COLUMNS}")
        if preferred_col is None:
            raise ValueError(f"Could not find preferred label column. Tried: {PREFERRED_COLUMNS}")

        with output_path.open("w", encoding="utf-8", newline="") as out_handle:
            writer = csv.DictWriter(
                out_handle,
                fieldnames=[
                    "alias",
                    "canonical_uri",
                    "canonical_label",
                    "language",
                    "source",
                ],
            )
            writer.writeheader()

            for row in reader:
                read_rows += 1

                row_lang = normalize_skill_text(row.get(lang_col, "")) if lang_col else language
                if lang_col and row_lang and row_lang != normalize_skill_text(language):
                    continue

                uri = (row.get(uri_col) or "").strip()
                preferred_label = (row.get(preferred_col) or "").strip()
                alt_raw = (row.get(alt_col) or "").strip() if alt_col else ""

                if not uri or not preferred_label:
                    skipped_rows += 1
                    continue

                for label in _expand_labels(preferred_label, alt_raw):
                    alias = normalize_skill_text(label)
                    if not alias:
                        continue
                    pair = (alias, uri)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    writer.writerow(
                        {
                            "alias": alias,
                            "canonical_uri": uri,
                            "canonical_label": preferred_label,
                            "language": language,
                            "source": "esco",
                        }
                    )
                    written_rows += 1

    return AliasBuildStats(
        input_rows=read_rows,
        alias_rows_written=written_rows,
        rows_skipped_missing_required=skipped_rows,
        output_path=output_path,
    )


__all__ = ["AliasBuildStats", "build_alias_table"]

