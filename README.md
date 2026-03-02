# Job Service

Job Service is a FastAPI-based job aggregation service. It ingests jobs from public ATS platforms and company-specific careers APIs, normalizes them into a common schema, stores them in PostgreSQL, and exposes APIs for source management, job retrieval, and experimental matching.

## What This Repo Does

- Ingests jobs from supported sources into a unified `Job` model
- Reconciles same-source snapshots so missing jobs can be closed automatically after a successful full sync
- Tracks source sync execution in `SyncRun`
- Optionally offloads large fields like `description_html` and `raw_payload` to Supabase Storage
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
   Dedupes by `external_job_id`, upserts open jobs, and closes missing jobs after a successful full snapshot. Ownership is keyed by `source_id` (FK to `sources.id`).
5. `SyncRun`
   Records each source-level execution status and stats, linked to `sources` via `source_id`
6. `run_scheduled_ingests.py`
   Thin orchestration layer for scheduled source syncs with retry and overlap protection

> **Note on `source` string field**: Both `job.source` and `syncrun.source` retain the legacy
> `platform:identifier` string (e.g. `greenhouse:airbnb`) as a **compatibility field**.
> It is dual-written alongside `source_id` and preserved for backward-compatible reads.
> `source_id` (FK to `sources.id`) is the authoritative owner key for all runtime behavior.

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

Optional features:

- `STORAGE_PROVIDER=supabase` and related storage vars for blob offload
- embedding / LLM settings for structured JD parsing and matching

### 3. Start PostgreSQL

```bash
docker compose up -d postgres
docker compose ps
```

Default local database:

```text
postgresql+asyncpg://postgres:postgres@localhost:5434/job_db
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

## Database Architecture

Authoritative ownership and storage strategy:

1. `Source`: Auth owner for sync runs and jobs (platform + identifier)
2. `Job`: Hot job row (title, apply_url, status, location metadata)
3. `JobEmbedding`: Dedicated vector storage with model/version isolation
4. `SyncRun`: Execution metrics/status logs

Legacy `job.embedding`, `job.embedding_model`, and `job.embedding_updated_at` columns are **deprecated** and preserved only as rollout compatibility. Both matching recall and new writes target `JobEmbedding`.

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
- overlap guard for already-running sources
- sequential execution
- non-zero exit code if any source fails

## Structured JD and Matching Pipelines

This repo also includes downstream enrichment and matching utilities:

- `scripts/backfill_structured_jd.py`
- `scripts/batch_parse_jd.py`
- `scripts/backfill_job_embeddings_gemini.py`
- `scripts/match_experiment.py`

These are separate from the raw ingest flow. A typical lifecycle is:

1. ingest jobs
2. backfill `structured_jd`
3. backfill embeddings into the `job_embedding` store
4. query recommendations through `/api/v1/matching/recommendations` (matching recall joins through `job_embedding`)

## Blob Storage

Large fields can be stored outside PostgreSQL in Supabase Storage:

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
./scripts/uv run pytest tests/unit/test_sync_service.py tests/unit/test_run_scheduled_ingests.py
```

### Common scripts

- `scripts/import_*.py`
  Platform or company-specific ingest entrypoints
- `scripts/run_scheduled_ingests.py`
  Source-level orchestration runner
- `scripts/backfill_structured_jd.py`
  Structured JD backfill
- `scripts/backfill_job_embeddings_gemini.py`
  Embedding backfill
- `scripts/migrate_job_blobs_to_storage.py`
  Blob pointer backfill

## Roadmap

The roadmap has been moved to [docs/ROADMAP.md](/Users/nd/Developer/job/docs/ROADMAP.md).

Current sizing, source coverage, and cost notes live in [docs/SIZING.md](/Users/nd/Developer/job/docs/SIZING.md).

Architecture diagrams live in [docs/architecture/README.md](/Users/nd/Developer/job/docs/architecture/README.md).
