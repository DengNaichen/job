"""Unit tests for seniority inference rules."""

from app.services.domain.rule_parsing.seniority import infer_seniority_level


def test_infer_seniority_level_prefers_title_signal_over_years_fallback() -> None:
    assert infer_seniority_level("Principal Engineer", 1) == "principal"
    assert infer_seniority_level("Associate Software Engineer", 10) == "junior"


def test_infer_seniority_level_handles_staff_engineer_as_principal_bucket() -> None:
    assert infer_seniority_level("Staff Engineer", None) == "principal"


def test_infer_seniority_level_uses_years_fallback_boundaries() -> None:
    assert infer_seniority_level(None, 1) == "junior"
    assert infer_seniority_level(None, 5) == "mid"
    assert infer_seniority_level(None, 8) == "senior"


def test_infer_seniority_level_returns_none_when_no_signal_available() -> None:
    assert infer_seniority_level(None, None) is None
