from __future__ import annotations

import asyncpg
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.match import (
    CandidateProfile,
    HardFilterSummary,
    LLMRerankSummary,
    MatchRequest,
    MatchResponse,
    MatchResponseMeta,
    MatchResultItem,
    SQLPrefilterSummary,
    VectorThresholdSummary,
)
from app.services.embedding import embed_text, get_embedding_config
from app.services.llm import get_llm_config
from app.services.llm_match_recommendation import (
    apply_llm_rerank,
    attach_default_llm_fields,
    build_disabled_llm_rerank_summary,
)
from app.services.match_query import (
    build_sql_prefilter,
    fetch_candidates,
    to_asyncpg_dsn,
    vector_literal,
)
from app.services.matching import (
    build_user_embedding_text,
    build_user_skill_tokens,
    filter_match_candidates_by_min_cosine_score,
    hard_filter_match_candidates,
    infer_needs_sponsorship,
    infer_user_degree_rank,
    infer_user_job_domain,
    infer_user_seniority_level,
    rerank_match_candidates,
    to_int,
)


class MatchServiceError(Exception):
    """Base exception for matching service failures."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class CandidateProfileValidationError(MatchServiceError):
    """Raised when candidate input cannot be parsed into the typed schema."""

    def __init__(self, message: str):
        super().__init__("CANDIDATE_PROFILE_INVALID", message)


class MatchQueryError(MatchServiceError):
    """Raised when the candidate recall query fails."""

    def __init__(self, message: str = "Failed to fetch match candidates"):
        super().__init__("MATCH_QUERY_ERROR", message)


class LLMRerankConfigurationError(MatchServiceError):
    """Raised when LLM rerank is requested without valid LLM configuration."""

    def __init__(self, message: str = "LLM rerank requested but LLM is not configured"):
        super().__init__("LLM_RERANK_CONFIG_ERROR", message)


def validate_candidate_profile(candidate_data: dict[str, object]) -> CandidateProfile:
    """Parse raw user JSON into the typed candidate schema."""

    try:
        return CandidateProfile.model_validate(candidate_data)
    except ValidationError as exc:
        raise CandidateProfileValidationError(str(exc)) from exc


class MatchExperimentService:
    """Application service for the offline match experiment pipeline."""

    async def run(self, request: MatchRequest) -> MatchResponse:
        legacy_user_data = request.candidate.to_matching_payload()
        user_years = request.candidate.total_years_experience
        user_years_for_rerank = to_int(request.candidate.total_years_experience, default=0)
        user_degree_rank = infer_user_degree_rank(legacy_user_data)
        needs_sponsorship = infer_needs_sponsorship(
            legacy_user_data,
            request.needs_sponsorship_override,
        )
        user_skill_tokens = build_user_skill_tokens(legacy_user_data)
        user_domain = infer_user_job_domain(legacy_user_data)
        user_seniority = infer_user_seniority_level(legacy_user_data)

        user_text = build_user_embedding_text(
            legacy_user_data,
            max_chars=request.max_user_chars,
        )
        settings = get_settings()
        user_embedding = await embed_text(
            user_text,
            config=get_embedding_config(),
            dimensions=settings.embedding_dim,
        )
        user_vec_literal = vector_literal(user_embedding)
        sql_prefilter, sql_prefilter_params, sql_prefilter_summary = build_sql_prefilter(
            start_index=2,
            needs_sponsorship=needs_sponsorship,
            user_degree_rank=user_degree_rank,
        )

        dsn = to_asyncpg_dsn(settings.database_url)
        try:
            conn = await asyncpg.connect(dsn)
            try:
                candidate_rows = await fetch_candidates(
                    conn,
                    user_vec_literal=user_vec_literal,
                    top_k=request.top_k,
                    prefilter_sql=sql_prefilter,
                    prefilter_params=sql_prefilter_params,
                )
            finally:
                await conn.close()
        except Exception as exc:
            raise MatchQueryError() from exc

        vector_filtered_rows, vector_threshold_summary = (
            filter_match_candidates_by_min_cosine_score(
                candidate_rows,
                min_cosine_score=request.min_cosine_score,
            )
        )
        hard_filtered_rows, hard_filter_summary = hard_filter_match_candidates(
            vector_filtered_rows,
            needs_sponsorship=False,
            user_years=user_years,
            user_degree_rank=-1,
            max_experience_gap=request.experience_buffer_years,
        )
        context_by_job_id = {
            str(row["job_id"]): row for row in hard_filtered_rows if row.get("job_id") is not None
        }

        ranked = rerank_match_candidates(
            hard_filtered_rows,
            user_years=user_years_for_rerank,
            user_degree_rank=user_degree_rank,
            user_skill_tokens=user_skill_tokens,
            user_domain=user_domain,
            user_seniority=user_seniority,
        )

        if request.enable_llm_rerank:
            llm_config = get_llm_config()
            if llm_config.provider != "ollama" and not llm_config.api_key:
                raise LLMRerankConfigurationError()
            ranked, llm_rerank_summary = await apply_llm_rerank(
                ranked,
                user_data=legacy_user_data,
                context_by_job_id=context_by_job_id,
                llm_top_n=request.llm_top_n,
                concurrency=request.llm_concurrency,
            )
        else:
            ranked = attach_default_llm_fields(ranked)
            llm_rerank_summary = build_disabled_llm_rerank_summary()

        top_results = ranked[: request.top_n]

        return MatchResponse(
            meta=MatchResponseMeta(
                user_json=request.user_json,
                needs_sponsorship=needs_sponsorship,
                user_total_years_experience=user_years,
                user_degree_rank=user_degree_rank,
                user_skill_count=len(user_skill_tokens),
                user_domain=user_domain,
                user_seniority=user_seniority,
                top_k=request.top_k,
                top_n=request.top_n,
                sql_prefilter=SQLPrefilterSummary.model_validate(sql_prefilter_summary),
                candidates_after_sql_prefilter=len(candidate_rows),
                vector_threshold_summary=VectorThresholdSummary.model_validate(
                    vector_threshold_summary
                ),
                candidates_after_vector_threshold=len(vector_filtered_rows),
                candidates_before_hard_filter=len(vector_filtered_rows),
                candidates_after_hard_filter=len(hard_filtered_rows),
                hard_filter_summary=HardFilterSummary.model_validate(hard_filter_summary),
                llm_rerank_summary=LLMRerankSummary.model_validate(llm_rerank_summary),
                results_returned=len(top_results),
            ),
            results=[MatchResultItem.model_validate(item) for item in top_results],
        )
