#!/usr/bin/env python3
"""Backfill job embeddings into the dedicated job_embedding store."""

from __future__ import annotations

import argparse
import asyncio
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass
from typing import Sequence

import asyncpg

from app.core.config import get_settings
from app.services.infra.embedding import (
    EmbeddingConfig,
    EmbeddingTargetDescriptor,
    embed_text,
    embed_texts,
    get_embedding_config,
    normalize_embedding_model_identity,
    resolve_active_job_embedding_target,
)

HTML_TAG_RE = re.compile(r"<[^>]+>")
DEFAULT_MAX_EMBED_TEXT_CHARS = 12000


@dataclass(frozen=True)
class JobRow:
    id: str
    title: str
    description: str
    content_fingerprint: str | None


@dataclass(frozen=True)
class LegacyEmbeddingRow:
    id: str
    embedding: list[float]
    embedding_model: str
    content_fingerprint: str | None


@dataclass
class MigrationStats:
    scanned: int = 0
    migrated: int = 0
    skipped_model_mismatch: int = 0
    skipped_dim_mismatch: int = 0


@dataclass
class GenerationStats:
    scanned: int = 0
    considered: int = 0
    generated: int = 0
    failed: int = 0
    skipped_planned_legacy_migration: int = 0


class TpmLimiter:
    """Simple token-per-minute limiter using an in-memory sliding window."""

    def __init__(self, target_tpm: int):
        self.target_tpm = target_tpm
        self._events: deque[tuple[float, int]] = deque()
        self._used_tokens = 0
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int) -> None:
        if self.target_tpm <= 0:
            return

        tokens = max(1, tokens)
        if tokens > self.target_tpm:
            raise ValueError(
                f"Single request estimated tokens ({tokens}) exceed target TPM ({self.target_tpm})"
            )

        while True:
            wait_seconds = 0.0
            async with self._lock:
                now = time.monotonic()
                self._evict_old(now)
                projected = self._used_tokens + tokens
                if projected <= self.target_tpm:
                    self._events.append((now, tokens))
                    self._used_tokens += tokens
                    return
                oldest_ts, _ = self._events[0]
                wait_seconds = max(0.01, 60.0 - (now - oldest_ts))

            await asyncio.sleep(wait_seconds)

    def _evict_old(self, now: float) -> None:
        while self._events and now - self._events[0][0] >= 60.0:
            _, used = self._events.popleft()
            self._used_tokens -= used


def _to_asyncpg_dsn(sqlalchemy_url: str) -> str:
    if sqlalchemy_url.startswith("postgresql+asyncpg://"):
        return sqlalchemy_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return sqlalchemy_url


def _strip_html(value: str) -> str:
    return HTML_TAG_RE.sub(" ", value).replace("\n", " ").strip()


def _make_embedding_text(title: str, description: str, max_chars: int) -> str:
    clean = _strip_html(description)
    text = f"Title: {title}\n\nDescription:\n{clean}"
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(f"{v:.9f}" for v in values) + "]"


def _target_params(target: EmbeddingTargetDescriptor) -> tuple[object, ...]:
    return (
        target.embedding_kind,
        target.embedding_target_revision,
        target.embedding_model,
        target.embedding_dim,
    )


async def _embed_text(
    *,
    embedding_config: EmbeddingConfig,
    dim: int,
    text: str,
    max_retries: int,
) -> list[float]:
    values = await embed_text(
        text,
        config=embedding_config,
        dimensions=dim,
        retries=max_retries,
    )
    if len(values) != dim:
        raise RuntimeError(f"Embedding dim mismatch: expected={dim}, actual={len(values)}")
    return values


def _structured_filter_sql(require_structured: bool, *, alias: str = "j") -> str:
    if not require_structured:
        return ""
    return (
        f"AND {alias}.structured_jd IS NOT NULL AND COALESCE({alias}.structured_jd_version, 0) >= 3"
    )


async def _fetch_generation_batch(
    conn: asyncpg.Connection,
    *,
    target: EmbeddingTargetDescriptor,
    limit: int,
    last_id: str,
    force: bool,
    require_structured: bool,
) -> list[JobRow]:
    stale_filter = (
        ""
        if force
        else "AND (je.id IS NULL OR je.content_fingerprint IS DISTINCT FROM j.content_fingerprint)"
    )
    rows = await conn.fetch(
        f"""
        SELECT
            j.id,
            j.title,
            COALESCE(NULLIF(j.description_plain, ''), NULLIF(j.description_html, '')) AS description,
            j.content_fingerprint
        FROM job j
        LEFT JOIN job_embedding je
          ON je.job_id = j.id
         AND je.embedding_kind = $1
         AND je.embedding_target_revision = $2
         AND je.embedding_model = $3
         AND je.embedding_dim = $4
        WHERE j.id > $5
          AND COALESCE(NULLIF(j.description_plain, ''), NULLIF(j.description_html, '')) IS NOT NULL
          {_structured_filter_sql(require_structured)}
          {stale_filter}
        ORDER BY j.id
        LIMIT $6
        """,
        *_target_params(target),
        last_id,
        limit,
    )
    return [
        JobRow(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            content_fingerprint=row["content_fingerprint"],
        )
        for row in rows
    ]


async def _fetch_legacy_migration_batch(
    conn: asyncpg.Connection,
    *,
    target: EmbeddingTargetDescriptor,
    limit: int,
    last_id: str,
    require_structured: bool,
) -> list[LegacyEmbeddingRow]:
    rows = await conn.fetch(
        f"""
        SELECT
            j.id,
            j.embedding,
            j.embedding_model,
            j.content_fingerprint
        FROM job j
        LEFT JOIN job_embedding je
          ON je.job_id = j.id
         AND je.embedding_kind = $1
         AND je.embedding_target_revision = $2
         AND je.embedding_model = $3
         AND je.embedding_dim = $4
        WHERE j.id > $5
          AND j.embedding IS NOT NULL
          AND j.embedding_model IS NOT NULL
          {_structured_filter_sql(require_structured)}
          AND je.id IS NULL
        ORDER BY j.id
        LIMIT $6
        """,
        *_target_params(target),
        last_id,
        limit,
    )

    parsed: list[LegacyEmbeddingRow] = []
    for row in rows:
        embedding_values = [float(value) for value in row["embedding"]]
        parsed.append(
            LegacyEmbeddingRow(
                id=row["id"],
                embedding=embedding_values,
                embedding_model=row["embedding_model"],
                content_fingerprint=row["content_fingerprint"],
            )
        )
    return parsed


async def _count_pending_generation(
    conn: asyncpg.Connection,
    *,
    target: EmbeddingTargetDescriptor,
    force: bool,
    require_structured: bool,
) -> int:
    stale_filter = (
        ""
        if force
        else "AND (je.id IS NULL OR je.content_fingerprint IS DISTINCT FROM j.content_fingerprint)"
    )
    value = await conn.fetchval(
        f"""
        SELECT count(*)
        FROM job j
        LEFT JOIN job_embedding je
          ON je.job_id = j.id
         AND je.embedding_kind = $1
         AND je.embedding_target_revision = $2
         AND je.embedding_model = $3
         AND je.embedding_dim = $4
        WHERE COALESCE(NULLIF(j.description_plain, ''), NULLIF(j.description_html, '')) IS NOT NULL
          {_structured_filter_sql(require_structured)}
          {stale_filter}
        """,
        *_target_params(target),
    )
    return int(value)


async def _count_fresh_active_rows(
    conn: asyncpg.Connection,
    *,
    target: EmbeddingTargetDescriptor,
    require_structured: bool,
) -> int:
    value = await conn.fetchval(
        f"""
        SELECT count(*)
        FROM job j
        JOIN job_embedding je
          ON je.job_id = j.id
         AND je.embedding_kind = $1
         AND je.embedding_target_revision = $2
         AND je.embedding_model = $3
         AND je.embedding_dim = $4
        WHERE COALESCE(NULLIF(j.description_plain, ''), NULLIF(j.description_html, '')) IS NOT NULL
          {_structured_filter_sql(require_structured)}
          AND je.content_fingerprint IS NOT DISTINCT FROM j.content_fingerprint
        """,
        *_target_params(target),
    )
    return int(value)


async def _count_missing_content_rows(
    conn: asyncpg.Connection,
    *,
    target: EmbeddingTargetDescriptor,
    force: bool,
    require_structured: bool,
) -> int:
    stale_filter = (
        ""
        if force
        else "AND (je.id IS NULL OR je.content_fingerprint IS DISTINCT FROM j.content_fingerprint)"
    )
    value = await conn.fetchval(
        f"""
        SELECT count(*)
        FROM job j
        LEFT JOIN job_embedding je
          ON je.job_id = j.id
         AND je.embedding_kind = $1
         AND je.embedding_target_revision = $2
         AND je.embedding_model = $3
         AND je.embedding_dim = $4
        WHERE COALESCE(NULLIF(j.description_plain, ''), NULLIF(j.description_html, '')) IS NULL
          {_structured_filter_sql(require_structured)}
          {stale_filter}
        """,
        *_target_params(target),
    )
    return int(value)


async def _upsert_active_target_rows(
    conn: asyncpg.Connection,
    *,
    target: EmbeddingTargetDescriptor,
    rows: list[tuple[str, str, str, str | None]],
) -> None:
    if not rows:
        return

    await conn.executemany(
        """
        INSERT INTO job_embedding (
            id,
            job_id,
            embedding_kind,
            embedding_target_revision,
            embedding_model,
            embedding_dim,
            embedding,
            content_fingerprint,
            created_at,
            updated_at
        )
        VALUES (
            $1,
            $2,
            $3,
            $4,
            $5,
            $6,
            $7::vector,
            $8,
            NOW(),
            NOW()
        )
        ON CONFLICT (
            job_id,
            embedding_kind,
            embedding_target_revision,
            embedding_model,
            embedding_dim
        )
        DO UPDATE
        SET embedding = EXCLUDED.embedding,
            content_fingerprint = EXCLUDED.content_fingerprint,
            updated_at = NOW()
        """,
        [
            (
                row_id,
                job_id,
                target.embedding_kind,
                target.embedding_target_revision,
                target.embedding_model,
                target.embedding_dim,
                vector_value,
                content_fingerprint,
            )
            for row_id, job_id, vector_value, content_fingerprint in rows
        ],
    )


async def _migrate_legacy_embeddings(
    conn: asyncpg.Connection,
    *,
    target: EmbeddingTargetDescriptor,
    provider: str,
    batch_size: int,
    require_structured: bool,
    dry_run: bool,
    limit: int | None,
) -> tuple[MigrationStats, set[str]]:
    stats = MigrationStats()
    planned_migrated_job_ids: set[str] = set()
    remaining = limit
    last_id = ""

    while remaining is None or remaining > 0:
        take = batch_size if remaining is None else min(batch_size, remaining)
        rows = await _fetch_legacy_migration_batch(
            conn,
            target=target,
            limit=take,
            last_id=last_id,
            require_structured=require_structured,
        )
        if not rows:
            break

        last_id = rows[-1].id
        stats.scanned += len(rows)

        upsert_rows: list[tuple[str, str, str, str | None]] = []
        for row in rows:
            normalized_legacy_model = normalize_embedding_model_identity(
                provider=provider,
                model=row.embedding_model,
            )
            if normalized_legacy_model != target.embedding_model:
                stats.skipped_model_mismatch += 1
                continue
            if len(row.embedding) != target.embedding_dim:
                stats.skipped_dim_mismatch += 1
                continue

            planned_migrated_job_ids.add(row.id)
            stats.migrated += 1
            upsert_rows.append(
                (
                    str(uuid.uuid4()),
                    row.id,
                    _vector_literal(row.embedding),
                    row.content_fingerprint,
                )
            )

        if upsert_rows and not dry_run:
            await _upsert_active_target_rows(conn, target=target, rows=upsert_rows)

        if remaining is not None:
            remaining -= len(upsert_rows)

    return stats, planned_migrated_job_ids


async def _embed_batch(
    rows: list[JobRow],
    *,
    embedding_config: EmbeddingConfig,
    dim: int,
    concurrency: int,
    api_batch_size: int,
    max_retries: int,
    max_embed_chars: int,
    tpm_limiter: TpmLimiter,
) -> tuple[list[tuple[str, str]], int]:
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one_fallback(
        row: JobRow,
        text: str,
        estimated_tokens: int,
    ) -> tuple[str, str] | Exception:
        try:
            await tpm_limiter.acquire(estimated_tokens)
            async with semaphore:
                vec = await _embed_text(
                    embedding_config=embedding_config,
                    dim=dim,
                    text=text,
                    max_retries=max_retries,
                )
            return (row.id, _vector_literal(vec))
        except Exception as exc:  # noqa: BLE001
            return exc

    updates: list[tuple[str, str]] = []
    failures = 0

    prepared: list[tuple[JobRow, str, int]] = []
    for row in rows:
        text = _make_embedding_text(row.title, row.description, max_chars=max_embed_chars)
        prepared.append((row, text, max(1, len(text) // 4)))

    chunk_size = max(1, api_batch_size)
    for i in range(0, len(prepared), chunk_size):
        chunk = prepared[i : i + chunk_size]
        chunk_rows = [item[0] for item in chunk]
        chunk_texts = [item[1] for item in chunk]
        chunk_tokens = sum(item[2] for item in chunk)

        try:
            await tpm_limiter.acquire(chunk_tokens)
            vectors = await embed_texts(
                chunk_texts,
                config=embedding_config,
                dimensions=dim,
                retries=max_retries,
            )
            if len(vectors) != len(chunk_rows):
                raise RuntimeError(
                    f"Embedding batch size mismatch: expected={len(chunk_rows)}, actual={len(vectors)}"
                )

            for row, vec in zip(chunk_rows, vectors):
                if len(vec) != dim:
                    raise RuntimeError(f"Embedding dim mismatch: expected={dim}, actual={len(vec)}")
                updates.append((row.id, _vector_literal(vec)))

        except Exception:
            fallback_results = await asyncio.gather(
                *(
                    run_one_fallback(row, text, estimated_tokens)
                    for row, text, estimated_tokens in chunk
                )
            )
            for result in fallback_results:
                if isinstance(result, Exception):
                    failures += 1
                    continue
                updates.append(result)

    return updates, failures


async def _assert_embedding_schema(conn: asyncpg.Connection) -> None:
    ext = await conn.fetchval("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    if ext != "vector":
        raise RuntimeError(
            "pgvector extension is missing. Run docker compose with pgvector image and migrate first."
        )

    job_rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'job'
        """
    )
    job_existing = {row["column_name"] for row in job_rows}
    job_required = {
        "id",
        "title",
        "description_plain",
        "description_html",
        "structured_jd",
        "structured_jd_version",
        "content_fingerprint",
        "embedding",
        "embedding_model",
    }
    job_missing = sorted(job_required - job_existing)
    if job_missing:
        raise RuntimeError(
            "Job columns required for embedding backfill are missing: "
            + ",".join(job_missing)
            + ". Run alembic upgrade head first."
        )

    embedding_rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'job_embedding'
        """
    )
    embedding_existing = {row["column_name"] for row in embedding_rows}
    embedding_required = {
        "id",
        "job_id",
        "embedding_kind",
        "embedding_target_revision",
        "embedding_model",
        "embedding_dim",
        "embedding",
        "content_fingerprint",
        "created_at",
        "updated_at",
    }
    embedding_missing = sorted(embedding_required - embedding_existing)
    if embedding_missing:
        raise RuntimeError(
            "job_embedding columns are missing: "
            + ",".join(embedding_missing)
            + ". Run alembic upgrade head first."
        )


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    embedding_config = get_embedding_config()
    if args.model:
        embedding_config = embedding_config.model_copy(update={"model": args.model})
    if not embedding_config.api_key:
        raise RuntimeError(
            "Embedding API key is required. Set EMBEDDING_API_KEY or GEMINI_API_KEY."
        )

    dim = args.dim or settings.embedding_dim
    batch_size = args.batch_size or settings.embedding_batch_size
    if dim <= 0:
        raise ValueError("Embedding dim must be > 0")
    if batch_size <= 0:
        raise ValueError("Batch size must be > 0")
    if args.concurrency <= 0:
        raise ValueError("Concurrency must be > 0")
    if args.api_batch_size <= 0:
        raise ValueError("api_batch_size must be > 0")
    if args.max_embed_chars <= 0:
        raise ValueError("max_embed_chars must be > 0")
    if args.target_tpm < 0:
        raise ValueError("target_tpm must be >= 0")

    target = resolve_active_job_embedding_target(
        config=embedding_config,
        embedding_dim=dim,
    )
    dsn = _to_asyncpg_dsn(settings.database_url)
    tpm_limiter = TpmLimiter(args.target_tpm)

    conn = await asyncpg.connect(dsn)
    try:
        await _assert_embedding_schema(conn)

        fresh_before = await _count_fresh_active_rows(
            conn,
            target=target,
            require_structured=args.require_structured,
        )
        pending_generation_before = await _count_pending_generation(
            conn,
            target=target,
            force=args.force,
            require_structured=args.require_structured,
        )
        missing_content_before = await _count_missing_content_rows(
            conn,
            target=target,
            force=args.force,
            require_structured=args.require_structured,
        )

        print(f"model={target.embedding_model}")
        print(f"embedding_kind={target.embedding_kind}")
        print(f"embedding_target_revision={target.embedding_target_revision}")
        print(f"dim={target.embedding_dim}")
        print(f"batch_size={batch_size}")
        print(f"concurrency={args.concurrency}")
        print(f"api_batch_size={args.api_batch_size}")
        print(f"target_tpm={args.target_tpm}")
        print(f"max_embed_chars={args.max_embed_chars}")
        print(f"require_structured={args.require_structured}")
        print(f"force={args.force}")
        print(f"dry_run={args.dry_run}")
        print(f"already_fresh={fresh_before}")
        print(f"pending_generation={pending_generation_before}")
        print(f"missing_content={missing_content_before}")

        migration_limit = args.limit
        migration_stats, planned_migrated_job_ids = await _migrate_legacy_embeddings(
            conn,
            target=target,
            provider=embedding_config.provider,
            batch_size=batch_size,
            require_structured=args.require_structured,
            dry_run=args.dry_run,
            limit=migration_limit,
        )

        remaining_limit = args.limit
        if remaining_limit is not None:
            remaining_limit = max(0, remaining_limit - migration_stats.migrated)

        print(
            "legacy_migration="
            f"scanned:{migration_stats.scanned}, "
            f"migrated:{migration_stats.migrated}, "
            f"skipped_model_mismatch:{migration_stats.skipped_model_mismatch}, "
            f"skipped_dim_mismatch:{migration_stats.skipped_dim_mismatch}"
        )

        generation_stats = GenerationStats()
        last_id = ""
        target_total = (
            pending_generation_before
            if remaining_limit is None
            else min(pending_generation_before, remaining_limit)
        )

        while remaining_limit is None or remaining_limit > 0:
            take = batch_size if remaining_limit is None else min(batch_size, remaining_limit)
            rows = await _fetch_generation_batch(
                conn,
                target=target,
                limit=take,
                last_id=last_id,
                force=args.force,
                require_structured=args.require_structured,
            )
            if not rows:
                break

            last_id = rows[-1].id
            generation_stats.scanned += len(rows)

            rows_to_process: list[JobRow] = []
            for row in rows:
                if args.dry_run and row.id in planned_migrated_job_ids:
                    generation_stats.skipped_planned_legacy_migration += 1
                    continue
                rows_to_process.append(row)

            if not rows_to_process:
                continue

            updates, failures = await _embed_batch(
                rows_to_process,
                embedding_config=embedding_config,
                dim=target.embedding_dim,
                concurrency=args.concurrency,
                api_batch_size=args.api_batch_size,
                max_retries=args.max_retries,
                max_embed_chars=args.max_embed_chars,
                tpm_limiter=tpm_limiter,
            )

            generation_stats.considered += len(rows_to_process)
            generation_stats.generated += len(updates)
            generation_stats.failed += failures

            if updates and not args.dry_run:
                content_by_job_id = {row.id: row.content_fingerprint for row in rows_to_process}
                upsert_rows = [
                    (
                        str(uuid.uuid4()),
                        job_id,
                        vector_value,
                        content_by_job_id.get(job_id),
                    )
                    for job_id, vector_value in updates
                ]
                await _upsert_active_target_rows(conn, target=target, rows=upsert_rows)

            if remaining_limit is not None:
                remaining_limit -= len(rows_to_process)

            progress = (
                0.0 if target_total == 0 else (generation_stats.considered / target_total) * 100.0
            )
            print(
                f"processed_generation={generation_stats.considered}/{target_total} ({progress:.1f}%), "
                f"batch_success={len(updates)}, batch_failed={failures}, "
                f"total_success={generation_stats.generated}, total_failed={generation_stats.failed}"
            )

        print("=== SUMMARY ===")
        print(f"already_fresh={fresh_before}")
        print(f"legacy_migrated={migration_stats.migrated}")
        print(
            "legacy_skips="
            f"model_mismatch:{migration_stats.skipped_model_mismatch}, "
            f"dim_mismatch:{migration_stats.skipped_dim_mismatch}"
        )
        print(f"generation_considered={generation_stats.considered}")
        print(f"generation_success={generation_stats.generated}")
        print(f"generation_failed={generation_stats.failed}")
        print(
            "dry_run_skipped_due_to_planned_legacy_migration="
            f"{generation_stats.skipped_planned_legacy_migration}"
        )
        print(f"missing_content={missing_content_before}")
        print(f"dry_run={args.dry_run}")

    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Job embeddings using LiteLLM API")
    parser.add_argument(
        "--model",
        default=None,
        help="Embedding model name. Default: env EMBEDDING_MODEL",
    )
    parser.add_argument(
        "--dim",
        type=int,
        default=None,
        help="Embedding dimension. Default: env EMBEDDING_DIM",
    )
    parser.add_argument("--batch-size", type=int, default=None, help="Rows fetched per batch")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent embedding API calls")
    parser.add_argument(
        "--api-batch-size",
        type=int,
        default=16,
        help="Texts per embedding API request",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max retries for transient API errors",
    )
    parser.add_argument(
        "--target-tpm",
        type=int,
        default=0,
        help="Estimated token-per-minute cap. 0 disables limiter.",
    )
    parser.add_argument(
        "--max-embed-chars",
        type=int,
        default=DEFAULT_MAX_EMBED_TEXT_CHARS,
        help="Max chars kept from formatted JD text before embedding.",
    )
    parser.add_argument(
        "--require-structured",
        action="store_true",
        help="Only embed jobs with structured_jd IS NOT NULL.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max rows to process")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute embeddings even when already present",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute embeddings but skip DB writes",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
