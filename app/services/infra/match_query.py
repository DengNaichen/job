from __future__ import annotations

from typing import Any

import asyncpg

from app.core.config import get_settings


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
    preferred_country_code: str | None = None,
) -> tuple[str, list[object], dict[str, Any]]:
    clauses: list[str] = []
    params: list[object] = []

    if needs_sponsorship:
        clauses.append("sponsorship_not_available <> 'yes'")

    if preferred_country_code:
        placeholder = f"${start_index + len(params)}"
        # Country filter should check the new normalized job_locations -> locations relationship
        # OR fall back to the compatibility `location_country_code` field for jobs not yet backfilled.
        clauses.append(
            f"(EXISTS ("
            f"SELECT 1 FROM job_locations jl "
            f"JOIN locations l ON jl.location_id = l.id "
            f"WHERE jl.job_id = job.id AND l.country_code = {placeholder}"
            f") OR location_country_code = {placeholder})"
        )
        params.append(preferred_country_code)

    if user_degree_rank >= 0:
        placeholder = f"${start_index + len(params)}"
        clauses.append(
            f"(COALESCE(min_degree_rank, -1) < 0 OR COALESCE(min_degree_rank, -1) <= {placeholder})"
        )
        params.append(user_degree_rank)

    return (
        " AND ".join(clauses),
        params,
        {
            "sponsorship_filter_applied": needs_sponsorship,
            "degree_filter_applied": user_degree_rank >= 0,
            "preferred_country_code": preferred_country_code,
            "user_degree_rank": user_degree_rank,
        },
    )


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
            location_city AS city,
            location_region AS region,
            location_country_code AS country_code,
            location_workplace_type AS workplace_type,
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


class MatchCandidateGateway:
    """Infrastructure adapter for match candidate recall."""

    def __init__(
        self,
        *,
        settings_provider=None,
        connect=None,
    ):
        self.settings_provider = settings_provider or get_settings
        self.connect = connect or asyncpg.connect

    async def fetch_candidates(
        self,
        *,
        user_vec_literal: str,
        top_k: int,
        prefilter_sql: str,
        prefilter_params: list[object],
    ) -> list[dict[str, Any]]:
        settings = self.settings_provider()
        dsn = to_asyncpg_dsn(settings.database_url)
        conn = await self.connect(dsn)
        try:
            return await fetch_candidates(
                conn,
                user_vec_literal=user_vec_literal,
                top_k=top_k,
                prefilter_sql=prefilter_sql,
                prefilter_params=prefilter_params,
            )
        finally:
            await conn.close()
