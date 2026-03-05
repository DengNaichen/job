"""Unit tests for sponsorship rule parsing."""

from app.services.domain.rule_parsing.sponsorship import extract_sponsorship


def test_extract_sponsorship_normalizes_explicit_boolean_like_values() -> None:
    assert extract_sponsorship("yes") == "yes"
    assert extract_sponsorship("No") == "no"
    assert extract_sponsorship("") == "unknown"


def test_extract_sponsorship_detects_deny_markers() -> None:
    assert extract_sponsorship("Unable to provide visa sponsorship for this role") == "yes"
    assert extract_sponsorship("Sponsorship is not provided") == "yes"


def test_extract_sponsorship_detects_allow_markers() -> None:
    assert extract_sponsorship("Visa sponsorship available for qualified candidates") == "no"
    assert extract_sponsorship("We can sponsor visas") == "no"


def test_extract_sponsorship_prefers_deny_when_conflicting_markers_exist() -> None:
    text = "Sponsorship is not provided for this role, even if sponsorship available elsewhere."
    assert extract_sponsorship(text) == "yes"
