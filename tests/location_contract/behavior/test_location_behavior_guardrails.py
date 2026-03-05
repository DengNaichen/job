"""Behavior guardrails that must remain stable through contract cutover."""

from app.services.domain.job_location import parse_location_text
from app.services.infra.matching.query import build_sql_prefilter


def test_country_prefilter_sql_semantics_remain_intact() -> None:
    sql, params, summary = build_sql_prefilter(
        start_index=6,
        needs_sponsorship=False,
        user_degree_rank=-1,
        preferred_country_code="US",
    )

    assert "EXISTS (SELECT 1 FROM job_locations jl JOIN locations l" in sql
    assert "l.country_code = $6" in sql
    assert params == ["US"]
    assert summary["preferred_country_code"] == "US"


def test_ambiguous_abbreviation_does_not_force_country() -> None:
    loc = parse_location_text("CA")
    assert loc.country_code is None


def test_multi_country_remote_scope_stays_non_singleton() -> None:
    loc = parse_location_text("Remote - US or Canada")
    assert loc.country_code is None


def test_single_country_remote_scope_can_set_country() -> None:
    loc = parse_location_text("Remote - Canada")
    assert loc.country_code == "CA"
