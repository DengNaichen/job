# Data Model: Embedding Pipeline

**Feature Branch**: `003-embedding-pipeline`  
**Status**: Planned

This document defines the data entities and value objects required for snapshot-aligned embedding generation.

## 1. EmbeddingTarget (value object)

Active identity used to isolate compatible embeddings.

| Field | Type | Description |
|-------|------|-------------|
| `embedding_kind` | string | Embedding purpose identifier (for current scope: job description) |
| `embedding_target_revision` | int | Explicit target revision for controlled rollouts |
| `embedding_model` | string | Normalized provider/model identity |
| `embedding_dim` | int | Vector dimensionality |

Validation rules:
- `embedding_dim > 0`
- `(embedding_kind, embedding_target_revision, embedding_model, embedding_dim)` must be treated as one compatibility key.

## 2. JobEmbeddingArtifact (persisted)

Persisted vector row for one job under one active target.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID/string | Row identity |
| `job_id` | UUID/string | Job FK |
| `embedding_kind` | string | Target field |
| `embedding_target_revision` | int | Target field |
| `embedding_model` | string | Target field |
| `embedding_dim` | int | Target field |
| `embedding` | vector | Numeric vector payload |
| `created_at` | datetime | Insert timestamp |
| `updated_at` | datetime | Last refresh timestamp |

Constraints:
- Unique active-target row per job:
  `(job_id, embedding_kind, embedding_target_revision, embedding_model, embedding_dim)`

State transitions:
- Missing -> Created (first successful generation)
- Created -> Updated (successful refresh for same target)

## 3. SnapshotSyncRun (persisted)

Successful full-source snapshot reconciliation record used as refresh trigger boundary.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID/string | Sync run identity |
| `source_id` | UUID/string | Source FK |
| `status` | enum/string | `running`, `success`, `failed` |
| `started_at` | datetime | Start time |
| `finished_at` | datetime | Completion time |

Trigger rule:
- Embedding refresh orchestration is eligible only when snapshot run status is successful.

## 4. EmbeddingRefreshScope (derived set, not persisted)

Derived job set selected for one refresh pass.

| Field | Type | Description |
|-------|------|-------------|
| `source_id` | string | Source boundary for refresh |
| `job_ids` | list[string] | Jobs eligible in this pass |
| `target` | EmbeddingTarget | Active target used by this pass |
| `snapshot_run_id` | string | Successful run that opened refresh window |

Selection rules:
- Jobs must belong to the source scope of the successful snapshot.
- Jobs must be refresh-eligible under snapshot-aligned policy.
- Closed jobs are excluded from refresh scope.

## Relationships

1. `SnapshotSyncRun (success)` defines refresh window per source.
2. `EmbeddingRefreshScope` is derived from current source job state after reconciliation.
3. Each eligible job maps to at most one `JobEmbeddingArtifact` row per `EmbeddingTarget` due to unique active-target constraint.
