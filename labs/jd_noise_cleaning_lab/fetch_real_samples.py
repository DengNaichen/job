#!/usr/bin/env python3
"""Fetch real JD samples from the configured database and run the lab on them."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings
from labs.jd_noise_cleaning_lab.run import (
    build_embedding_text,
    load_input,
    select_evidence,
    split_into_sections,
    summarize_blocks,
)

BASE_QUERY = """
    SELECT
        j.id,
        j.title,
        j.description_plain,
        j.structured_jd,
        j.structured_jd_version,
        j.updated_at,
        s.platform::text AS source_platform,
        s.identifier AS source_identifier
    FROM job j
    JOIN sources s ON s.id = j.source_id
    WHERE j.description_plain IS NOT NULL
      AND length(trim(j.description_plain)) > 600
      AND j.structured_jd IS NOT NULL
      AND COALESCE(j.structured_jd_version, 0) >= 3
      AND j.status = 'open'
    {order_clause}
    LIMIT $1
"""


async def fetch_rows(limit: int, *, randomize: bool) -> list[asyncpg.Record]:
    dsn = get_settings().database_url
    conn = await asyncpg.connect(dsn=dsn)
    try:
        order_clause = "ORDER BY random()" if randomize else "ORDER BY j.updated_at DESC"
        query = BASE_QUERY.format(order_clause=order_clause)
        return await conn.fetch(query, limit)
    finally:
        await conn.close()


def write_job_payload(row: asyncpg.Record, directory: Path, index: int) -> Path:
    structured_jd = row["structured_jd"] or {}
    if isinstance(structured_jd, str):
        structured_jd = json.loads(structured_jd)

    payload = {
        "job_id": row["id"],
        "source": f"{row['source_platform']}:{row['source_identifier']}",
        "title": row["title"],
        "description": row["description_plain"],
        "structured_jd": structured_jd,
    }
    path = directory / f"real_job_{index:02d}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_lab_on_payload(path: Path, max_chars: int) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    title, description, structured = load_input(path)
    blocks = split_into_sections(description)
    evidence = select_evidence(blocks, structured)
    embedding_text = build_embedding_text(
        title=title,
        structured=structured,
        evidence=evidence,
        max_chars=max_chars,
    )
    return {
        "job_id": payload["job_id"],
        "source": payload["source"],
        "title": title,
        "original_chars": len(description),
        "section_summary": summarize_blocks(blocks, structured),
        "selected_evidence": evidence,
        "embedding_text_chars": len(embedding_text),
        "embedding_text": embedding_text,
        "structured_jd": structured.model_dump(mode="json"),
    }


def build_summary(reports: list[dict[str, object]]) -> dict[str, object]:
    label_counts: Counter[str] = Counter()
    dropped_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    dropped_jobs: list[dict[str, object]] = []

    for report in reports:
        source = str(report["source"])
        source_counts[source] += 1
        dropped_labels: list[str] = []
        for item in report["section_summary"]:  # type: ignore[index]
            label = str(item["label"])
            label_counts[label] += 1
            if item["decision"] == "drop":
                dropped_counts[label] += 1
                dropped_labels.append(label)
        dropped_jobs.append(
            {
                "job_id": report["job_id"],
                "title": report["title"],
                "source": source,
                "dropped_labels": dropped_labels,
                "original_chars": report["original_chars"],
                "embedding_text_chars": report["embedding_text_chars"],
            }
        )

    return {
        "sample_count": len(reports),
        "label_counts": dict(label_counts),
        "dropped_counts": dict(dropped_counts),
        "source_counts": dict(source_counts),
        "jobs": dropped_jobs,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch real JD samples and run the lab")
    parser.add_argument("--limit", type=int, default=10, help="Number of jobs to fetch")
    parser.add_argument(
        "--random",
        action="store_true",
        help="Sample randomly instead of taking the most recently updated jobs",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "real_samples"),
        help="Directory for fetched sample payloads and outputs",
    )
    parser.add_argument("--max-chars", type=int, default=2200, help="Max embedding text chars")
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = await fetch_rows(max(1, args.limit), randomize=bool(args.random))
    manifest: list[dict[str, object]] = []
    reports: list[dict[str, object]] = []

    for index, row in enumerate(rows, start=1):
        payload_path = write_job_payload(row, output_dir, index)
        report = run_lab_on_payload(payload_path, max_chars=max(200, args.max_chars))
        output_path = output_dir / f"real_job_{index:02d}_output.json"
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        reports.append(report)
        manifest.append(
            {
                "job_id": row["id"],
                "source": f"{row['source_platform']}:{row['source_identifier']}",
                "title": row["title"],
                "payload_file": payload_path.name,
                "output_file": output_path.name,
            }
        )

    summary_path = output_dir / "manifest.json"
    summary_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    experiment_summary_path = output_dir / "summary.json"
    experiment_summary_path.write_text(
        json.dumps(build_summary(reports), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"saved {len(manifest)} samples to {output_dir}")
    print(f"manifest: {summary_path}")
    print(f"summary: {experiment_summary_path}")


def main() -> None:
    asyncio.run(main_async(parse_args()))


if __name__ == "__main__":
    main()
