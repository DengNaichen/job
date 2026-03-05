# Embedding Retry and Dimensions Fallback Rules

This note documents the runtime behavior of `app.services.infra.embedding.embed_texts(...)`.

## Request Assembly
- Request kwargs are built in one place (`_build_embedding_kwargs`) using:
  - `model`
  - `input`
  - `custom_llm_provider`
  - `api_key`
  - normalized `api_base`
  - `timeout`
  - optional `dimensions`

## Dimensions Fallback
- If `dimensions` is provided, the first request includes it.
- If provider failure clearly indicates unsupported dimensions, one immediate fallback request is sent without `dimensions`.
- After dimensions are disabled once, later retry attempts continue without `dimensions`.

## Retry Policy
- `retries` keeps the existing meaning: total attempts are `retries + 1`.
- Retries are only used for transient failures (timeout, connection, rate-limit, service-unavailable, and known transient HTTP status codes).
- Non-transient failures fail fast without extra retries.

## Response Validation
- Embedding responses are validated centrally in `parsing.py`:
  - `response.data` must be a non-empty list.
  - each item must contain a non-empty embedding list.
  - values are coerced to `float`; non-numeric values fail explicitly.
  - optional vector count and dimension checks are enforced when requested.
- Validation errors include provider/model context for faster diagnostics.

## Snapshot-Aligned Refresh Semantics
- Embedding refresh orchestration is driven by successful full snapshot sync outcomes.
- Refresh scope is source-scoped and restricted to open jobs only (closed jobs are excluded).
- Refresh reads only active-target-missing or fingerprint-stale rows for that source.
- Writes use active-target upsert semantics in `job_embedding`, so repeated successful snapshots remain idempotent.
