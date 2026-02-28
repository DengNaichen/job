#!/usr/bin/env python3
"""Verify ATS identifiers from a CSV and write a report."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.services.stapply_platform_audit import (
    PLATFORM_AUDIT_CONFIGS,
    build_platform_argument,
    default_missing_report_path,
    default_verification_report_path,
    parse_platform,
    read_candidates_csv,
    verify_candidates,
    write_verification_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify ATS identifiers from a CSV and write a report.",
    )
    build_platform_argument(parser)
    parser.add_argument(
        "--input",
        default=None,
        help="CSV exported by export_missing_ats_identifiers.py. Defaults to reports/<platform>_missing_identifiers.csv.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="CSV path to write the verification report. Defaults to reports/<platform>_verification_report.csv.",
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
        default=None,
        help="Concurrent verification requests. Defaults to a platform-specific value.",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    platform = parse_platform(args.platform)
    input_path = Path(args.input).expanduser().resolve() if args.input else default_missing_report_path(platform).resolve()
    if not input_path.exists():
        raise SystemExit(f"Input CSV does not exist: {input_path}")

    output_path = Path(args.output).expanduser().resolve() if args.output else default_verification_report_path(platform).resolve()
    candidates = read_candidates_csv(input_path)
    candidates = [candidate for candidate in candidates if candidate.platform == platform]
    concurrency = args.concurrency or PLATFORM_AUDIT_CONFIGS[platform].default_verify_concurrency

    results, summary = await verify_candidates(
        candidates,
        concurrency=concurrency,
        limit=args.limit,
    )
    write_verification_csv(output_path, results)

    print(f"platform={platform.value}")
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
