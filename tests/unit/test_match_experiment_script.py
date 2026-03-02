"""Unit tests for scripts/match_experiment.py."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import pytest

from app.schemas.match import MatchResponse


def _load_match_experiment_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "match_experiment.py"
    spec = importlib.util.spec_from_file_location("match_experiment_test_module", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover - importlib guard
        raise RuntimeError("Unable to load match_experiment.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_response(*, llm_enabled: bool) -> MatchResponse:
    return MatchResponse.model_validate(
        {
            "meta": {
                "user_json": "/tmp/user.json",
                "needs_sponsorship": False,
                "user_total_years_experience": 3,
                "user_degree_rank": 2,
                "user_skill_count": 2,
                "user_domain": "data_ai",
                "user_seniority": "mid",
                "top_k": 10,
                "top_n": 2,
                "sql_prefilter": {
                    "sponsorship_filter_applied": False,
                    "degree_filter_applied": True,
                    "preferred_country_code": None,
                    "user_degree_rank": 2,
                },
                "candidates_after_sql_prefilter": 2,
                "vector_threshold_summary": {
                    "enabled": True,
                    "input_count": 2,
                    "passed_count": 2,
                    "rejected_count": 0,
                    "min_cosine_score": 0.48,
                },
                "candidates_after_vector_threshold": 2,
                "candidates_before_hard_filter": 2,
                "candidates_after_hard_filter": 2,
                "hard_filter_summary": {
                    "enabled": True,
                    "input_count": 2,
                    "passed_count": 2,
                    "rejected_count": 0,
                    "rejected_by_reason": {
                        "sponsorship": 0,
                        "degree": 0,
                        "experience": 0,
                    },
                    "config": {
                        "needs_sponsorship": False,
                        "degree_filter_applied": False,
                        "experience_filter_applied": True,
                        "max_experience_gap": 1,
                    },
                },
                "llm_rerank_summary": {
                    "enabled": llm_enabled,
                    "window_size": 2 if llm_enabled else 0,
                    "attempted_count": 2 if llm_enabled else 0,
                    "succeeded_count": 2 if llm_enabled else 0,
                    "failed_count": 0,
                    "concurrency": 3 if llm_enabled else 0,
                    "reorder_applied": llm_enabled,
                    "adjustment_map": {
                        "strong_yes": 0.03,
                        "yes": 0.015,
                        "maybe": 0.0,
                        "stretch": -0.015,
                        "no": -0.03,
                    },
                    "token_usage": {
                        "total_requests": 2 if llm_enabled else 0,
                        "total_tokens": 42 if llm_enabled else 0,
                        "prompt_tokens": 30 if llm_enabled else 0,
                        "completion_tokens": 12 if llm_enabled else 0,
                        "by_model": {},
                    },
                },
                "results_returned": 2,
            },
            "results": [
                {
                    "job_id": "job-2" if llm_enabled else "job-1",
                    "source": "greenhouse",
                    "title": "Job 2" if llm_enabled else "Job 1",
                    "apply_url": "https://example.com/job-2"
                    if llm_enabled
                    else "https://example.com/job-1",
                    "location_text": "Toronto, ON",
                    "city": "Toronto",
                    "region": "Ontario",
                    "country_code": "CA",
                    "workplace_type": "hybrid",
                    "department": "Analytics",
                    "team": "BI",
                    "employment_type": "full-time",
                    "cosine_score": 0.88,
                    "skill_overlap_score": 1.0,
                    "domain_match_score": 1.0,
                    "seniority_match_score": 1.0,
                    "experience_gap": 0,
                    "education_gap": 0,
                    "penalties": {
                        "experience_penalty": 0.0,
                        "education_penalty": 0.0,
                        "total_penalty": 0.0,
                    },
                    "score_breakdown": {
                        "cosine_component": 0.616,
                        "skill_component": 0.15,
                        "domain_component": 0.1,
                        "seniority_component": 0.05,
                    },
                    "final_score": 0.916,
                    "llm_recommendation": "yes" if llm_enabled else None,
                    "llm_reasons": ["Relevant analytics experience"] if llm_enabled else [],
                    "llm_gaps": [],
                    "llm_resume_focus_points": ["Highlight dashboard ownership"]
                    if llm_enabled
                    else [],
                    "llm_adjustment": 0.015 if llm_enabled else 0.0,
                    "llm_adjusted_score": 0.931 if llm_enabled else 0.916,
                    "llm_enriched": llm_enabled,
                },
                {
                    "job_id": "job-1" if llm_enabled else "job-2",
                    "source": "greenhouse",
                    "title": "Job 1" if llm_enabled else "Job 2",
                    "apply_url": "https://example.com/job-1"
                    if llm_enabled
                    else "https://example.com/job-2",
                    "location_text": "Toronto, ON",
                    "city": "Toronto",
                    "region": "Ontario",
                    "country_code": "CA",
                    "workplace_type": "hybrid",
                    "department": "Analytics",
                    "team": "BI",
                    "employment_type": "full-time",
                    "cosine_score": 0.83,
                    "skill_overlap_score": 1.0,
                    "domain_match_score": 1.0,
                    "seniority_match_score": 1.0,
                    "experience_gap": 0,
                    "education_gap": 0,
                    "penalties": {
                        "experience_penalty": 0.0,
                        "education_penalty": 0.0,
                        "total_penalty": 0.0,
                    },
                    "score_breakdown": {
                        "cosine_component": 0.581,
                        "skill_component": 0.15,
                        "domain_component": 0.1,
                        "seniority_component": 0.05,
                    },
                    "final_score": 0.881,
                    "llm_recommendation": "yes" if llm_enabled else None,
                    "llm_reasons": ["Relevant analytics experience"] if llm_enabled else [],
                    "llm_gaps": [],
                    "llm_resume_focus_points": ["Highlight dashboard ownership"]
                    if llm_enabled
                    else [],
                    "llm_adjustment": 0.015 if llm_enabled else 0.0,
                    "llm_adjusted_score": 0.896 if llm_enabled else 0.881,
                    "llm_enriched": llm_enabled,
                },
            ],
        }
    )


def _make_args(user_json: Path, output: Path, *, enable_llm_rerank: bool) -> argparse.Namespace:
    return argparse.Namespace(
        user_json=str(user_json),
        top_k=10,
        top_n=2,
        needs_sponsorship="auto",
        experience_buffer_years=1,
        min_cosine_score=0.48,
        enable_llm_rerank=enable_llm_rerank,
        llm_top_n=2,
        llm_concurrency=3,
        max_user_chars=12000,
        preferred_country_code=None,
        output=str(output),
    )


@pytest.mark.asyncio
async def test_run_skips_llm_rerank_when_flag_disabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_match_experiment_module()
    user_json = tmp_path / "user.json"
    output_json = tmp_path / "output.json"
    user_json.write_text(
        json.dumps(
            {
                "summary": "Analytics profile",
                "skills": ["Python", "SQL"],
                "workHistory": [
                    {"title": "Analyst", "company": "ACME", "bullets": ["Built dashboards"]}
                ],
                "education": [{"degree": "B.S."}],
                "totalYearsExperience": 3,
            }
        ),
        encoding="utf-8",
    )

    calls: list[dict[str, object]] = []

    async def fake_run(self, request):  # noqa: ANN001
        _ = self
        calls.append(
            {
                "candidate_summary": request.candidate.summary,
                "top_k": request.top_k,
                "top_n": request.top_n,
                "enable_llm_rerank": request.enable_llm_rerank,
                "user_json": request.user_json,
            }
        )
        return _make_response(llm_enabled=False)

    monkeypatch.setattr(module.MatchExperimentService, "run", fake_run)

    await module.run(_make_args(user_json, output_json, enable_llm_rerank=False))

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert calls == [
        {
            "candidate_summary": "Analytics profile",
            "top_k": 10,
            "top_n": 2,
            "enable_llm_rerank": False,
            "user_json": str(user_json),
        }
    ]
    assert payload["meta"]["llm_rerank_summary"]["enabled"] is False
    assert all(item["llm_enriched"] is False for item in payload["results"])
    assert all(item["llm_adjusted_score"] == item["final_score"] for item in payload["results"])


@pytest.mark.asyncio
async def test_run_applies_llm_rerank_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_match_experiment_module()
    user_json = tmp_path / "user.json"
    output_json = tmp_path / "output.json"
    user_json.write_text(
        json.dumps(
            {
                "summary": "Analytics profile",
                "skills": ["Python", "SQL"],
                "workHistory": [
                    {"title": "Analyst", "company": "ACME", "bullets": ["Built dashboards"]}
                ],
                "education": [{"degree": "B.S."}],
                "totalYearsExperience": 3,
            }
        ),
        encoding="utf-8",
    )

    calls: list[dict[str, object]] = []

    async def fake_run(self, request):  # noqa: ANN001
        _ = self
        calls.append(
            {
                "candidate_summary": request.candidate.summary,
                "top_k": request.top_k,
                "top_n": request.top_n,
                "enable_llm_rerank": request.enable_llm_rerank,
                "llm_top_n": request.llm_top_n,
                "llm_concurrency": request.llm_concurrency,
                "user_json": request.user_json,
            }
        )
        return _make_response(llm_enabled=True)

    monkeypatch.setattr(module.MatchExperimentService, "run", fake_run)

    await module.run(_make_args(user_json, output_json, enable_llm_rerank=True))

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert calls == [
        {
            "candidate_summary": "Analytics profile",
            "top_k": 10,
            "top_n": 2,
            "enable_llm_rerank": True,
            "llm_top_n": 2,
            "llm_concurrency": 3,
            "user_json": str(user_json),
        }
    ]
    assert payload["meta"]["llm_rerank_summary"]["enabled"] is True
    assert [item["job_id"] for item in payload["results"]] == ["job-2", "job-1"]
    assert all(item["llm_recommendation"] == "yes" for item in payload["results"])
