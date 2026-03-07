"""Unit tests for domain LLM parsing and post-processing helpers."""

from app.services.domain.llm_parsing import (
    merge_llm_and_rule_fields,
    merge_llm_and_rule_fields_batch,
    parse_llm_payload,
    parse_llm_payload_batch,
)


def test_parse_llm_payload_handles_compact_schema() -> None:
    parsed = parse_llm_payload(
        {
            "d": "software_engineering",
            "s": ["Python", "SQL"],
        }
    )

    assert parsed["required_skills"] == ["Python (computer programming)", "SQL"]
    assert parsed["preferred_skills"] == []
    assert parsed["job_domain_raw"] is None
    assert parsed["job_domain_normalized"] == "software_engineering"


def test_parse_llm_payload_handles_full_schema() -> None:
    parsed = parse_llm_payload(
        {
            "required_skills": ["Python"],
            "preferred_skills": ["Go"],
            "key_responsibilities": ["Build APIs"],
            "keywords": ["distributed systems"],
            "job_domain_raw": "Backend Engineering",
            "job_domain_normalized": "software_engineering",
        }
    )

    assert parsed["required_skills"] == ["Python (computer programming)"]
    assert parsed["preferred_skills"] == ["Go"]
    assert parsed["job_domain_raw"] == "Backend Engineering"
    assert parsed["job_domain_normalized"] == "software_engineering"
    assert "key_responsibilities" not in parsed
    assert "keywords" not in parsed


def test_parse_llm_payload_defaults_unknown_domain_when_missing() -> None:
    parsed = parse_llm_payload({"s": ["Python"]})

    assert parsed["required_skills"] == ["Python (computer programming)"]
    assert parsed["job_domain_normalized"] == "unknown"


def test_parse_llm_payload_batch_normalizes_each_alias() -> None:
    parsed = parse_llm_payload_batch(
        {
            "j1": {"d": "software_engineering", "s": ["Python"]},
            "j2": {
                "required_skills": ["Treasury"],
                "preferred_skills": ["Risk"],
                "job_domain_raw": "Finance",
                "job_domain_normalized": "finance_treasury",
            },
        }
    )

    assert parsed["j1"]["required_skills"] == ["Python (computer programming)"]
    assert parsed["j1"]["job_domain_normalized"] == "software_engineering"
    assert parsed["j2"]["required_skills"] == ["treasury"]
    assert parsed["j2"]["preferred_skills"] == ["Risk"]
    assert parsed["j2"]["job_domain_raw"] == "Finance"


def test_merge_llm_and_rule_fields_merges_single_payload_with_rule_fields() -> None:
    merged = merge_llm_and_rule_fields(
        llm_payload={
            "d": "software_engineering",
            "s": ["Python", "SQL"],
        },
        description=(
            "Bachelor's degree in Computer Science required. "
            "3-5 years of backend engineering experience required. "
            "The company is unable to provide visa sponsorship for this role."
        ),
        title="Senior Backend Engineer",
    )

    assert merged.required_skills == ["Python (computer programming)", "SQL"]
    assert merged.job_domain_normalized == "software_engineering"
    assert merged.experience_years == 3
    assert merged.min_degree_level == "bachelor"
    assert merged.sponsorship_not_available == "yes"
    assert merged.seniority_level == "senior"


def test_merge_llm_and_rule_fields_batch_merges_by_alias_and_skips_missing_inputs() -> None:
    merged = merge_llm_and_rule_fields_batch(
        llm_payloads_by_alias={
            "j1": {"d": "finance_treasury", "s": ["banking", "swift"]},
            "j2": {"d": "software_engineering", "s": ["python", "sql"]},
            "j999": {"d": "unknown", "s": ["misc"]},
        },
        normalized_inputs_by_alias={
            "j1": {
                "title": "Treasury Manager",
                "description": "Master's degree required. 8-12 years of relevant experience. No sponsorship available.",
            },
            "j2": {
                "title": "Backend Engineer",
                "description": "Strong Python and SQL skills. 3+ years of experience.",
            },
            "j3": {
                "title": "Unused",
                "description": "This alias has no llm payload",
            },
        },
        input_aliases=["j1", "j2", "j3"],
    )

    assert set(merged.keys()) == {"j1", "j2"}

    assert merged["j1"].job_domain_normalized == "finance_treasury"
    assert merged["j1"].experience_years == 8
    assert merged["j1"].min_degree_level == "master"
    assert merged["j1"].sponsorship_not_available == "yes"

    assert merged["j2"].job_domain_normalized == "software_engineering"
    assert merged["j2"].experience_years == 3
    assert merged["j2"].required_skills == ["Python (computer programming)", "SQL"]
