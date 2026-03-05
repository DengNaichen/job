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
        # Country filter checks normalized job_locations -> locations only.
        clauses.append(
            f"(EXISTS ("
            f"SELECT 1 FROM job_locations jl "
            f"JOIN locations l ON jl.location_id = l.id "
            f"WHERE jl.job_id = j.id AND l.country_code = {placeholder}"
            f"))"
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
    embedding_kind: str,
    embedding_target_revision: int,
    embedding_model: str,
    embedding_dim: int,
) -> list[dict[str, Any]]:
    where_clauses = [
        "je.embedding IS NOT NULL",
        "COALESCE(j.structured_jd_version, 0) >= 3",
        "je.embedding_kind = $2",
        "je.embedding_target_revision = $3",
        "je.embedding_model = $4",
        "je.embedding_dim = $5",
    ]
    if prefilter_sql:
        where_clauses.append(prefilter_sql)

    params: list[object] = [
        user_vec_literal,
        embedding_kind,
        embedding_target_revision,
        embedding_model,
        embedding_dim,
        *prefilter_params,
        top_k,
    ]
    limit_placeholder = f"${len(params)}"
    query = f"""
        SELECT
            j.id AS job_id,
            (s.platform::text || ':' || s.identifier) AS source,
            j.title,
            j.apply_url,
            loc_payload.locations AS locations,
            j.department,
            j.team,
            j.employment_type,
            j.sponsorship_not_available,
            j.job_domain_raw,
            j.job_domain_normalized,
            j.min_degree_level,
            j.min_degree_rank,
            j.structured_jd,
            CASE
                WHEN j.structured_jd IS NOT NULL AND (j.structured_jd ->> 'experience_years') ~ '^-?\\d+$'
                THEN (j.structured_jd ->> 'experience_years')::int
                ELSE NULL
            END AS jd_experience_years,
            (1 - (je.embedding <=> $1::vector)) AS cosine_score
        FROM job j
        JOIN sources s ON s.id = j.source_id
        JOIN job_embedding je ON j.id = je.job_id
        LEFT JOIN LATERAL (
            SELECT COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'source_raw', jl.source_raw,
                        'workplace_type', jl.workplace_type,
                        'remote_scope', jl.remote_scope,
                        'is_primary', jl.is_primary,
                        'city', l.city,
                        'region', l.region,
                        'country_code', l.country_code,
                        'display_name', l.display_name
                    )
                    ORDER BY jl.is_primary DESC, jl.created_at ASC
                ),
                '[]'::jsonb
            ) AS locations
            FROM job_locations jl
            LEFT JOIN locations l ON l.id = jl.location_id
            WHERE jl.job_id = j.id
        ) AS loc_payload ON TRUE
        WHERE {" AND ".join(where_clauses)}
        ORDER BY je.embedding <=> $1::vector
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
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
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
                embedding_kind=embedding_kind,
                embedding_target_revision=embedding_target_revision,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
            )
        finally:
            await conn.close()
