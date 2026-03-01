#!/usr/bin/env python3
"""Offline match experiment script wrapper."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from app.schemas.match import CandidateProfile, MatchRequest
from app.services.match_service import (
    CandidateProfileValidationError,
    MatchExperimentService,
    MatchServiceError,
    validate_candidate_profile,
)

DEFAULT_USER_JSON = str(Path(__file__).resolve().parents[1] / "app" / "schemas" / "user.json")


def load_user_json_as_candidate_profile(user_path: Path) -> CandidateProfile:
    if not user_path.exists():
        raise FileNotFoundError(f"user_json not found: {user_path}")

    raw_candidate = json.loads(user_path.read_text(encoding="utf-8"))
    return validate_candidate_profile(raw_candidate)


def build_match_request_from_args(
    candidate: CandidateProfile,
    *,
    args: argparse.Namespace,
    user_path: Path,
) -> MatchRequest:
    return MatchRequest(
        candidate=candidate,
        top_k=args.top_k,
        top_n=args.top_n,
        needs_sponsorship_override=args.needs_sponsorship,
        experience_buffer_years=args.experience_buffer_years,
        min_cosine_score=args.min_cosine_score,
        enable_llm_rerank=args.enable_llm_rerank,
        llm_top_n=args.llm_top_n,
        llm_concurrency=args.llm_concurrency,
        max_user_chars=args.max_user_chars,
        user_json=str(user_path),
    )


async def run(args: argparse.Namespace) -> None:
    user_path = Path(args.user_json)
    candidate = load_user_json_as_candidate_profile(user_path)
    request = build_match_request_from_args(candidate, args=args, user_path=user_path)
    response = await MatchExperimentService().run(request)
    output_json = json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output_json, encoding="utf-8")
        print(f"saved: {output_path}")
    else:
        print(output_json)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run offline match experiment")
    parser.add_argument("--user-json", default=DEFAULT_USER_JSON, help="Path to user profile json")
    parser.add_argument("--top-k", type=int, default=200, help="Vector recall candidate size")
    parser.add_argument("--top-n", type=int, default=50, help="Final result size")
    parser.add_argument(
        "--needs-sponsorship",
        choices=["auto", "true", "false"],
        default="auto",
        help="Override user sponsorship need; default auto from workAuthorization",
    )
    parser.add_argument(
        "--experience-buffer-years",
        type=int,
        default=1,
        help="Allow this many years of experience gap before hard filtering",
    )
    parser.add_argument(
        "--min-cosine-score",
        type=float,
        default=0.48,
        help="Minimum cosine similarity required after vector recall",
    )
    parser.add_argument(
        "--enable-llm-rerank",
        action="store_true",
        help="Enable top-N LLM recommendation and light reranking",
    )
    parser.add_argument(
        "--llm-top-n",
        type=int,
        default=10,
        help="Top-N deterministic results sent to the LLM recommendation layer",
    )
    parser.add_argument(
        "--llm-concurrency",
        type=int,
        default=3,
        help="Concurrent LLM requests for top-N recommendation rerank",
    )
    parser.add_argument(
        "--max-user-chars", type=int, default=12000, help="Max chars for user embedding text"
    )
    parser.add_argument("--output", default=None, help="Optional output JSON file path")
    return parser.parse_args()


def main() -> None:
    try:
        asyncio.run(run(parse_args()))
    except (CandidateProfileValidationError, MatchServiceError) as exc:
        raise SystemExit(exc.message) from exc


if __name__ == "__main__":
    main()
