"""Unit tests for match query helpers."""

from __future__ import annotations

import pytest

from app.services.match_query import (
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


def test_build_sql_prefilter_with_sponsorship_and_degree() -> None:
    sql, params, summary = build_sql_prefilter(
        start_index=2,
        needs_sponsorship=True,
        user_degree_rank=3,
    )

    assert "sponsorship_not_available <> 'yes'" in sql
    assert "min_degree_rank" in sql
    assert params == [3]
    assert summary == {
        "sponsorship_filter_applied": True,
        "degree_filter_applied": True,
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
                "location_text": "Toronto, ON",
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
        prefilter_sql="sponsorship_not_available <> 'yes'",
        prefilter_params=[2],
    )

    assert "embedding IS NOT NULL" in fake_conn.query
    assert "COALESCE(structured_jd_version, 0) >= 3" in fake_conn.query
    assert "sponsorship_not_available <> 'yes'" in fake_conn.query
    assert "LIMIT $3" in fake_conn.query
    assert fake_conn.params == ("[0.1,0.2]", 2, 25)
    assert rows[0]["job_id"] == "job-1"
    assert rows[0]["structured_jd"]["required_skills"] == ["Python"]
