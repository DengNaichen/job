# Data Models

Data model design for the job aggregation service.

## Overview

This service contains two core models:

- **Job** - Job posting information, stores data fetched from external sources
- **SyncRun** - Sync run records, tracks execution status of each sync task

## Job Model

Job posting table with multi-source aggregation and intelligent deduplication.

### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `source` | str | Same-source identity key (e.g. `greenhouse:airbnb`, `greenhouse:stripe`) |
| `external_job_id` | str | Job ID from external system |
| `title` | str | Job title |
| `apply_url` | str | Application URL |

### Deduplication Strategy

The system supports multi-level deduplication:

| Field | Purpose |
|-------|---------|
| `source` + `external_job_id` | Unique identifier within one concrete source snapshot stream |
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
| `description_plain` | Plain text job description |
| `raw_payload` | Raw API response, preserves complete information |

### Metadata

| Field | Description |
|-------|-------------|
| `location_text` | Work location |
| `department` | Department |
| `team` | Team |
| `employment_type` | Employment type (full-time, part-time, contract, etc.) |
| `published_at` | Publication time |

---

## SyncRun Model

Sync task record table, tracks execution status and statistics of each sync operation.

### Status Management

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `source` | str | Data source identifier |
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

1. **Preserve Raw Data** - `raw_payload` field saves complete API response for future analysis
2. **Complete Timestamps** - `ingested_at`, `last_seen_at`, `source_updated_at` support full timeline tracking
3. **Same-Source Reconcile First** - `source` is a concrete `platform:identifier` key, so full snapshot sync can safely upsert and immediately close missing jobs
4. **Layered Deduplication** - Same-source dedup is the current foundation; cross-source URL/content dedup remains a later phase
5. **Observability** - `SyncRun` provides detailed sync statistics for monitoring and troubleshooting

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
