"""Unit tests for match query helpers."""

from __future__ import annotations

import pytest

from app.services.infra.matching.query import (
    build_sql_prefilter,
    fetch_candidates,
    to_asyncpg_dsn,
    vector_literal,
)


class _FakeConnection:
    def __init__(self, rows: list[dict[str, object]]):
        self.rows = rows
        self.query: str | None = None
        self.params: tuple[object, ...] | None = None

    async def fetch(self, query: str, *params: object):  # noqa: ANN002
        self.query = query
        self.params = params
        return self.rows


def test_to_asyncpg_dsn_rewrites_sqlalchemy_driver() -> None:
    assert (
        to_asyncpg_dsn("postgresql+asyncpg://postgres:postgres@localhost:5434/job_db")
        == "postgresql://postgres:postgres@localhost:5434/job_db"
    )
    assert (
        to_asyncpg_dsn("postgresql://postgres@localhost/job_db")
        == "postgresql://postgres@localhost/job_db"
    )


def test_vector_literal_formats_values() -> None:
    assert vector_literal([0.1, 0.2, 0.3]) == "[0.100000000,0.200000000,0.300000000]"


def test_build_sql_prefilter_with_country_sponsorship_and_degree() -> None:
    sql, params, summary = build_sql_prefilter(
        start_index=2,
        needs_sponsorship=True,
        user_degree_rank=3,
        preferred_country_code="US",
    )

    assert "sponsorship_not_available <> 'yes'" in sql
    assert "EXISTS (SELECT 1 FROM job_locations jl JOIN locations l" in sql
    assert "l.country_code = $2" in sql
    assert "jl.job_id = j.id" in sql
    assert "min_degree_rank" in sql
    assert params == ["US", 3]
    assert summary == {
        "sponsorship_filter_applied": True,
        "degree_filter_applied": True,
        "preferred_country_code": "US",
        "user_degree_rank": 3,
    }


def test_build_sql_prefilter_omits_degree_when_unknown() -> None:
    sql, params, summary = build_sql_prefilter(
        start_index=2,
        needs_sponsorship=False,
        user_degree_rank=-1,
    )

    assert sql == ""
    assert params == []
    assert summary == {
        "sponsorship_filter_applied": False,
        "degree_filter_applied": False,
        "preferred_country_code": None,
        "user_degree_rank": -1,
    }


def test_build_sql_prefilter_with_only_country() -> None:
    sql, params, summary = build_sql_prefilter(
        start_index=2,
        needs_sponsorship=False,
        user_degree_rank=-1,
        preferred_country_code="CA",
    )

    assert "sponsorship_not_available" not in sql
    assert "l.country_code = $2" in sql
    assert params == ["CA"]
    assert summary == {
        "sponsorship_filter_applied": False,
        "degree_filter_applied": False,
        "preferred_country_code": "CA",
        "user_degree_rank": -1,
    }


@pytest.mark.asyncio
async def test_fetch_candidates_keeps_match_constraints_and_fields() -> None:
    fake_conn = _FakeConnection(
        [
            {
                "job_id": "job-1",
                "source": "greenhouse",
                "title": "Analyst",
                "apply_url": "https://example.com/job-1",
                "locations": [
                    {
                        "source_raw": "Toronto, ON",
                        "city": "Toronto",
                        "region": "Ontario",
                        "country_code": "CA",
                        "workplace_type": "hybrid",
                        "is_primary": True,
                    }
                ],
                "department": "Analytics",
                "team": "BI",
                "employment_type": "full-time",
                "sponsorship_not_available": "unknown",
                "job_domain_raw": None,
                "job_domain_normalized": "data_ai",
                "min_degree_level": "bachelor",
                "min_degree_rank": 2,
                "structured_jd": {"required_skills": ["Python"]},
                "jd_experience_years": 3,
                "cosine_score": 0.88,
            }
        ]
    )

    rows = await fetch_candidates(
        fake_conn,
        user_vec_literal="[0.1,0.2]",
        top_k=25,
        prefilter_sql=(
            "j.sponsorship_not_available <> 'yes' "
            "AND EXISTS (SELECT 1 FROM job_locations jl JOIN locations l "
            "ON jl.location_id = l.id WHERE jl.job_id = j.id AND l.country_code = $6)"
        ),
        prefilter_params=["US"],
        embedding_kind="job_description",
        embedding_target_revision=2,
        embedding_model="gemini/gemini-embedding-001",
        embedding_dim=1024,
    )

    assert fake_conn.query is not None
    assert "je.embedding IS NOT NULL" in fake_conn.query
    assert "loc_payload.locations AS locations" in fake_conn.query
    assert "LEFT JOIN LATERAL" in fake_conn.query
    assert "jsonb_build_object(" in fake_conn.query
    assert "COALESCE(j.structured_jd_version, 0) >= 3" in fake_conn.query
    assert "j.sponsorship_not_available <> 'yes'" in fake_conn.query
    assert "JOIN job_embedding je ON j.id = je.job_id" in fake_conn.query
    assert "LIMIT $7" in fake_conn.query
    assert fake_conn.params == (
        "[0.1,0.2]",
        "job_description",
        2,
        "gemini/gemini-embedding-001",
        1024,
        "US",
        25,
    )
    assert rows[0]["job_id"] == "job-1"
    assert rows[0]["locations"][0]["country_code"] == "CA"
