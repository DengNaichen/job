# JobX Onboarding Guide

## Overview

JobX ingests job postings from public career pages (Greenhouse, Lever, Ashby, etc.), normalizes them into a standard schema, and stores them in **Firestore**. This document covers how to run the ingest pipeline, what data lives where, and all the settings you can tweak.

---

## Firestore Collections

The database has 5 collections:

### `sources`
Companies you want to track. Each document represents one company on one platform.

| Field | Description |
|-------|-------------|
| `name` | Display name (e.g. "Anthropic") |
| `name_normalized` | Lowercase name for dedup lookups |
| `platform` | Which ATS platform (`greenhouse`, `lever`, `ashby`, etc.) |
| `identifier` | The company's slug on that platform (e.g. `anthropic`) |
| `enabled` | Whether this source is included in scheduled ingests |
| `notes` | Optional freeform notes |
| `created_at` / `updated_at` | Timestamps |

### `jobs`
The core data. Every job posting that has been ingested lives here.

| Field | Description |
|-------|-------------|
| `source_id` | Links back to the source that owns this job |
| `external_job_id` | The job's ID on the original platform (used for dedup) |
| `title` | Job title |
| `department` | Department or team name |
| `apply_url` | Direct link to the application page |
| `description_plain` | Plain-text version of the job description |
| `description_html_key` / `description_html_hash` | Blob storage pointers (not used in Firestore-only mode) |
| `status` | `open` or `closed` — closed means the job disappeared from the board |
| `last_seen_at` | Last time this job appeared in a fetch |
| `location_raw` | The raw location string from the platform |
| `primary_location_id` | Links to the resolved location in the `locations` collection |
| `created_at` / `updated_at` | Timestamps |

### `locations`
Normalized location records. Multiple jobs can share the same location.

| Field | Description |
|-------|-------------|
| `canonical_key` | Unique key like `us-ca-san-francisco` or `in-bangalore` |
| `display_name` | Human-readable name (e.g. "San Francisco, CA, US") |
| `country_code` | ISO country code (e.g. `US`, `IN`) |
| `region` | State/province |
| `city` | City name |
| `is_remote` | Whether this is a remote position |

### `job_locations`
Join collection linking jobs to locations (a job can have multiple locations).

| Field | Description |
|-------|-------------|
| `job_id` | References a document in `jobs` |
| `location_id` | References a document in `locations` |
| `is_primary` | Whether this is the job's primary location |
| `source` | How the location was determined (e.g. `parsed`, `structured_jd`) |

### `sync_runs`
Audit log of every ingest run. Useful for debugging and monitoring.

| Field | Description |
|-------|-------------|
| `source_id` | Which source was synced |
| `status` | `running`, `success`, or `failed` |
| `started_at` / `finished_at` | Timing |
| `fetched_count` | Jobs pulled from the API |
| `mapped_count` | Jobs after normalization |
| `unique_count` | Jobs after dedup |
| `inserted_count` | New jobs created |
| `updated_count` | Existing jobs refreshed |
| `closed_count` | Jobs marked closed (removed from the board) |
| `error_summary` | Error message if the run failed |

---

## Running the Ingest Pipeline

### Basic Command

```bash
uv run python -m scripts.run_scheduled_ingests [OPTIONS]
```

### All Options

| Flag | Default | Description |
|------|---------|-------------|
| `--platform` | all | Filter to one platform: `greenhouse`, `lever`, `ashby`, `smartrecruiters`, `eightfold`, `apple`, `uber`, `tiktok` |
| `--identifier` | all | Exact company identifier (e.g. `anthropic`, `stripe`) |
| `--limit N` | 5 (capped) | Max number of sources to process. Hard-capped by `INGEST_MAX_SOURCES` in `.env` |
| `--include-content` / `--no-include-content` | `--include-content` | Fetch full job descriptions. Use `--no-include-content` for faster metadata-only sync |
| `--dry-run` | off | Fetches and maps jobs but does NOT write to Firestore |
| `--retry-attempts N` | 3 | Number of retry attempts per source on failure |
| `--yes` / `-y` | off | Skip the "are you sure?" confirmation prompt |

### Examples

**Ingest one company:**
```bash
uv run python -m scripts.run_scheduled_ingests --platform greenhouse --identifier anthropic --yes
```

**Dry-run first (no writes):**
```bash
uv run python -m scripts.run_scheduled_ingests --platform greenhouse --identifier anthropic --dry-run --yes
```

**Ingest all Greenhouse sources:**
```bash
uv run python -m scripts.run_scheduled_ingests --platform greenhouse --yes
```

**Ingest everything enabled:**
```bash
uv run python -m scripts.run_scheduled_ingests --yes
```

**Raise the source limit:**
```bash
uv run python -m scripts.run_scheduled_ingests --limit 20 --yes
```

> Note: `--limit` is capped by `INGEST_MAX_SOURCES` in `.env` (default 5). Change that value to allow larger runs.

---

## Adding a New Company

Before ingesting a company, it must exist as a **source** in Firestore.

### Option 1: Via the API

```
POST /api/v1/sources/
{
  "name": "Stripe",
  "platform": "greenhouse",
  "identifier": "stripe"
}
```

### Option 2: Quick script

```bash
uv run python -c "
import asyncio
from app.infrastructure.firestore_client import get_firestore_client
from app.repositories.firestore import FirestoreSourceRepository
from app.models import Source, PlatformType

async def add():
    db = get_firestore_client()
    repo = FirestoreSourceRepository(db)
    source = Source(
        name='Stripe',
        platform=PlatformType.GREENHOUSE,
        identifier='stripe',
        enabled=True,
    )
    await repo.create(source)
    print(f'Created: {source.name} ({source.platform.value}:{source.identifier})')

asyncio.run(add())
"
```

Then run the ingest targeting that source:
```bash
uv run python -m scripts.run_scheduled_ingests --platform greenhouse --identifier stripe --yes
```

---

## What is the "identifier"?

The identifier is the company's slug on the platform's public job board URL:

| Platform | URL Pattern | Example identifier |
|----------|------------|-------------------|
| Greenhouse | `https://boards.greenhouse.io/{id}` | `anthropic`, `stripe`, `figma` |
| Lever | `https://jobs.lever.co/{id}` | `netflix`, `twitch` |
| Ashby | `https://jobs.ashbyhq.com/{id}` | `notion` |
| SmartRecruiters | SmartRecruiters company ID | varies |
| Apple / Uber / TikTok | Hardcoded fetchers | any string works |

---

## Environment Variables

Key settings in your `.env` file:

| Variable | Required | Description |
|----------|----------|-------------|
| `FIRESTORE_CREDENTIALS_FILE` | Yes | Path to your Firebase service account JSON. This switches the app from Postgres to Firestore |
| `INGEST_MAX_SOURCES` | No (default: 5) | Safety cap on sources per ingest run. Raise if you want to ingest more at once |

---

## What Happens During an Ingest

1. **Fetch** — Pulls all open jobs from the platform's public API
2. **Map** — Normalizes raw API data into the standard Job model
3. **Dedupe** — Removes duplicate `external_job_id` entries within the batch
4. **Stage** — Compares against existing Firestore jobs: new ones get inserted, existing ones get updated
5. **Location sync** — Parses location strings into structured location records, creates/links them
6. **Finalize** — Marks any jobs not seen in this fetch as `closed` (removed from the board)

### Reading the Output

```
fetched=450        # Jobs pulled from the API
unique=450         # After deduplication
inserted=450       # New jobs created in Firestore
updated=0          # Existing jobs refreshed with latest data
closed=0           # Jobs marked closed (no longer on the board)
```

On subsequent runs for the same source, you'll typically see `inserted=0` and `updated=N` since the jobs already exist and are just being refreshed.

---

## Supported Platforms

| Platform | Status |
|----------|--------|
| Greenhouse | Supported |
| Lever | Supported |
| Ashby | Supported |
| SmartRecruiters | Supported |
| Eightfold | Supported |
| Apple | Supported |
| Uber | Supported |
| TikTok | Supported |
| Workday | Not yet supported |
| GitHub Jobs | Not yet supported |
