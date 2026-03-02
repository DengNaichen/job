# Data Models

Data model design for the job aggregation service.

## Overview

This service contains three core models:

- **Source** - Upstream source configuration, keyed by `platform + identifier`
- **Job** - Job posting information, stores data fetched from external sources. Linked to Source via `source_id` (authoritative FK)
- **JobEmbedding** - Dedicated persisted vector store for one job + active embedding target
- **SyncRun** - Sync run records, tracks execution status of each sync task. Linked to Source via `source_id` (authoritative FK)

## Job Model

Job posting table with multi-source aggregation and intelligent deduplication.

### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `source_id` | UUID FK | **Authoritative owner key** — FK to `sources.id`. |
| `external_job_id` | str | Job ID from external system |
| `title` | str | Job title |
| `apply_url` | str | Application URL |

### Deduplication Strategy

The system supports multi-level deduplication:

| Field | Purpose |
|-------|---------|
| `source_id` + `external_job_id` | **Authoritative** unique identity within one source |
| `normalized_apply_url` | Cross-source URL deduplication |
| `content_fingerprint` | Content hash for detecting job content changes |
| `dedupe_group_id` | Custom deduplication group for advanced dedup logic |

### Status Tracking

| Field | Description |
|-------|-------------|
| `status` | Job status: `open` or `closed` |
| `last_seen_at` | Last time seen in a successful full snapshot sync |
| `source_updated_at` | Update time in data source |

### Content Storage

| Field | Description |
|-------|-------------|
| `description_html` | HTML formatted job description |
| `description_html_key` / `description_html_hash` | Supabase Storage pointer for gzip-compressed HTML |
| `description_plain` | Plain text job description |
| `raw_payload` | Raw API response, preserves complete information |
| `raw_payload_key` / `raw_payload_hash` | Supabase Storage pointer for gzip-compressed raw payload JSON |

### Metadata

| Field | Description |
|-------|-------------|
| `locations` / `job_locations` | Authoritative structured location storage (city/region/country + workplace metadata). Raw display text lives in `job_locations.source_raw`. |
| `department` | Department |
| `team` | Team |
| `employment_type` | Employment type (full-time, part-time, contract, etc.) |
| `published_at` | Publication time |

---

## JobEmbedding Model

Persisted embedding rows are isolated from `job` so model/version rollouts do not mutate the hot job row.

| Field | Description |
|-------|-------------|
| `job_id` | FK to `job.id` |
| `embedding_kind` | Retrieval purpose identifier (for this rollout: job description recall) |
| `embedding_target_revision` | Explicit target revision for controlled cutovers |
| `embedding_model` | Normalized model identity (for example `gemini/gemini-embedding-001`) |
| `embedding_dim` | Vector dimension metadata for target isolation |
| `embedding` | Persisted vector payload |
| `content_fingerprint` | Content state used for stale/fresh detection |
| `created_at` / `updated_at` | Lifecycle timestamps |

One row is unique per `job_id + embedding_kind + embedding_target_revision + embedding_model + embedding_dim`.

---

## SyncRun Model

Sync task record table, tracks execution status and statistics of each sync operation.

### Status Management

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `source_id` | UUID FK | **Authoritative owner key** — FK to `sources.id`. |
| `status` | enum | `running` / `success` / `failed` |
| `started_at` | datetime | Start time |
| `finished_at` | datetime | End time (nullable) |
| `error_summary` | str | Error summary (recorded on failure) |

### Statistics Funnel

Key metrics during sync process:

```
fetched_count     → Raw count from API
mapped_count      → Successfully mapped to model
unique_count      → Unique count after deduplication
inserted_count    → Newly inserted to database
updated_count     → Updated existing records
closed_count      → Marked as closed
failed_count      → Failed to process
```

Deduplication breakdown:

| Field | Description |
|-------|-------------|
| `deduped_by_external_id` | Deduplicated by external_job_id |
| `deduped_by_apply_url` | Deduplicated by apply_url |

---

## Design Principles

1. **Preserve Raw Data** - `raw_payload` stays available during transition while the large body can move to object storage
2. **Complete Timestamps** - `ingested_at`, `last_seen_at`, `source_updated_at` support full timeline tracking
3. **Authoritative Source Ownership** - `source_id` (FK to `sources.id`) is the owner key for job and sync-run records.
4. **Same-Source Reconcile** - Full snapshot sync uses `source_id` to upsert and close missing jobs
5. **Layered Deduplication** - Same-source dedup is the current foundation; cross-source URL/content dedup remains a later phase
6. **Observability** - `SyncRun` provides detailed sync statistics for monitoring and troubleshooting
7. **Source Lifecycle Guardrails** - Sources referenced by jobs or sync runs cannot be deleted; platform/identifier mutations are blocked when references exist

## Enum Types

### JobStatus

```python
class JobStatus(str, enum.Enum):
    open = "open"      # Job is open
    closed = "closed"  # Job is closed
```

### SyncRunStatus

```python
class SyncRunStatus(str, enum.Enum):
    running = "running"  # Sync in progress
    success = "success"  # Sync succeeded
    failed = "failed"    # Sync failed
```

### WorkplaceType

```python
class WorkplaceType(str, enum.Enum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    unknown = "unknown"
```
