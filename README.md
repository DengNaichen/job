# Job Service

Job Service is a FastAPI-based job aggregation service. It ingests jobs from public ATS platforms and company-specific careers APIs, normalizes them into a common schema, stores them in PostgreSQL, and exposes APIs for source management, job retrieval, and experimental matching.

## What This Repo Does

- Ingests jobs from supported sources into a unified `Job` model
- Reconciles same-source snapshots so missing jobs can be closed automatically after a successful full sync
- Tracks source sync execution in `SyncRun`
- Stores large fields (`description_html`, `raw_payload`) in Supabase Storage via pointer/hash columns on `job`
- Exposes REST APIs for `sources`, `jobs`, and `matching`
- Includes a lightweight scheduled runner for local `cron` or future Cloud Run / Cloud Scheduler style execution

## Developer Workflow

Bootstrap the local environment:

```bash
./scripts/uv sync
```

or:

```bash
./scripts/bootstrap
```

Common engineering commands:

```bash
./scripts/lint
./scripts/test
./scripts/fmt
```

Enable local git hooks:

```bash
./scripts/install_hooks
```

The repository CI baseline runs:

- `./scripts/lint`
- `./scripts/test`

Optional aliases are available through `make` if your local toolchain already
has Command Line Tools configured:

- `make bootstrap`
- `make lint`
- `make test`
- `make fmt`

## Supported Sources

### ATS / platform-based sources

- `greenhouse`
- `lever`
- `ashby`
- `smartrecruiters`
- `eightfold`
  Currently configured for:
  - `microsoft`
  - `nvidia`

### Company API sources

- `apple`
- `uber`
- `tiktok`

### Not implemented or intentionally deferred

- `workday`
  Requires a dedicated API-based implementation.
- `amazon`
  Current API hard-caps search pagination at 10,000 results, which is unsafe for the current full-snapshot reconcile model.

## Architecture

The ingest path is intentionally layered:

1. `Source`
   One configured upstream source, keyed by `platform + identifier`. Each source has a UUID `id` that serves as the **authoritative owner key** (`source_id`) for jobs and sync runs.
2. `Fetcher`
   Pulls raw jobs from an external ATS or company API
3. `Mapper`
   Converts raw payloads into the internal `JobCreate` schema
4. `FullSnapshotSyncService`
   Dedupes by `external_job_id`, upserts open jobs, syncs normalized canonical locations (`locations` + `job_locations`), and closes missing jobs after a successful full snapshot. Ownership is keyed by `source_id` (FK to `sources.id`). The implementation is modularized under `app/services/application/full_snapshot_sync/` and uses bounded blob-sync concurrency.
5. `SyncRun`
   Records each source-level execution status and stats, linked to `sources` via `source_id`
6. `run_scheduled_ingests.py`
   Thin orchestration layer for scheduled source syncs with retry and overlap protection. Overlap guard is keyed by `source_id` and backed by a DB-level unique running-run guard. After successful non-dry-run snapshots, it triggers source-scoped embedding refresh into `job_embedding`.

> **Note on source ownership key**: Runtime ownership is now keyed only by `source_id`
> (FK to `sources.id`) on both `job` and `syncrun`. Legacy string columns were removed
> in migration `f7a8b9c0d1e2_drop_legacy_source_columns`.

## Quick Start

### 1. Install dependencies

```bash
./scripts/uv sync
```

### 2. Configure environment

```bash
cp .env.example .env
```

Minimum local setup:

- `DATABASE_URL`
- Blob storage configuration (`STORAGE_PROVIDER=supabase` + required Supabase vars) if you run ingest or job write flows

Optional features:

- embedding / LLM settings for structured JD parsing and matching

### 3. Start local Supabase (and optionally Metabase)

```bash
npx supabase start
```

Start Metabase for local BI/dashboarding:

```bash
docker compose up -d metabase
docker compose ps
```

Default local database:

```text
postgresql+asyncpg://postgres:postgres@127.0.0.1:55322/postgres
```

### 4. Apply database migrations

Database migrations use the standard Alembic layout in this repository:

- `alembic.ini`
- `alembic/`

Apply migrations before starting the API server:

```bash
./scripts/uv run alembic upgrade head
```

### 5. Start the API server

```bash
./scripts/uv run uvicorn app.main:app --reload
```

Useful URLs:

- API docs: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`
- Metrics: `http://127.0.0.1:8000/metrics`
- Metabase: `http://127.0.0.1:3001`

## Metabase Setup (Local)

After `docker compose up -d metabase`, open `http://127.0.0.1:3001` and finish the first-run setup.

When adding this app database in Metabase, use:

- Database type: `PostgreSQL`
- Host: `host.docker.internal` (when Metabase runs in Docker)
- Port: `55322`
- Database name: `postgres`
- Username: `postgres`
- Password: `postgres`

If you run Metabase outside Docker, set host to `127.0.0.1` and port to `55322`.

## Database Architecture

Authoritative ownership and storage strategy:

1. `Source`: Authoritative owner for `Job` and `SyncRun` via `source_id` (platform + identifier config)
2. `Job`: Hot job row (identity, status, metadata, structured JD, blob pointer/hash columns)
3. `Location`: Canonical reusable location entity (`canonical_key`, `display_name`, country/region/city, optional GeoNames metadata)
4. `JobLocation`: Many-to-many link between jobs and canonical locations, with primary flag and workplace metadata
5. `JobEmbedding`: Dedicated vector storage with active-target model/version isolation
6. `SyncRun`: Source-level execution stats and status logs

Physical cleanup already completed:

- Legacy source compatibility columns (`job.source`, `syncrun.source`) are dropped.
- Legacy denormalized location column (`job.location_text`) is dropped.
- Legacy inline blob columns (`job.description_html`, `job.raw_payload`) are dropped in favor of pointer-based storage.
- Legacy inline embedding columns on `job` are dropped; matching recall and writes use `job_embedding`.

## Core API Surface

### Health and observability

- `GET /health`
- `GET /metrics`

### Source management

- `POST /api/v1/sources`
- `GET /api/v1/sources`
- `GET /api/v1/sources/slugs`
- `GET /api/v1/sources/{source_id}`
- `PATCH /api/v1/sources/{source_id}`
- `DELETE /api/v1/sources/{source_id}`

### Job CRUD

- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs`
- `PATCH /api/v1/jobs/{job_id}`
- `DELETE /api/v1/jobs/{job_id}`

### Experimental matching

- `POST /api/v1/matching/recommendations`

## Ingest Workflows

### 1. Create sources

Create sources through the Source API before importing jobs.

Examples:

```json
{"name": "Stripe", "platform": "greenhouse", "identifier": "stripe"}
```

```json
{"name": "Microsoft", "platform": "eightfold", "identifier": "microsoft"}
```

```json
{"name": "Uber", "platform": "uber", "identifier": "uber"}
```

### 2. Run platform-specific import scripts

Examples:

```bash
./scripts/uv run python scripts/import_greenhouse_jobs.py --slug stripe
./scripts/uv run python scripts/import_eightfold_jobs.py --slug microsoft
./scripts/uv run python scripts/import_apple_jobs.py --slug apple
./scripts/uv run python scripts/import_uber_jobs.py --slug uber
./scripts/uv run python scripts/import_tiktok_jobs.py --slug tiktok
```

All import scripts support `--dry-run`. Most also support `--include-content` and `--limit`.

### 3. Run scheduled orchestration

The scheduled runner is the preferred entrypoint for repeated source syncs:

```bash
./scripts/uv run python scripts/run_scheduled_ingests.py
./scripts/uv run python scripts/run_scheduled_ingests.py --platform greenhouse
./scripts/uv run python scripts/run_scheduled_ingests.py --identifier microsoft
./scripts/uv run python scripts/run_scheduled_ingests.py --dry-run
```

Current behavior:

- supported platforms only
- source-level `SyncRun` records
- source-level retry via `tenacity`
- overlap guard for already-running sources (source_id + DB unique running guard)
- embedding refresh runs only after successful non-dry-run snapshots
- embedding refresh is source-scoped, excludes closed jobs, and writes idempotent active-target upserts
- sequential execution
- non-zero exit code if any source fails

## Structured JD and Matching Pipelines

This repo also includes downstream enrichment and matching utilities:

- `scripts/backfill_structured_jd.py`
- `scripts/batch_parse_jd.py`
- `scripts/match_experiment.py`

Structured JD backfill is separate from raw ingest flow. Embedding refresh is snapshot-aligned and
is triggered automatically by `SyncService` after successful full snapshots. A typical lifecycle is:

1. ingest jobs
2. backfill `structured_jd`
3. run snapshot sync (`scripts/run_scheduled_ingests.py`) to refresh active-target embeddings for open jobs
4. query recommendations through `/api/v1/matching/recommendations` (matching recall joins through `job_embedding`)

## Blob Storage

Large fields are stored outside PostgreSQL in Supabase Storage:

- `description_html`
- `raw_payload`

Pointer columns kept in PostgreSQL:

- `description_html_key`
- `description_html_hash`
- `raw_payload_key`
- `raw_payload_hash`

Required environment variables when enabling storage:

- `STORAGE_PROVIDER=supabase`
- `SUPABASE_STORAGE_BASE_URL`
- `SUPABASE_STORAGE_BUCKET`
- `SUPABASE_STORAGE_SERVICE_KEY`

Note:

- Ingest and job write paths expect blob storage to be configured.
- Read-only API usage without ingest can run with `STORAGE_PROVIDER=none`.

Backfill existing rows:

```bash
./scripts/uv run python scripts/migrate_job_blobs_to_storage.py --batch-size 100
```

Useful modes:

- `--dry-run`
- `--html-only`
- `--raw-only`

## Local Supabase

This repo includes a local Supabase project for storage-backed development.

Start it with:

```bash
npx supabase start
./scripts/with_local_supabase_env.sh <command>
./scripts/bootstrap_local_supabase_schema.sh
```

Default local ports:

- API: `http://127.0.0.1:55321`
- DB: `postgresql+asyncpg://postgres:postgres@127.0.0.1:55322/postgres`
- Studio: `http://127.0.0.1:55323`
- Mailpit: `http://127.0.0.1:55324`

## Development

### Run tests

```bash
./scripts/uv run pytest
```

### Run a smaller targeted suite

```bash
./scripts/uv run pytest tests/unit/sync
```

### Common scripts

- `scripts/import_*.py`
  Platform or company-specific ingest entrypoints
- `scripts/run_scheduled_ingests.py`
  Source-level orchestration runner
- `scripts/backfill_structured_jd.py`
  Structured JD backfill
- `scripts/migrate_job_blobs_to_storage.py`
  Blob pointer backfill

## Roadmap

The roadmap has been moved to [docs/ROADMAP.md](/Users/nd/Developer/job/docs/ROADMAP.md).

Current sizing, source coverage, and cost notes live in [docs/SIZING.md](/Users/nd/Developer/job/docs/SIZING.md).

Architecture diagrams live in [docs/architecture/README.md](/Users/nd/Developer/job/docs/architecture/README.md).
