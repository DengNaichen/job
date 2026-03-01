"""Unit tests for rule-based JD extraction helpers."""

from app.services.domain.jd_rules import extract_rule_based_fields, fallback_job_domain


def test_extract_rule_based_fields_parses_sponsorship_years_degree_and_seniority() -> None:
    payload = extract_rule_based_fields(
        """
        This position is open to candidates legally authorized to work in Thailand.
        The company is unable to provide visa sponsorship for this role.
        Bachelor's degree in Computer Science or related field required.
        3-5 years of relevant experience in backend engineering.
        """,
        title="Senior Backend Engineer",
    )

    assert payload["sponsorship_not_available"] == "yes"
    assert payload["experience_years"] == 3
    assert payload["min_degree_level"] == "bachelor"
    assert payload["seniority_level"] == "senior"
    assert payload["experience_requirements"]
    assert payload["education_requirements"]


def test_fallback_job_domain_uses_title_and_text() -> None:
    domain = fallback_job_domain(
        "Threat Researcher",
        "Research malware, threat actors, SIEM detections, and security controls.",
    )

    assert domain == "cybersecurity"
