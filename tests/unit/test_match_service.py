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
from app.services.infra.llm import LLMConfig


class _FakeConnection:
    async def close(self) -> None:
        return None


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
        "location_text": "Toronto, ON",
        "city": "Toronto",
        "region": "Ontario",
        "country_code": "CA",
        "workplace_type": "hybrid",
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


@pytest.mark.asyncio
async def test_match_service_run_returns_typed_response_without_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_connect(dsn: str):  # noqa: ANN001
        assert dsn == "postgresql://local/test"
        return _FakeConnection()

    async def fake_embed_text(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        return [0.1, 0.2, 0.3]

    async def fake_fetch_candidates(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        assert "embedding_kind" in kwargs
        assert "embedding_model" in kwargs
        return [
            _make_candidate("job-1", 0.88),
            _make_candidate("job-2", 0.83),
        ]

    monkeypatch.setattr("app.services.infra.match_query.asyncpg.connect", fake_connect)
    monkeypatch.setattr(
        "app.services.application.match_service.get_settings",
        lambda: SimpleNamespace(database_url="postgresql+asyncpg://local/test", embedding_dim=3),
    )
    monkeypatch.setattr(
        "app.services.application.match_service.get_embedding_config", lambda: SimpleNamespace()
    )
    monkeypatch.setattr(
        "app.services.application.match_service.resolve_active_job_embedding_target",
        lambda **_: EmbeddingTargetDescriptor(
            embedding_kind="job_description",
            embedding_target_revision=1,
            embedding_model="test-model",
            embedding_dim=3,
        ),
    )
    monkeypatch.setattr("app.services.application.match_service.embed_text", fake_embed_text)
    monkeypatch.setattr("app.services.infra.match_query.fetch_candidates", fake_fetch_candidates)

    response = await MatchExperimentService().run(_make_request(enable_llm_rerank=False))

    assert response.meta.user_json == "/tmp/user.json"
    assert response.meta.sql_prefilter.degree_filter_applied is True
    assert response.meta.sql_prefilter.preferred_country_code is None
    assert response.meta.llm_rerank_summary.enabled is False
    assert response.meta.results_returned == 2
    assert len(response.results) == 2
    assert response.results[0].llm_enriched is False
    assert response.results[0].llm_adjusted_score == response.results[0].final_score


@pytest.mark.asyncio
async def test_match_service_run_applies_llm_rerank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def fake_connect(dsn: str):  # noqa: ANN001
        _ = dsn
        return _FakeConnection()

    async def fake_embed_text(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        return [0.1, 0.2, 0.3]

    async def fake_fetch_candidates(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        assert "embedding_kind" in kwargs
        assert "embedding_model" in kwargs
        return [
            _make_candidate("job-1", 0.88),
            _make_candidate("job-2", 0.83),
        ]

    async def fake_apply_llm_rerank(rows, *, user_data, context_by_job_id, llm_top_n, concurrency):  # noqa: ANN001
        calls.append(
            {
                "row_ids": [row["job_id"] for row in rows],
                "context_ids": sorted(context_by_job_id),
                "llm_top_n": llm_top_n,
                "concurrency": concurrency,
                "user_summary": user_data["summary"],
            }
        )
        enriched = []
        for row in reversed(rows):
            item = dict(row)
            item["llm_recommendation"] = "yes"
            item["llm_reasons"] = ["Relevant analytics experience"]
            item["llm_gaps"] = []
            item["llm_resume_focus_points"] = ["Highlight dashboard ownership"]
            item["llm_adjustment"] = 0.015
            item["llm_adjusted_score"] = round(float(item["final_score"]) + 0.015, 6)
            item["llm_enriched"] = True
            enriched.append(item)
        return enriched, {
            "enabled": True,
            "window_size": 2,
            "attempted_count": 2,
            "succeeded_count": 2,
            "failed_count": 0,
            "concurrency": concurrency,
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
        }

    monkeypatch.setattr("app.services.infra.match_query.asyncpg.connect", fake_connect)
    monkeypatch.setattr(
        "app.services.application.match_service.get_settings",
        lambda: SimpleNamespace(database_url="postgresql+asyncpg://local/test", embedding_dim=3),
    )
    monkeypatch.setattr(
        "app.services.application.match_service.get_embedding_config", lambda: SimpleNamespace()
    )
    monkeypatch.setattr(
        "app.services.application.match_service.resolve_active_job_embedding_target",
        lambda **_: EmbeddingTargetDescriptor(
            embedding_kind="job_description",
            embedding_target_revision=1,
            embedding_model="test-model",
            embedding_dim=3,
        ),
    )
    monkeypatch.setattr("app.services.application.match_service.embed_text", fake_embed_text)
    monkeypatch.setattr("app.services.infra.match_query.fetch_candidates", fake_fetch_candidates)
    monkeypatch.setattr(
        "app.services.infra.llm_match_recommendation.get_llm_config",
        lambda: LLMConfig(provider="openai", model="gpt-4o-mini", api_key="test-key"),
    )
    monkeypatch.setattr(
        "app.services.infra.llm_match_recommendation.apply_llm_rerank",
        fake_apply_llm_rerank,
    )

    response = await MatchExperimentService().run(_make_request(enable_llm_rerank=True))

    assert calls == [
        {
            "row_ids": ["job-1", "job-2"],
            "context_ids": ["job-1", "job-2"],
            "llm_top_n": 2,
            "concurrency": 2,
            "user_summary": "Analytics profile",
        }
    ]
    assert response.meta.llm_rerank_summary.enabled is True
    assert [item.job_id for item in response.results] == ["job-2", "job-1"]
    assert all(item.llm_recommendation == "yes" for item in response.results)


@pytest.mark.asyncio
async def test_match_service_run_wraps_query_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_connect(dsn: str):  # noqa: ANN001
        raise RuntimeError("connection boom")

    async def fake_embed_text(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr("app.services.infra.match_query.asyncpg.connect", fake_connect)
    monkeypatch.setattr(
        "app.services.application.match_service.get_settings",
        lambda: SimpleNamespace(database_url="postgresql+asyncpg://local/test", embedding_dim=3),
    )
    monkeypatch.setattr(
        "app.services.application.match_service.get_embedding_config", lambda: SimpleNamespace()
    )
    monkeypatch.setattr(
        "app.services.application.match_service.resolve_active_job_embedding_target",
        lambda **_: EmbeddingTargetDescriptor(
            embedding_kind="job_description",
            embedding_target_revision=1,
            embedding_model="test-model",
            embedding_dim=3,
        ),
    )
    monkeypatch.setattr("app.services.application.match_service.embed_text", fake_embed_text)

    with pytest.raises(MatchQueryError):
        await MatchExperimentService().run(_make_request(enable_llm_rerank=False))


@pytest.mark.asyncio
async def test_match_service_run_fails_fast_when_llm_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_connect(dsn: str):  # noqa: ANN001
        _ = dsn
        return _FakeConnection()

    async def fake_embed_text(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        return [0.1, 0.2, 0.3]

    async def fake_fetch_candidates(*args, **kwargs):  # noqa: ANN002, ANN003
        _ = (args, kwargs)
        return [_make_candidate("job-1", 0.88)]

    monkeypatch.setattr("app.services.infra.match_query.asyncpg.connect", fake_connect)
    monkeypatch.setattr(
        "app.services.application.match_service.get_settings",
        lambda: SimpleNamespace(database_url="postgresql+asyncpg://local/test", embedding_dim=3),
    )
    monkeypatch.setattr(
        "app.services.application.match_service.get_embedding_config", lambda: SimpleNamespace()
    )
    monkeypatch.setattr(
        "app.services.application.match_service.resolve_active_job_embedding_target",
        lambda **_: EmbeddingTargetDescriptor(
            embedding_kind="job_description",
            embedding_target_revision=1,
            embedding_model="test-model",
            embedding_dim=3,
        ),
    )
    monkeypatch.setattr("app.services.application.match_service.embed_text", fake_embed_text)
    monkeypatch.setattr("app.services.infra.match_query.fetch_candidates", fake_fetch_candidates)
    monkeypatch.setattr(
        "app.services.infra.llm_match_recommendation.get_llm_config",
        lambda: LLMConfig(provider="openai", model="gpt-4o-mini", api_key=None),
    )

    with pytest.raises(LLMRerankConfigurationError):
        await MatchExperimentService().run(_make_request(enable_llm_rerank=True))
