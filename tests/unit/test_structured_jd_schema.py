"""Unit tests for structured JD schema normalization."""

from app.schemas.structured_jd import (
    STRUCTURED_JD_SCHEMA_VERSION,
    StructuredJD,
    build_structured_jd_projection,
    build_structured_jd_storage_payload,
    degree_level_to_rank,
)


def test_structured_jd_normalizes_new_fields() -> None:
    jd = StructuredJD.model_validate(
        {
            "required_skills": "Python",
            "sponsorship_not_available": "Cannot sponsor visas",
            "job_domain_raw": "Treasury / Banking Operations",
            "job_domain_normalized": "not-a-real-industry",
            "min_degree_level": "M.S.",
        }
    )

    assert jd.required_skills == ["Python"]
    assert jd.sponsorship_not_available == "yes"
    assert jd.job_domain_raw == "Treasury / Banking Operations"
    assert jd.job_domain_normalized == "finance_treasury"
    assert jd.min_degree_level == "master"


def test_structured_jd_projection_sets_rank_and_version() -> None:
    projection = build_structured_jd_projection(
        {
            "sponsorship_not_available": "unknown",
            "job_domain_raw": "Threat Research",
            "job_domain_normalized": "unknown",
            "min_degree_level": "bachelor",
        }
    )

    assert projection["job_domain_normalized"] == "cybersecurity"
    assert projection["min_degree_rank"] == degree_level_to_rank("bachelor")
    assert projection["structured_jd_version"] == STRUCTURED_JD_SCHEMA_VERSION


def test_structured_jd_storage_payload_omits_duplicated_canonical_fields() -> None:
    payload = build_structured_jd_storage_payload(
        {
            "required_skills": ["Python"],
            "experience_years": 4,
            "seniority_level": "senior",
            "sponsorship_not_available": "yes",
            "job_domain_raw": "unknown",
            "job_domain_normalized": "software_engineering",
            "min_degree_level": "master",
        }
    )

    assert payload["required_skills"] == ["Python"]
    assert payload["experience_years"] == 4
    assert payload["seniority_level"] == "senior"
    assert "sponsorship_not_available" not in payload
    assert "job_domain_normalized" not in payload
    assert "min_degree_level" not in payload
    assert "job_domain_raw" not in payload


def test_structured_jd_invalid_values_fall_back_to_unknown() -> None:
    jd = StructuredJD.model_validate(
        {
            "sponsorship_not_available": "maybe",
            "job_domain_normalized": "something-else",
            "min_degree_level": "legendary",
        }
    )

    assert jd.sponsorship_not_available == "unknown"
    assert jd.job_domain_normalized == "unknown"
    assert jd.min_degree_level == "unknown"


def test_structured_jd_accepts_legacy_industry_fields() -> None:
    jd = StructuredJD.model_validate(
        {
            "industry_raw": "Artificial Intelligence",
            "industry_normalized": "software_internet",
        }
    )

    assert jd.job_domain_raw == "Artificial Intelligence"
    assert jd.job_domain_normalized == "software_engineering"
