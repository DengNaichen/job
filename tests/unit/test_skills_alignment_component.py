"""Unit tests for skills alignment domain component."""

from __future__ import annotations

import csv
from pathlib import Path

from app.services.domain.skills_alignment import (
    align_skills_from_files,
    build_alias_table,
    load_alias_table,
    normalize_skill_text,
)


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_normalize_skill_text() -> None:
    assert normalize_skill_text("  Node.js / TypeScript  ") == "node js typescript"
    assert normalize_skill_text("C++") == "c++"
    assert normalize_skill_text("A&B") == "a and b"
    assert normalize_skill_text(None) == ""


def test_build_alias_table_and_load(tmp_path: Path) -> None:
    source_path = tmp_path / "skills.csv"
    out_path = tmp_path / "alias.csv"
    _write(
        source_path,
        "\n".join(
            [
                "uri,preferredLabel,altLabels,language",
                "http://x/1,Python (programming),python|py,en",
                "http://x/2,JavaScript,js|node js,en",
                "http://x/3,Ignored Skill,ignored,fr",
                ",Missing URI,foo,en",
            ]
        ),
    )

    stats = build_alias_table(input_path=source_path, output_path=out_path, language="en")

    assert stats.input_rows == 4
    assert stats.rows_skipped_missing_required == 1
    assert stats.alias_rows_written >= 5

    alias_map = load_alias_table(out_path)
    assert alias_map["python"][0] == "http://x/1"
    assert alias_map["py"][0] == "http://x/1"
    assert alias_map["javascript"][0] == "http://x/2"
    assert alias_map["js"][0] == "http://x/2"
    assert "ignored" not in alias_map


def test_align_skills_from_files_patch_override(tmp_path: Path) -> None:
    base_alias = tmp_path / "base.csv"
    patch_alias = tmp_path / "patch.csv"
    raw = tmp_path / "raw.txt"
    out = tmp_path / "out.csv"

    _write(
        base_alias,
        "\n".join(
            [
                "alias,canonical_uri,canonical_label,language,source",
                "python,http://x/base-python,Python,en,base",
                "go,http://x/go,Go,en,base",
            ]
        ),
    )
    _write(
        patch_alias,
        "\n".join(
            [
                "alias,canonical_uri,canonical_label,language,source",
                "python,http://x/patch-python,Python,en,patch",
            ]
        ),
    )
    _write(raw, "Python\ngo\nRust\n")

    stats = align_skills_from_files(
        alias_table_path=base_alias,
        alias_patch_path=patch_alias,
        raw_skills_path=raw,
        output_path=out,
    )

    assert stats.input_skills == 3
    assert stats.mapped == 2
    assert stats.unknown == 1

    with out.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    by_raw = {row["raw_skill"]: row for row in rows}
    assert by_raw["Python"]["status"] == "mapped"
    assert by_raw["Python"]["canonical_uri"] == "http://x/patch-python"
    assert by_raw["go"]["status"] == "mapped"
    assert by_raw["Rust"]["status"] == "unknown"

