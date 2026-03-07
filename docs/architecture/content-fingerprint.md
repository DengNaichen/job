# Content Fingerprint Design

This document defines how `job.content_fingerprint` should be generated and used
for reliable incremental downstream refresh (structured parsing, embeddings, and
other content-derived pipelines).

## 1. Why This Exists

`sync_run.updated_count` is a snapshot reconciliation metric, not a semantic
content-change metric. In the current full-snapshot flow, an existing
`external_job_id` is counted as `updated` when it is re-seen and rewritten,
even if content is unchanged.

So `updated_count` cannot be used as the target set for LLM/embedding refresh.
The reliable target selector must be content-diff based.

## 2. Current State

- `job.content_fingerprint` column exists.
- `job_embedding.content_fingerprint` column exists.
- Snapshot embedding refresh already uses fingerprint diff selection
  (`job_embedding.content_fingerprint IS DISTINCT FROM job.content_fingerprint`).
- Current write paths do not compute/populate `job.content_fingerprint`, so the
  diff signal is incomplete.

## 3. Fingerprint Definition (v1)

Fingerprint format:

- `cfp:v1:<sha256_hex>`

Hash input (canonical payload):

- `title` (normalized)
- `description_plain` (normalized)

Canonicalization rules:

- Unicode normalization: NFKC
- Trim leading/trailing whitespace
- Collapse internal whitespace runs to a single space
- Serialize canonical payload as stable JSON (`sort_keys=True`, compact separators)
- Hash bytes as UTF-8 using SHA-256

Notes:

- Do not include volatile fields (`updated_at`, `last_seen_at`, raw payload blobs).
- Keep a version prefix (`v1`) to allow future rule changes (`v2`, `v3`) without ambiguity.

## 4. Write Points (Authoritative)

Fingerprint should be computed in all job write paths:

1. Full snapshot ingest path
   - New row creation path
   - Existing row update path
2. API write path
   - `POST /jobs` (create)
   - `PATCH /jobs/{id}` (update)
3. Any future bulk-import/backfill writer touching `title` or `description_plain`

Computation timing:

- Compute after `description_plain` hydration (`description_html -> description_plain` fallback),
  so both HTML-backed and plain-text-backed inputs converge to the same signal.

## 5. Backfill Plan for Existing Rows

To make incremental refresh reliable, existing rows need one-time backfill:

1. Scan jobs in keyset batches (`ORDER BY id`, `WHERE id > :last_id`).
2. Recompute `content_fingerprint` from current `title + description_plain`.
3. Update only rows whose stored fingerprint differs from recomputed value.
4. Commit in batches.
5. Emit progress metrics:
   - scanned rows
   - updated rows
   - unchanged rows
   - rows with missing embeddable text

## 6. Operational Checks

After rollout and backfill, track these checks:

1. Null coverage

```sql
select
  count(*) as total_jobs,
  count(*) filter (where content_fingerprint is null) as null_fingerprint_jobs
from job;
```

2. Stale or missing active-target embeddings

```sql
select count(*) as missing_or_stale_embeddings
from job j
left join job_embedding je
  on je.job_id = j.id
  and je.embedding_kind = :embedding_kind
  and je.embedding_target_revision = :embedding_target_revision
  and je.embedding_model = :embedding_model
  and je.embedding_dim = :embedding_dim
where j.status = 'open'
  and j.description_plain is not null
  and (
    je.id is null
    or je.content_fingerprint is distinct from j.content_fingerprint
  );
```

3. Fresh active-target embeddings

```sql
select count(*) as fresh_embeddings
from job j
join job_embedding je
  on je.job_id = j.id
  and je.embedding_kind = :embedding_kind
  and je.embedding_target_revision = :embedding_target_revision
  and je.embedding_model = :embedding_model
  and je.embedding_dim = :embedding_dim
where j.status = 'open'
  and j.description_plain is not null
  and je.content_fingerprint is not distinct from j.content_fingerprint;
```

## 7. Non-Goals (v1)

- This spec does not define ranking quality improvements.
- This spec does not require changing snapshot `updated_count` semantics.
- This spec does not require immediate schema changes.

## 8. Success Criteria

- New/updated jobs persist non-null `job.content_fingerprint`.
- One-time backfill reduces historical nulls to near-zero (or explicit known exceptions).
- Embedding refresh candidate selection is driven by fingerprint diff, not snapshot update count.
- Repeat full snapshots with unchanged upstream content produce near-zero incremental
  embedding writes after convergence.
