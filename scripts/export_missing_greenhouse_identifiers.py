#!/usr/bin/env python3
"""Export Greenhouse identifiers that exist in stapply but not in the local sources table."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.services.stapply_greenhouse_audit import (
    default_stapply_clone_path,
    find_missing_greenhouse_candidates,
    load_greenhouse_candidates,
    write_candidates_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export missing Greenhouse identifiers from stapply-ai/ats-scrapers.",
    )
    parser.add_argument(
        "--clone-path",
        default=str(default_stapply_clone_path()) if default_stapply_clone_path() else None,
        help="Path to a local clone of stapply-ai/ats-scrapers.",
    )
    parser.add_argument(
        "--output",
        default="reports/greenhouse_missing_identifiers.csv",
        help="CSV path to write missing Greenhouse identifiers.",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    if not args.clone_path:
        raise SystemExit("Missing --clone-path. Clone stapply-ai/ats-scrapers locally first.")

    clone_path = Path(args.clone_path).expanduser().resolve()
    if not clone_path.exists():
        raise SystemExit(f"Clone path does not exist: {clone_path}")

    output_path = Path(args.output).expanduser().resolve()
    candidates, summary = load_greenhouse_candidates(clone_path)
    missing = await find_missing_greenhouse_candidates(candidates, summary)
    write_candidates_csv(output_path, missing)

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
