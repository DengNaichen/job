"""Unit tests for education rule parsing."""

from app.services.domain.rule_parsing.education import extract_min_degree_level


def test_extract_min_degree_level_handles_abbreviation_formats() -> None:
    level, lines = extract_min_degree_level(
        """
        Qualifications:
        - BS/MS in Computer Science, Engineering, or related discipline.
        - 4-year degree preferred.
        """
    )

    assert level == "bachelor"
    assert lines


def test_extract_min_degree_level_ignores_associate_job_title() -> None:
    level, _ = extract_min_degree_level(
        """
        Associate Director, Platform Engineering
        8+ years of relevant experience in distributed systems.
        """
    )

    assert level == "unknown"


def test_extract_min_degree_level_does_not_treat_ms_office_as_master() -> None:
    level, _ = extract_min_degree_level(
        """
        Requirements:
        - Proficiency in MS Office, Excel, and PowerPoint.
        - 5+ years of experience.
        """
    )

    assert level == "unknown"


def test_extract_min_degree_level_prefers_explicit_degree_over_equivalent_experience() -> None:
    level, _ = extract_min_degree_level(
        """
        Qualifications:
        - Bachelor's degree in Computer Science required.
        - 8+ years of relevant experience or equivalent experience.
        """
    )

    assert level == "bachelor"
