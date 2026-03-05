"""Integration contract checks for matching location payload shape."""

from fastapi.testclient import TestClient

from app.api.v1.matching import get_match_service
from app.main import app
from app.schemas.match import MatchResponse


class _StubMatchService:
    async def run(self, request):  # noqa: ANN001
        _ = request
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
                    "candidates_after_sql_prefilter": 1,
                    "vector_threshold_summary": {
                        "enabled": True,
                        "input_count": 1,
                        "passed_count": 1,
                        "rejected_count": 0,
                        "min_cosine_score": 0.48,
                    },
                    "candidates_after_vector_threshold": 1,
                    "candidates_before_hard_filter": 1,
                    "candidates_after_hard_filter": 1,
                    "hard_filter_summary": {
                        "enabled": True,
                        "input_count": 1,
                        "passed_count": 1,
                        "rejected_count": 0,
                        "rejected_by_reason": {
                            "sponsorship": 0,
                            "degree": 0,
                            "experience": 0,
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
                        "llm_adjusted_score": 0.916,
                    }
                ],
            }
        )


def test_matching_response_excludes_legacy_flattened_location_fields(client: TestClient) -> None:
    app.dependency_overrides[get_match_service] = lambda: _StubMatchService()
    try:
        response = client.post(
            "/api/v1/matching/recommendations",
            json={
                "candidate": {
                    "summary": "Analytics engineer",
                    "skills": ["Python", "SQL"],
                },
                "top_k": 10,
                "top_n": 3,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    item = payload["results"][0]

    for field_name in ("location_text", "city", "region", "country_code", "workplace_type"):
        assert field_name not in item
    assert "locations" in item
