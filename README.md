# Job Service

Job aggregation microservice.

## Local PostgreSQL (Docker)

1. Start PostgreSQL:
   `docker compose up -d postgres`
2. Check container health:
   `docker compose ps`
3. Copy env template if needed:
   `cp .env.example .env`

Default local DB connection:
`postgresql+asyncpg://postgres:postgres@localhost:5434/job_db`

## Local Supabase (CLI)

This repo now includes a local Supabase project under
[supabase/config.toml](/Users/nd/Developer/job/supabase/config.toml) with a
private `job-blobs` bucket for blob storage.

1. Start the local stack:
   `npx supabase start`
2. Run app commands against local Supabase without replacing your main `.env`:
   `./scripts/with_local_supabase_env.sh <command>`
3. Bootstrap this repo's schema into the local Supabase DB:
   `./scripts/bootstrap_local_supabase_schema.sh`

Current local Supabase ports for this repo:

- API: `http://127.0.0.1:55321`
- DB: `postgresql+asyncpg://postgres:postgres@127.0.0.1:55322/postgres`
- Studio: `http://127.0.0.1:55323`
- Mailpit: `http://127.0.0.1:55324`

Local blob storage overrides live in `.env.supabase.local`, which is gitignored.
The helper script loads `.env` first, then overrides DB and Storage settings
with the local Supabase values.

This repo does not yet use Supabase SQL migrations as the source of truth for
fresh databases. After a local `supabase db reset`, rerun
`./scripts/bootstrap_local_supabase_schema.sh`.

## Job Blob Offload

To reduce PostgreSQL table size and TOAST pressure, `job.description_html` and
`job.raw_payload` now have external blob pointers in the `job` table:

- `description_html_key`
- `description_html_hash`
- `raw_payload_key`
- `raw_payload_hash`

Current phase keeps these fields in PostgreSQL:

- `description_plain`
- `structured_jd`
- all filter/sort columns already used by matching and search

Current phase keeps the legacy `description_html` and `raw_payload` columns in
place for compatibility. New writes upload gzip-compressed blobs to Supabase
Storage first and only then write the DB pointer fields. That ordering means:

- the database should never point at a missing blob
- a failed DB transaction can leave orphaned storage objects, which is acceptable
  for this phase and easier to repair later

Stable object keys are content-addressed:

- `job-html/{sha256}.html.gz`
- `job-raw/{sha256}.json.gz`

### Blob Storage Config

Add these environment variables when enabling blob storage:

- `STORAGE_PROVIDER=supabase`
- `SUPABASE_STORAGE_BASE_URL=https://<project-ref>.supabase.co/storage/v1`
- `SUPABASE_STORAGE_BUCKET=<bucket-name>`
- `SUPABASE_STORAGE_SERVICE_KEY=<service-role-key>`

If blob storage is not configured, the app can still start, but write paths and
backfill scripts that need blob storage will fail with an explicit runtime
error.

### Backfill Existing Jobs

After applying the schema migration, backfill existing rows:

```bash
PYTHONPATH=. .venv/bin/python scripts/migrate_job_blobs_to_storage.py --batch-size 100
```

Useful modes:

- `--dry-run`
- `--html-only`
- `--raw-only`

The backfill uploads missing blobs and writes the new key/hash columns, but it
does not clear the legacy `description_html` or `raw_payload` columns yet.

### Phase 2 Cleanup

Once reads have been fully moved to storage-backed helpers and the backfill has
completed, phase 2 can clear legacy column bodies in batches:

1. backfill all missing blob pointers
2. verify spot samples by reading from storage
3. set `description_html = NULL` and/or `raw_payload = '{}'` for migrated rows
4. monitor storage reads before considering column removal in a later migration

## Embedding Setup (LiteLLM Generic, 1024)

1. Ensure PostgreSQL runs with pgvector:
   `docker compose up -d postgres`
2. Add embedding config in `.env` (example for SiliconFlow CN + Qwen):
   `EMBEDDING_PROVIDER=openai`
   `EMBEDDING_API_BASE=https://api.siliconflow.cn/v1`
   `EMBEDDING_API_KEY=...`
   `EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B`
   `EMBEDDING_DIM=1024`
3. Apply migrations:
   `PYTHONPATH=. .venv/bin/alembic upgrade head`
4. Backfill job embeddings:
   `PYTHONPATH=. .venv/bin/python scripts/backfill_job_embeddings_gemini.py --dim 1024 --batch-size 32 --concurrency 5`

## Roadmap

Current snapshot as of 2026-02-28: public ATS ingestion is live for Greenhouse, Ashby, Lever, and SmartRecruiters. The database currently holds 35,795 jobs total: Greenhouse 18,117, Ashby 6,820, Lever 4,266, and SmartRecruiters 6,592. Source coverage currently includes 107 Ashby sources with jobs, 50 Lever sources with jobs, and 52 SmartRecruiters sources with jobs.

### Phase 0: Core Models & Migrations

- [x] Project structure (FastAPI + SQLModel + Alembic)
- [x] Data models (Job, SyncRun)
- [x] Alembic migration scripts (P0)
- [x] Unique constraints (source + external_id) (P0)

### Phase 1: Source Abstraction + Greenhouse End-to-End

- [x] Source model + schemas (company list config) (P0)
- [x] Greenhouse Fetcher & Mapper (P0)
- [x] Source repository / service / CRUD API (P0)
- [x] Single source sync / import flow (P0)

### Phase 2: Repository + Dedup + SyncRun State

- [x] JobRepository base CRUD + structured_jd persistence helpers (P1)
- [x] JobRepository dedup queries (P1)
- [x] Offload `description_html` / `raw_payload` blobs to Supabase Storage with DB key/hash pointers (P1)
- [ ] SyncRunRepository (P1)
- [x] Same-source dedup (external_id) (P1)
- [x] Full snapshot reconcile for same-source ATS imports (Greenhouse / Ashby / Lever / SmartRecruiters; missing jobs close immediately after successful full sync) (P1)
- [ ] Update SyncRun dedup stats (P2)
- [ ] URL normalization tool (P2)
- [ ] Content fingerprint generation (simhash/minhash) (P2)
- [ ] DedupService implementation (P2)
- [ ] Cross-source dedup (apply_url, fingerprint) (P2)
- [ ] Index optimization (apply_url, fingerprint) (P3)

### Phase 3: Scheduling & Retry (pgBoss)

- [ ] SyncService orchestration (P1)
- [ ] Scheduled tasks (pgBoss cron) (P1)
- [ ] Error handling & retry (P2)

### Phase 4: Additional Data Sources

- [x] Lever (P1)
- [x] Eightfold (Microsoft, NVIDIA) (P1)
- [x] Apple Careers API (P2)
- [x] Uber Careers API (P2)
- [x] TikTok Careers API (P2)
- [ ] Workday (requires API-based special handling) (P1)
- [x] Ashby (P2)
- [x] SmartRecruiters (P2)

- [ ] Amazon Jobs API (P2, current API hard-caps search results at 10,000)
- [ ] ~~Jobo API (P2, paid)~~
- [ ] Recruitee (P3)
- [ ] Workable (P3)
- [ ] JobSpy (P3)

### Phase 5: API & Monitoring

- [x] Health check (P1)
- [x] Source CRUD API endpoints (P1)
- [x] Job CRUD API endpoints (P1)
- [x] Matching / recommendation API (P1)
- [x] Logging & monitoring (P2)

### Phase 6: Matching & Ranking (Offline / Experimental)

- [x] Structured JD extraction service (P1)
- [x] Batch structured_jd backfill scripts (P1)
- [x] Job embedding generation pipeline (P1)
- [x] Offline matching pipeline: hard filters + vector recall + cosine threshold + deterministic rerank (P2)
- [x] Experimental top-10 LLM enum recommendation rerank (P3)
- [ ] Evaluation / benchmark harness (P2)
- [ ] Production-ready matching service (P3)

### Phase 7: Candidate Service & Productization

- [ ] Candidate model design (reference other repos) (P2)
- [ ] Candidate data ingestion / resume parsing (P2)
- [ ] Stored candidate profiles / persistence (P2)
- [ ] Comparison & recommendation features (P3)
- [ ] UI integration for explanations and apply guidance (P3)
