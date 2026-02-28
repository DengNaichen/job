#!/usr/bin/env python3
"""Verify missing Greenhouse identifiers and write a CSV report."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.services.stapply_greenhouse_audit import (
    read_candidates_csv,
    verify_greenhouse_candidates,
    write_verification_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify Greenhouse identifiers from a CSV and write a report.",
    )
    parser.add_argument(
        "--input",
        default="reports/greenhouse_missing_identifiers.csv",
        help="CSV exported by export_missing_greenhouse_identifiers.py.",
    )
    parser.add_argument(
        "--output",
        default="reports/greenhouse_verification_report.csv",
        help="CSV path to write the verification report.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Verify only the first N identifiers from the input CSV.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent Greenhouse verification requests.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=20.0,
        help="Per-request timeout for the Greenhouse API.",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise SystemExit(f"Input CSV does not exist: {input_path}")

    output_path = Path(args.output).expanduser().resolve()
    candidates = read_candidates_csv(input_path)
    results, summary = await verify_greenhouse_candidates(
        candidates,
        concurrency=args.concurrency,
        limit=args.limit,
        timeout_seconds=args.timeout_seconds,
    )
    write_verification_csv(output_path, results)

    print(f"input={input_path}")
    print(f"output={output_path}")
    print(f"input_candidates={len(candidates)}")
    print(f"checked={summary.checked}")
    print(f"eligible={summary.eligible}")
    print(f"invalid_name={summary.invalid_name}")
    print(f"invalid_identifier={summary.invalid_identifier}")
    print(f"fetch_failed={summary.fetch_failed}")
    print(f"empty_results={summary.empty_results}")
    print(f"sample_map_failed={summary.sample_map_failed}")

    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run(build_parser().parse_args())))


if __name__ == "__main__":
    main()
