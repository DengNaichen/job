#!/usr/bin/env python3
"""Export identifiers that exist in stapply but not in the local sources table."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.services.stapply_platform_audit import (
    build_platform_argument,
    default_missing_report_path,
    default_stapply_clone_path,
    find_missing_candidates,
    parse_platform,
    write_candidates_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export missing ATS identifiers from stapply-ai/ats-scrapers.",
    )
    build_platform_argument(parser)
    parser.add_argument(
        "--clone-path",
        default=str(default_stapply_clone_path()) if default_stapply_clone_path() else None,
        help="Path to a local clone of stapply-ai/ats-scrapers.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="CSV path to write missing identifiers. Defaults to reports/<platform>_missing_identifiers.csv.",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    if not args.clone_path:
        raise SystemExit("Missing --clone-path. Clone stapply-ai/ats-scrapers locally first.")

    clone_path = Path(args.clone_path).expanduser().resolve()
    if not clone_path.exists():
        raise SystemExit(f"Clone path does not exist: {clone_path}")

    platform = parse_platform(args.platform)
    output_path = Path(args.output).expanduser().resolve() if args.output else default_missing_report_path(platform).resolve()

    missing, summary = await find_missing_candidates(clone_path, platform)
    write_candidates_csv(output_path, missing)

    print(f"platform={platform.value}")
    print(f"clone_path={clone_path}")
    print(f"output={output_path}")
    print(f"csv_rows={summary.csv_rows}")
    print(f"valid_candidates={summary.valid_candidates}")
    print(f"duplicate_identifiers={summary.duplicate_identifiers}")
    print(f"duplicate_names={summary.duplicate_names}")
    print(f"existing_in_db={summary.existing_in_db}")
    print(f"name_collisions={summary.name_collisions}")
    print(f"missing_in_db={summary.missing_in_db}")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run(build_parser().parse_args())))


if __name__ == "__main__":
    main()
