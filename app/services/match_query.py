from __future__ import annotations

from typing import Any

import asyncpg


def to_asyncpg_dsn(sqlalchemy_url: str) -> str:
    if sqlalchemy_url.startswith("postgresql+asyncpg://"):
        return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return sqlalchemy_url


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.9f}" for value in values) + "]"


def build_sql_prefilter(
    *,
    start_index: int,
    needs_sponsorship: bool,
    user_degree_rank: int,
) -> tuple[str, list[object], dict[str, Any]]:
    clauses: list[str] = []
    params: list[object] = []

    if needs_sponsorship:
        clauses.append("sponsorship_not_available <> 'yes'")

    if user_degree_rank >= 0:
        placeholder = f"${start_index + len(params)}"
        clauses.append(
            f"(COALESCE(min_degree_rank, -1) < 0 OR COALESCE(min_degree_rank, -1) <= {placeholder})"
        )
        params.append(user_degree_rank)

    return " AND ".join(clauses), params, {
        "sponsorship_filter_applied": needs_sponsorship,
        "degree_filter_applied": user_degree_rank >= 0,
        "user_degree_rank": user_degree_rank,
    }


async def fetch_candidates(
    conn: asyncpg.Connection,
    *,
    user_vec_literal: str,
    top_k: int,
    prefilter_sql: str,
    prefilter_params: list[object],
) -> list[dict[str, Any]]:
    where_clauses = [
        "embedding IS NOT NULL",
        "COALESCE(structured_jd_version, 0) >= 3",
    ]
    if prefilter_sql:
        where_clauses.append(prefilter_sql)

    params: list[object] = [user_vec_literal, *prefilter_params, top_k]
    limit_placeholder = f"${len(params)}"

    query = f"""
        SELECT
            id AS job_id,
            source,
            title,
            apply_url,
            location_text,
            department,
            team,
            employment_type,
            sponsorship_not_available,
            job_domain_raw,
            job_domain_normalized,
            min_degree_level,
            min_degree_rank,
            structured_jd,
            CASE
                WHEN structured_jd IS NOT NULL AND (structured_jd ->> 'experience_years') ~ '^-?\\d+$'
                THEN (structured_jd ->> 'experience_years')::int
                ELSE NULL
            END AS jd_experience_years,
            (1 - (embedding <=> $1::vector)) AS cosine_score
        FROM job
        WHERE {" AND ".join(where_clauses)}
        ORDER BY embedding <=> $1::vector
        LIMIT {limit_placeholder}
    """

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]
