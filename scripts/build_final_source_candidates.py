#!/usr/bin/env python3
"""Build the final source candidate CSV after cross-platform overlap resolution."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.services.verified_source_import import (
    default_verification_report_paths,
    load_eligible_candidates,
    resolve_overlap_candidates,
    write_candidates_csv,
    write_overlap_resolution_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a final import candidate CSV from verified ATS reports.",
    )
    parser.add_argument(
        "--output",
        default="reports/final_source_import_candidates.csv",
        help="Path to the final import candidate CSV.",
    )
    parser.add_argument(
        "--overlap-output",
        default="reports/cross_platform_overlap_resolution.csv",
        help="Path to the overlap resolution CSV.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report_paths = [path.resolve() for path in default_verification_report_paths()]
    candidates = load_eligible_candidates(report_paths)
    selected, overlap_rows = resolve_overlap_candidates(candidates)

    output_path = Path(args.output).expanduser().resolve()
    overlap_output_path = Path(args.overlap_output).expanduser().resolve()
    write_candidates_csv(output_path, selected)
    write_overlap_resolution_csv(overlap_output_path, overlap_rows)

    print(f"reports={','.join(str(path) for path in report_paths)}")
    print(f"output={output_path}")
    print(f"overlap_output={overlap_output_path}")
    print(f"eligible_total={len(candidates)}")
    print(f"final_selected={len(selected)}")
    print(f"dropped_due_to_cross_platform_overlap={len(candidates) - len(selected)}")


if __name__ == "__main__":
    main()
