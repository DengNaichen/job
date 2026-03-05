"""Unit tests for experience rule parsing."""

from app.services.domain.rule_parsing.experience import extract_experience


def test_extract_experience_returns_max_years_and_first_two_unique_lines() -> None:
    years, lines = extract_experience(
        """
        We need 3-5 years of relevant experience in backend systems.
        We need 3-5 years of relevant experience in backend systems.
        Nice to have: 6+ years of leadership experience.
        Strong background with 8 years in distributed systems.
        """
    )

    assert years == 8
    assert len(lines) == 2
    assert lines[0] == "We need 3-5 years of relevant experience in backend systems."
    assert lines[1] == "Nice to have: 6+ years of leadership experience."


def test_extract_experience_ignores_year_lines_without_experience_context() -> None:
    years, lines = extract_experience(
        """
        5+ years with Python and SQL.
        3-5 years building APIs.
        """
    )

    assert years is None
    assert lines == []


def test_extract_experience_returns_none_when_no_numeric_years_present() -> None:
    years, lines = extract_experience(
        """
        Prior experience in distributed systems is preferred.
        Relevant background in platform engineering.
        """
    )

    assert years is None
    assert lines == []


def test_extract_experience_handles_single_value_years() -> None:
    years, lines = extract_experience("Minimum 4 years of relevant experience required.")

    assert years == 4
    assert lines == ["Minimum 4 years of relevant experience required."]
