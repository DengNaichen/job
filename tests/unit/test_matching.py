"""Unit tests for matching helpers."""

from app.services.domain.matching import (
    build_user_embedding_text,
    build_user_skill_tokens,
    compute_domain_match_score,
    compute_seniority_match_score,
    filter_match_candidates_by_min_cosine_score,
    hard_filter_match_candidates,
    infer_needs_sponsorship,
    infer_user_degree_rank,
    infer_user_job_domain,
    infer_user_seniority_level,
    rerank_match_candidates,
    to_optional_int,
)


def test_infer_needs_sponsorship_from_work_authorization() -> None:
    assert infer_needs_sponsorship({"workAuthorization": "Need sponsorship for H1B"}) is True
    assert infer_needs_sponsorship({"workAuthorization": "US citizen"}) is False


def test_infer_user_degree_rank_uses_highest_degree() -> None:
    user = {
        "education": [
            {"degree": "B.A."},
            {"degree": "M.S."},
        ]
    }
    assert infer_user_degree_rank(user) == 3


def test_build_user_embedding_text_contains_summary_skills_and_work() -> None:
    user = {
        "summary": "Analytics profile",
        "skills": ["Python", "SQL"],
        "workHistory": [{"title": "Analyst", "company": "ACME", "bullets": ["Built dashboards"]}],
    }

    text = build_user_embedding_text(user, max_chars=500)

    assert "Analytics profile" in text
    assert "Python, SQL" in text
    assert "Analyst | ACME | Built dashboards" in text


def test_rerank_match_candidates_applies_weighted_scoring_and_sorts() -> None:
    rows = [
        {
            "job_id": "a",
            "cosine_score": 0.91,
            "jd_experience_years": 6,
            "min_degree_rank": 3,
            "job_domain_normalized": "software_engineering",
            "title": "Senior Software Engineer",
            "structured_jd": {
                "required_skills": ["Go"],
                "preferred_skills": ["Distributed Systems"],
                "seniority_level": "senior",
            },
        },
        {
            "job_id": "b",
            "cosine_score": 0.88,
            "jd_experience_years": 3,
            "min_degree_rank": 2,
            "job_domain_normalized": "data_ai",
            "title": "Business Intelligence Analyst",
            "structured_jd": {
                "required_skills": ["Python"],
                "preferred_skills": ["SQL"],
                "seniority_level": "mid",
            },
        },
    ]

    ranked = rerank_match_candidates(
        rows,
        user_years=3,
        user_degree_rank=2,
        user_skill_tokens={"python", "sql", "tableau"},
        user_domain="data_ai",
        user_seniority="mid",
    )

    assert ranked[0]["job_id"] == "b"
    assert ranked[0]["skill_overlap_score"] == 1.0
    assert ranked[0]["domain_match_score"] == 1.0
    assert ranked[0]["seniority_match_score"] == 1.0
    assert ranked[0]["final_score"] == 0.916
    assert "llm_recommendation" not in ranked[0]
    assert ranked[1]["experience_gap"] == 3
    assert ranked[1]["education_gap"] == 1
    assert ranked[1]["penalties"]["total_penalty"] == 0.2


def test_build_user_features_for_rerank() -> None:
    user = {
        "summary": "Business analytics student with experience in business intelligence and operations",
        "skills": ["Python", "SQL", "Business Intelligence"],
        "workHistory": [{"title": "Business Intelligence Analyst"}],
        "totalYearsExperience": 3,
    }

    assert build_user_skill_tokens(user) == {"python", "sql", "business intelligence"}
    assert infer_user_job_domain(user) == "data_ai"
    assert infer_user_seniority_level(user) == "mid"


def test_domain_and_seniority_scores_handle_exact_and_adjacent_matches() -> None:
    assert compute_domain_match_score(user_domain="data_ai", job_domain="data_ai") == 1.0
    assert compute_domain_match_score(user_domain="data_ai", job_domain="operations") == 0.5
    assert compute_domain_match_score(user_domain="unknown", job_domain="operations") == 0.0

    assert compute_seniority_match_score(user_seniority="mid", job_seniority="mid") == 1.0
    assert compute_seniority_match_score(user_seniority="mid", job_seniority="senior") == 0.7
    assert compute_seniority_match_score(user_seniority="mid", job_seniority="director") == 0.0


def test_to_optional_int_preserves_missing_values() -> None:
    assert to_optional_int(None) is None
    assert to_optional_int("") is None
    assert to_optional_int("3") == 3
    assert to_optional_int("3.0") == 3
    assert to_optional_int(2) == 2
    assert to_optional_int("abc") is None


def test_filter_match_candidates_by_min_cosine_score() -> None:
    rows = [
        {"job_id": "keep-high", "cosine_score": 0.52},
        {"job_id": "keep-edge", "cosine_score": 0.48},
        {"job_id": "drop", "cosine_score": 0.4799},
        {"job_id": "missing-score"},
    ]

    passed, summary = filter_match_candidates_by_min_cosine_score(rows, min_cosine_score=0.48)

    assert [row["job_id"] for row in passed] == ["keep-high", "keep-edge"]
    assert summary["input_count"] == 4
    assert summary["passed_count"] == 2
    assert summary["rejected_count"] == 2
    assert summary["min_cosine_score"] == 0.48


def test_filter_match_candidates_by_min_cosine_score_rejects_invalid_threshold() -> None:
    try:
        filter_match_candidates_by_min_cosine_score([], min_cosine_score=1.01)
    except ValueError as exc:
        assert "min_cosine_score" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid cosine threshold")


def test_hard_filter_excludes_sponsorship_only_when_needed() -> None:
    rows = [
        {
            "job_id": "blocked",
            "sponsorship_not_available": "yes",
            "min_degree_rank": -1,
            "jd_experience_years": None,
        },
        {
            "job_id": "unknown",
            "sponsorship_not_available": "unknown",
            "min_degree_rank": -1,
            "jd_experience_years": None,
        },
    ]

    passed, summary = hard_filter_match_candidates(
        rows,
        needs_sponsorship=True,
        user_years=3,
        user_degree_rank=2,
    )

    assert [row["job_id"] for row in passed] == ["unknown"]
    assert summary["rejected_count"] == 1
    assert summary["rejected_by_reason"]["sponsorship"] == 1

    passed_without_need, summary_without_need = hard_filter_match_candidates(
        rows,
        needs_sponsorship=False,
        user_years=3,
        user_degree_rank=2,
    )

    assert [row["job_id"] for row in passed_without_need] == ["blocked", "unknown"]
    assert summary_without_need["rejected_count"] == 0


def test_hard_filter_excludes_degree_only_when_user_degree_known() -> None:
    rows = [
        {
            "job_id": "blocked",
            "sponsorship_not_available": "unknown",
            "min_degree_rank": 3,
            "jd_experience_years": None,
        },
        {
            "job_id": "allowed",
            "sponsorship_not_available": "unknown",
            "min_degree_rank": 2,
            "jd_experience_years": None,
        },
        {
            "job_id": "unknown",
            "sponsorship_not_available": "unknown",
            "min_degree_rank": -1,
            "jd_experience_years": None,
        },
    ]

    passed, summary = hard_filter_match_candidates(
        rows,
        needs_sponsorship=False,
        user_years=3,
        user_degree_rank=2,
    )

    assert [row["job_id"] for row in passed] == ["allowed", "unknown"]
    assert summary["rejected_by_reason"]["degree"] == 1

    passed_with_unknown_user, summary_with_unknown_user = hard_filter_match_candidates(
        rows,
        needs_sponsorship=False,
        user_years=3,
        user_degree_rank=-1,
    )

    assert [row["job_id"] for row in passed_with_unknown_user] == ["blocked", "allowed", "unknown"]
    assert summary_with_unknown_user["rejected_by_reason"]["degree"] == 0


def test_hard_filter_excludes_experience_beyond_buffer() -> None:
    rows = [
        {
            "job_id": "blocked",
            "sponsorship_not_available": "unknown",
            "min_degree_rank": -1,
            "jd_experience_years": 5,
        },
        {
            "job_id": "allowed",
            "sponsorship_not_available": "unknown",
            "min_degree_rank": -1,
            "jd_experience_years": 4,
        },
        {
            "job_id": "unknown",
            "sponsorship_not_available": "unknown",
            "min_degree_rank": -1,
            "jd_experience_years": None,
        },
    ]

    passed, summary = hard_filter_match_candidates(
        rows,
        needs_sponsorship=False,
        user_years=3,
        user_degree_rank=2,
        max_experience_gap=1,
    )

    assert [row["job_id"] for row in passed] == ["allowed", "unknown"]
    assert summary["rejected_by_reason"]["experience"] == 1

    passed_with_unknown_user, summary_with_unknown_user = hard_filter_match_candidates(
        rows,
        needs_sponsorship=False,
        user_years=None,
        user_degree_rank=2,
        max_experience_gap=1,
    )

    assert [row["job_id"] for row in passed_with_unknown_user] == ["blocked", "allowed", "unknown"]
    assert summary_with_unknown_user["rejected_by_reason"]["experience"] == 0


def test_hard_filter_tracks_multiple_rejection_reasons_and_marks_passed_rows() -> None:
    rows = [
        {
            "job_id": "blocked",
            "sponsorship_not_available": "unknown",
            "min_degree_rank": 3,
            "jd_experience_years": 6,
        },
        {
            "job_id": "allowed",
            "sponsorship_not_available": "unknown",
            "min_degree_rank": 2,
            "jd_experience_years": 4,
            "cosine_score": 0.88,
        },
    ]

    passed, summary = hard_filter_match_candidates(
        rows,
        needs_sponsorship=False,
        user_years=3,
        user_degree_rank=2,
        max_experience_gap=1,
    )

    assert summary["rejected_count"] == 1
    assert summary["rejected_by_reason"]["degree"] == 1
    assert summary["rejected_by_reason"]["experience"] == 1
    assert passed[0]["hard_filter"] == {"passed": True, "reasons": []}

    ranked = rerank_match_candidates(passed, user_years=3, user_degree_rank=2)
    assert ranked[0]["job_id"] == "allowed"
