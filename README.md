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
- [ ] SyncRunRepository (P1)
- [ ] URL normalization tool (P1)
- [ ] Content fingerprint generation (simhash/minhash) (P1)
- [ ] DedupService implementation (P1)
- [x] Same-source dedup (external_id) (P1)
- [x] Full snapshot reconcile for same-source ATS imports (Greenhouse / Ashby / Lever / SmartRecruiters; missing jobs close immediately after successful full sync) (P1)
- [ ] Cross-source dedup (apply_url, fingerprint) (P1)
- [ ] Update SyncRun dedup stats (P1)
- [ ] Index optimization (apply_url, fingerprint) (P2)

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
- [ ] Matching / recommendation API (P1)
- [ ] Logging & monitoring (P2)

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
