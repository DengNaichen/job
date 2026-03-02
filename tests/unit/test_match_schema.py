"""Unit tests for typed matching schemas."""

from app.schemas.match import CandidateProfile, MatchRequest, MatchResponse, MatchResultItem


def test_candidate_profile_accepts_existing_user_json_aliases() -> None:
    candidate = CandidateProfile.model_validate(
        {
            "summary": "Analytics profile",
            "skills": ["Python", "SQL"],
            "workAuthorization": "US citizen",
            "totalYearsExperience": 3,
            "education": [
                {
                    "degree": "B.S.",
                    "school": "Example University",
                    "fieldOfStudy": "Computer Science",
                }
            ],
            "workHistory": [
                {
                    "title": "Analyst",
                    "company": "ACME",
                    "bullets": ["Built dashboards"],
                    "description": "Business intelligence work",
                    "achievements": ["Improved reporting latency"],
                }
            ],
        }
    )

    assert candidate.work_authorization == "US citizen"
    assert candidate.total_years_experience == 3
    assert candidate.education[0].field_of_study == "Computer Science"
    assert candidate.work_history[0].title == "Analyst"

    dumped = candidate.model_dump(by_alias=True)
    assert dumped["workAuthorization"] == "US citizen"
    assert dumped["totalYearsExperience"] == 3
    assert dumped["education"][0]["fieldOfStudy"] == "Computer Science"
    assert dumped["workHistory"][0]["title"] == "Analyst"


def test_match_request_defaults() -> None:
    request = MatchRequest(candidate=CandidateProfile())

    assert request.top_k == 200
    assert request.top_n == 50
    assert request.needs_sponsorship_override == "auto"
    assert request.experience_buffer_years == 1
    assert request.min_cosine_score == 0.48
    assert request.enable_llm_rerank is False
    assert request.llm_top_n == 10
    assert request.llm_concurrency == 3
    assert request.max_user_chars == 12000


def test_match_response_model_dump_preserves_existing_json_shape() -> None:
    response = MatchResponse.model_validate(
        {
            "meta": {
                "user_json": "/tmp/user.json",
                "needs_sponsorship": False,
                "user_total_years_experience": 3,
                "user_degree_rank": 2,
                "user_skill_count": 2,
                "user_domain": "data_ai",
                "user_seniority": "mid",
                "top_k": 200,
                "top_n": 20,
                "sql_prefilter": {
                    "sponsorship_filter_applied": False,
                    "degree_filter_applied": True,
                    "user_degree_rank": 2,
                },
                "candidates_after_sql_prefilter": 200,
                "vector_threshold_summary": {
                    "enabled": True,
                    "input_count": 200,
                    "passed_count": 70,
                    "rejected_count": 130,
                    "min_cosine_score": 0.48,
                },
                "candidates_after_vector_threshold": 70,
                "candidates_before_hard_filter": 70,
                "candidates_after_hard_filter": 49,
                "hard_filter_summary": {
                    "enabled": True,
                    "input_count": 70,
                    "passed_count": 49,
                    "rejected_count": 21,
                    "rejected_by_reason": {
                        "sponsorship": 0,
                        "degree": 0,
                        "experience": 21,
                    },
                    "config": {
                        "needs_sponsorship": False,
                        "degree_filter_applied": False,
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
                    "title": "Business Intelligence Analyst",
                    "apply_url": "https://example.com/job-1",
                    "location_text": "Toronto, ON",
                    "city": "Toronto",
                    "region": "Ontario",
                    "country_code": "CA",
                    "workplace_type": "hybrid",
                    "department": "Analytics",
                    "team": "BI",
                    "employment_type": "full-time",
                    "job_domain_normalized": "data_ai",
                    "min_degree_rank": 2,
                    "jd_experience_years": 3,
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

    dumped = response.model_dump(mode="json")
    assert dumped["meta"]["user_json"] == "/tmp/user.json"
    assert dumped["results"][0]["job_domain_normalized"] == "data_ai"
    assert dumped["results"][0]["penalties"]["total_penalty"] == 0.0
    assert dumped["results"][0]["llm_recommendation"] is None


def test_match_result_item_keeps_extra_fields_in_dump() -> None:
    item = MatchResultItem.model_validate(
        {
            "job_id": "job-1",
            "title": "Analyst",
            "apply_url": "https://example.com/job-1",
            "city": "Toronto",
            "region": "Ontario",
            "country_code": "CA",
            "workplace_type": "hybrid",
            "cosine_score": 0.8,
            "skill_overlap_score": 0.5,
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
                "cosine_component": 0.56,
                "skill_component": 0.075,
                "domain_component": 0.1,
                "seniority_component": 0.05,
            },
            "final_score": 0.785,
            "llm_adjusted_score": 0.785,
            "job_domain_normalized": "data_ai",
        }
    )

    assert item.model_dump()["job_domain_normalized"] == "data_ai"
