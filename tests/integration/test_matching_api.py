from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.v1.matching import get_match_service
from app.main import app
from app.schemas.match import MatchResponse
from app.services.application.match_service import MatchQueryError


def _build_response() -> MatchResponse:
    return MatchResponse.model_validate(
        {
            "meta": {
                "user_json": None,
                "needs_sponsorship": False,
                "user_total_years_experience": 3,
                "user_degree_rank": 2,
                "user_skill_count": 2,
                "user_domain": "data_ai",
                "user_seniority": "mid",
                "top_k": 10,
                "top_n": 3,
                "sql_prefilter": {
                    "sponsorship_filter_applied": False,
                    "degree_filter_applied": True,
                    "preferred_country_code": None,
                    "user_degree_rank": 2,
                },
                "candidates_after_sql_prefilter": 3,
                "vector_threshold_summary": {
                    "enabled": True,
                    "input_count": 3,
                    "passed_count": 2,
                    "rejected_count": 1,
                    "min_cosine_score": 0.48,
                },
                "candidates_after_vector_threshold": 2,
                "candidates_before_hard_filter": 2,
                "candidates_after_hard_filter": 1,
                "hard_filter_summary": {
                    "enabled": True,
                    "input_count": 2,
                    "passed_count": 1,
                    "rejected_count": 1,
                    "rejected_by_reason": {
                        "sponsorship": 0,
                        "degree": 0,
                        "experience": 1,
                    },
                    "config": {
                        "needs_sponsorship": False,
                        "degree_filter_applied": True,
                        "experience_filter_applied": True,
                        "max_experience_gap": 1,
                    },
                },
                "llm_rerank_summary": {
                    "enabled": False,
                    "window_size": 0,
                    "attempted_count": 0,
                    "succeeded_count": 0,
                    "failed_count": 0,
                    "concurrency": 0,
                    "reorder_applied": False,
                    "adjustment_map": {
                        "strong_yes": 0.03,
                        "yes": 0.015,
                        "maybe": 0.0,
                        "stretch": -0.015,
                        "no": -0.03,
                    },
                    "token_usage": {
                        "total_requests": 0,
                        "total_tokens": 0,
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "by_model": {},
                    },
                },
                "results_returned": 1,
            },
            "results": [
                {
                    "job_id": "job-1",
                    "source": "greenhouse",
                    "title": "Analytics Engineer",
                    "apply_url": "https://example.com/job-1",
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
                    "department": "Data",
                    "team": "Platform",
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
                    "hard_filter": {
                        "passed": True,
                        "reasons": [],
                    },
                    "llm_recommendation": None,
                    "llm_reasons": [],
                    "llm_gaps": [],
                    "llm_resume_focus_points": [],
                    "llm_adjustment": 0.0,
                    "llm_adjusted_score": 0.916,
                    "llm_enriched": False,
                }
            ],
        }
    )


class _StubMatchService:
    async def run(self, request):  # noqa: ANN001
        assert request.candidate.skills == ["Python", "SQL"]
        return _build_response()


class _FailingMatchService:
    async def run(self, request):  # noqa: ANN001
        _ = request
        raise MatchQueryError("candidate lookup unavailable")


class TestMatchingAPI:
    def test_get_match_recommendations_success(self, client: TestClient) -> None:
        app.dependency_overrides[get_match_service] = lambda: _StubMatchService()
        try:
            response = client.post(
                "/api/v1/matching/recommendations",
                json={
                    "candidate": {
                        "summary": "Analytics engineer",
                        "skills": ["Python", "SQL"],
                        "workAuthorization": "US citizen",
                        "totalYearsExperience": 3,
                    },
                    "top_k": 10,
                    "top_n": 3,
                },
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.headers["x-request-id"]
        payload = response.json()
        assert payload["meta"]["results_returned"] == 1
        assert payload["results"][0]["job_id"] == "job-1"
        assert payload["results"][0]["final_score"] == 0.916
        assert payload["results"][0]["locations"][0]["country_code"] == "CA"

    def test_get_match_recommendations_returns_service_unavailable_on_query_failure(
        self,
        client: TestClient,
    ) -> None:
        app.dependency_overrides[get_match_service] = lambda: _FailingMatchService()
        try:
            response = client.post(
                "/api/v1/matching/recommendations",
                json={
                    "candidate": {
                        "summary": "Analytics engineer",
                        "skills": ["Python"],
                    }
                },
            )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 503
        payload = response.json()
        assert payload["detail"]["code"] == "MATCH_QUERY_ERROR"
        assert payload["detail"]["message"] == "candidate lookup unavailable"
