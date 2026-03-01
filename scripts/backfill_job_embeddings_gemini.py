#!/usr/bin/env python3
"""Backfill job embeddings using a LiteLLM embedding provider."""

from __future__ import annotations

import argparse
import asyncio
import re
import time
from collections import deque
from dataclasses import dataclass
from typing import Sequence

import asyncpg

from app.core.config import get_settings
from app.services.infra.embedding import (
    EmbeddingConfig,
    embed_text,
    embed_texts,
    get_embedding_config,
    resolve_embedding_model_name,
)

HTML_TAG_RE = re.compile(r"<[^>]+>")
DEFAULT_MAX_EMBED_TEXT_CHARS = 12000


@dataclass
class JobRow:
    id: str
    title: str
    description: str


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


async def _fetch_jobs_batch(
    conn: asyncpg.Connection,
    *,
    model: str,
    limit: int,
    offset: int,
    force: bool,
    require_structured: bool,
) -> list[JobRow]:
    structured_filter = (
        "AND structured_jd IS NOT NULL AND COALESCE(structured_jd_version, 0) >= 3"
        if require_structured
        else ""
    )

    if force:
        rows = await conn.fetch(
            f"""
            SELECT id, title,
                   COALESCE(NULLIF(description_plain, ''), NULLIF(description_html, '')) AS description
            FROM job
            WHERE COALESCE(NULLIF(description_plain, ''), NULLIF(description_html, '')) IS NOT NULL
              {structured_filter}
            ORDER BY updated_at, id
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    else:
        rows = await conn.fetch(
            f"""
            SELECT id, title,
                   COALESCE(NULLIF(description_plain, ''), NULLIF(description_html, '')) AS description
            FROM job
            WHERE COALESCE(NULLIF(description_plain, ''), NULLIF(description_html, '')) IS NOT NULL
              {structured_filter}
              AND (embedding IS NULL OR embedding_model IS DISTINCT FROM $1)
            ORDER BY updated_at, id
            LIMIT $2 OFFSET $3
            """,
            model,
            limit,
            offset,
        )

    return [JobRow(id=r["id"], title=r["title"], description=r["description"]) for r in rows]


async def _count_jobs(
    conn: asyncpg.Connection,
    *,
    model: str,
    force: bool,
    require_structured: bool,
) -> int:
    structured_filter = (
        "AND structured_jd IS NOT NULL AND COALESCE(structured_jd_version, 0) >= 3"
        if require_structured
        else ""
    )

    if force:
        value = await conn.fetchval(
            f"""
            SELECT count(*)
            FROM job
            WHERE COALESCE(NULLIF(description_plain, ''), NULLIF(description_html, '')) IS NOT NULL
              {structured_filter}
            """
        )
    else:
        value = await conn.fetchval(
            f"""
            SELECT count(*)
            FROM job
            WHERE COALESCE(NULLIF(description_plain, ''), NULLIF(description_html, '')) IS NOT NULL
              {structured_filter}
              AND (embedding IS NULL OR embedding_model IS DISTINCT FROM $1)
            """,
            model,
        )
    return int(value)


async def _assert_embedding_schema(conn: asyncpg.Connection) -> None:
    ext = await conn.fetchval("SELECT extname FROM pg_extension WHERE extname = 'vector'")
    if ext != "vector":
        raise RuntimeError(
            "pgvector extension is missing. Run docker compose with pgvector image and migrate first."
        )

    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'job'
        """
    )
    existing = {r["column_name"] for r in rows}
    required = {"embedding", "embedding_model", "embedding_updated_at"}
    missing = sorted(required - existing)
    if missing:
        raise RuntimeError(
            "Job embedding columns are missing: "
            + ",".join(missing)
            + ". Run alembic upgrade head first."
        )


async def _embed_batch(
    rows: list[JobRow],
    *,
    embedding_config: EmbeddingConfig,
    model: str,
    dim: int,
    concurrency: int,
    api_batch_size: int,
    max_retries: int,
    max_embed_chars: int,
    tpm_limiter: TpmLimiter,
) -> tuple[list[tuple[str, str, str]], int]:
    semaphore = asyncio.Semaphore(concurrency)

    async def run_one_fallback(
        row: JobRow, text: str, estimated_tokens: int
    ) -> tuple[str, str, str] | Exception:
        try:
            await tpm_limiter.acquire(estimated_tokens)
            async with semaphore:
                vec = await _embed_text(
                    embedding_config=embedding_config,
                    dim=dim,
                    text=text,
                    max_retries=max_retries,
                )
            return (row.id, _vector_literal(vec), model)
        except Exception as exc:  # noqa: BLE001
            return exc

    updates: list[tuple[str, str, str]] = []
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
                updates.append((row.id, _vector_literal(vec), model))

        except Exception:
            fallback_results = await asyncio.gather(
                *(
                    run_one_fallback(row, text, estimated_tokens)
                    for row, text, estimated_tokens in chunk
                )
            )
            for res in fallback_results:
                if isinstance(res, Exception):
                    failures += 1
                    continue
                updates.append(res)

    return updates, failures


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    embedding_config = get_embedding_config()
    if args.model:
        embedding_config = embedding_config.model_copy(update={"model": args.model})
    if not embedding_config.api_key:
        raise RuntimeError(
            "Embedding API key is required. Set EMBEDDING_API_KEY or GEMINI_API_KEY."
        )

    model = resolve_embedding_model_name(embedding_config)
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

    dsn = _to_asyncpg_dsn(settings.database_url)
    tpm_limiter = TpmLimiter(args.target_tpm)

    conn = await asyncpg.connect(dsn)
    try:
        await _assert_embedding_schema(conn)
        total_pending = await _count_jobs(
            conn,
            model=model,
            force=args.force,
            require_structured=args.require_structured,
        )
        target_total = total_pending if args.limit is None else min(total_pending, args.limit)

        print(f"model={model}")
        print(f"dim={dim}")
        print(f"batch_size={batch_size}")
        print(f"concurrency={args.concurrency}")
        print(f"api_batch_size={args.api_batch_size}")
        print(f"target_tpm={args.target_tpm}")
        print(f"max_embed_chars={args.max_embed_chars}")
        print(f"require_structured={args.require_structured}")
        print(f"force={args.force}")
        print(f"dry_run={args.dry_run}")
        print(f"pending={total_pending}")
        print(f"target={target_total}")

        processed = 0
        success = 0
        failed = 0

        while processed < target_total:
            remaining = target_total - processed
            take = min(batch_size, remaining)

            rows = await _fetch_jobs_batch(
                conn,
                model=model,
                limit=take,
                offset=processed if (args.force or args.dry_run) else 0,
                force=args.force,
                require_structured=args.require_structured,
            )
            if not rows:
                break

            updates, failures = await _embed_batch(
                rows,
                embedding_config=embedding_config,
                model=model,
                dim=dim,
                concurrency=args.concurrency,
                api_batch_size=args.api_batch_size,
                max_retries=args.max_retries,
                max_embed_chars=args.max_embed_chars,
                tpm_limiter=tpm_limiter,
            )

            if updates and not args.dry_run:
                await conn.executemany(
                    """
                    UPDATE job
                    SET embedding = $2::vector,
                        embedding_model = $3,
                        embedding_updated_at = NOW()
                    WHERE id = $1
                    """,
                    updates,
                )

            processed += len(rows)
            success += len(updates)
            failed += failures

            progress = 0.0 if target_total == 0 else (processed / target_total) * 100.0
            print(
                f"processed={processed}/{target_total} ({progress:.1f}%), "
                f"batch_success={len(updates)}, batch_failed={failures}, "
                f"total_success={success}, total_failed={failed}"
            )

        print("=== SUMMARY ===")
        print(f"processed={processed}")
        print(f"success={success}")
        print(f"failed={failed}")

    finally:
        await conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill Job embeddings using LiteLLM API")
    parser.add_argument(
        "--model", default=None, help="Embedding model name. Default: env EMBEDDING_MODEL"
    )
    parser.add_argument(
        "--dim", type=int, default=None, help="Embedding dimension. Default: env EMBEDDING_DIM"
    )
    parser.add_argument("--batch-size", type=int, default=None, help="Rows fetched per batch")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent embedding API calls")
    parser.add_argument(
        "--api-batch-size", type=int, default=16, help="Texts per embedding API request"
    )
    parser.add_argument(
        "--max-retries", type=int, default=3, help="Max retries for transient API errors"
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
        "--force", action="store_true", help="Recompute embeddings even when already present"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Compute embeddings but skip DB writes"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
