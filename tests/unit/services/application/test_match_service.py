"""Unit tests for the match application service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.match import CandidateProfile, MatchRequest
from app.services.application.match_service import (
    LLMRerankConfigurationError,
    MatchExperimentService,
    MatchQueryError,
)
from app.services.infra.embedding import EmbeddingTargetDescriptor
from app.services.infra.matching.llm_rerank import (
    attach_default_llm_fields,
    build_disabled_llm_rerank_summary,
)


def _active_target() -> EmbeddingTargetDescriptor:
    return EmbeddingTargetDescriptor(
        embedding_kind="job_description",
        embedding_target_revision=1,
        embedding_model="test-model",
        embedding_dim=3,
    )


def _make_request(*, enable_llm_rerank: bool = False) -> MatchRequest:
    return MatchRequest(
        candidate=CandidateProfile.model_validate(
            {
                "summary": "Analytics profile",
                "skills": ["Python", "SQL"],
                "workAuthorization": "US citizen",
                "education": [{"degree": "B.S."}],
                "workHistory": [
                    {"title": "Analyst", "company": "ACME", "bullets": ["Built dashboards"]}
                ],
                "totalYearsExperience": 3,
            }
        ),
        top_k=10,
        top_n=2,
        enable_llm_rerank=enable_llm_rerank,
        llm_top_n=2,
        llm_concurrency=2,
        user_json="/tmp/user.json",
    )


def _make_candidate(job_id: str, cosine_score: float) -> dict[str, object]:
    return {
        "job_id": job_id,
        "source": "greenhouse",
        "title": f"Job {job_id}",
        "apply_url": f"https://example.com/{job_id}",
        "locations": [
            {
                "source_raw": "Toronto, ON",
                "city": "Toronto",
                "region": "Ontario",
                "country_code": "CA",
                "workplace_type": "hybrid",
                "is_primary": True,
            }
        ],
        "department": "Analytics",
        "team": "BI",
        "employment_type": "full-time",
        "sponsorship_not_available": "unknown",
        "job_domain_raw": None,
        "job_domain_normalized": "data_ai",
        "min_degree_level": "bachelor",
        "min_degree_rank": 2,
        "structured_jd": {
            "required_skills": ["Python"],
            "preferred_skills": ["SQL"],
            "experience_years": 3,
            "seniority_level": "mid",
        },
        "jd_experience_years": 3,
        "cosine_score": cosine_score,
    }


class _FakeCandidateGateway:
    def __init__(
        self,
        *,
        rows: list[dict[str, object]] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.rows = rows or []
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def fetch_candidates(self, **kwargs):  # noqa: ANN003
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.rows


class _FakeLLMReranker:
    def __init__(
        self,
        *,
        result_rows: list[dict[str, object]] | None = None,
        summary: dict[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result_rows = result_rows
        self.summary = summary
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def rerank_if_enabled(  # noqa: PLR0913
        self,
        rows: list[dict[str, object]],
        *,
        enabled: bool,
        user_data: dict[str, object],
        context_by_job_id: dict[str, dict[str, object]],
        llm_top_n: int,
        concurrency: int,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        self.calls.append(
            {
                "row_ids": [str(row["job_id"]) for row in rows],
                "context_ids": sorted(context_by_job_id),
                "llm_top_n": llm_top_n,
                "concurrency": concurrency,
                "enabled": enabled,
                "user_summary": str(user_data.get("summary") or ""),
            }
        )
        if self.error is not None:
            raise self.error
        if enabled:
            base_rows = self.result_rows or list(reversed(rows))
            enriched_rows: list[dict[str, object]] = []
            for row in base_rows:
                item = dict(row)
                item["llm_recommendation"] = "yes"
                item["llm_reasons"] = ["Relevant analytics experience"]
                item["llm_gaps"] = []
                item["llm_resume_focus_points"] = ["Highlight dashboard ownership"]
                item["llm_adjustment"] = 0.015
                item["llm_adjusted_score"] = round(float(item.get("final_score") or 0.0) + 0.015, 6)
                item["llm_enriched"] = True
                enriched_rows.append(item)
            return (
                enriched_rows,
                self.summary
                or {
                    "enabled": True,
                    "window_size": len(rows),
                    "attempted_count": len(rows),
                    "succeeded_count": len(rows),
                    "failed_count": 0,
                    "concurrency": concurrency,
                    "reorder_applied": False,
                    "adjustment_map": {
                        "strong_yes": 0.03,
                        "yes": 0.015,
                        "maybe": 0.0,
                        "stretch": -0.015,
                        "no": -0.03,
                    },
                    "token_usage": {
                        "total_requests": len(rows),
                        "total_tokens": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "by_model": {},
                    },
                },
            )
        return attach_default_llm_fields(rows), build_disabled_llm_rerank_summary()


def _build_service(
    *,
    candidate_gateway: _FakeCandidateGateway,
    llm_reranker: _FakeLLMReranker,
) -> MatchExperimentService:
    async def _embed_text(*_args, **_kwargs):  # noqa: ANN002, ANN003
        return [0.1, 0.2, 0.3]

    return MatchExperimentService(
        candidate_gateway=candidate_gateway,
        llm_reranker=llm_reranker,
        embedding_fn=_embed_text,
        embedding_config_provider=lambda: SimpleNamespace(),
        settings_provider=lambda: SimpleNamespace(
            database_url="postgresql+asyncpg://local/test",
            embedding_dim=3,
        ),
        active_target_resolver=lambda **_: _active_target(),
    )


@pytest.mark.asyncio
async def test_match_service_run_returns_typed_response_without_llm() -> None:
    gateway = _FakeCandidateGateway(
        rows=[_make_candidate("job-1", 0.88), _make_candidate("job-2", 0.83)]
    )
    reranker = _FakeLLMReranker()
    response = await _build_service(candidate_gateway=gateway, llm_reranker=reranker).run(
        _make_request(enable_llm_rerank=False)
    )

    assert len(gateway.calls) == 1
    assert gateway.calls[0]["embedding_kind"] == "job_description"
    assert gateway.calls[0]["embedding_model"] == "test-model"
    assert response.meta.user_json == "/tmp/user.json"
    assert response.meta.sql_prefilter.degree_filter_applied is True
    assert response.meta.sql_prefilter.preferred_country_code is None
    assert response.meta.llm_rerank_summary.enabled is False
    assert response.meta.results_returned == 2
    assert len(response.results) == 2
    assert response.results[0].llm_enriched is False
    assert response.results[0].llm_adjusted_score == response.results[0].final_score


@pytest.mark.asyncio
async def test_match_service_run_applies_llm_rerank() -> None:
    gateway = _FakeCandidateGateway(
        rows=[_make_candidate("job-1", 0.88), _make_candidate("job-2", 0.83)]
    )
    reranker = _FakeLLMReranker(
        summary={
            "enabled": True,
            "window_size": 2,
            "attempted_count": 2,
            "succeeded_count": 2,
            "failed_count": 0,
            "concurrency": 2,
            "reorder_applied": True,
            "adjustment_map": {
                "strong_yes": 0.03,
                "yes": 0.015,
                "maybe": 0.0,
                "stretch": -0.015,
                "no": -0.03,
            },
            "token_usage": {
                "total_requests": 2,
                "total_tokens": 42,
                "prompt_tokens": 30,
                "completion_tokens": 12,
                "by_model": {},
            },
        },
    )

    response = await _build_service(candidate_gateway=gateway, llm_reranker=reranker).run(
        _make_request(enable_llm_rerank=True)
    )

    assert reranker.calls == [
        {
            "row_ids": ["job-1", "job-2"],
            "context_ids": ["job-1", "job-2"],
            "llm_top_n": 2,
            "concurrency": 2,
            "enabled": True,
            "user_summary": "Analytics profile",
        }
    ]
    assert response.meta.llm_rerank_summary.enabled is True
    assert [item.job_id for item in response.results] == ["job-2", "job-1"]
    assert all(item.llm_recommendation == "yes" for item in response.results)


@pytest.mark.asyncio
async def test_match_service_run_wraps_query_errors() -> None:
    gateway = _FakeCandidateGateway(error=RuntimeError("connection boom"))
    reranker = _FakeLLMReranker()

    with pytest.raises(MatchQueryError):
        await _build_service(candidate_gateway=gateway, llm_reranker=reranker).run(
            _make_request(enable_llm_rerank=False)
        )


@pytest.mark.asyncio
async def test_match_service_run_fails_fast_when_llm_not_configured() -> None:
    gateway = _FakeCandidateGateway(rows=[_make_candidate("job-1", 0.88)])
    reranker = _FakeLLMReranker(error=ValueError("llm api key missing"))

    with pytest.raises(LLMRerankConfigurationError):
        await _build_service(candidate_gateway=gateway, llm_reranker=reranker).run(
            _make_request(enable_llm_rerank=True)
        )
