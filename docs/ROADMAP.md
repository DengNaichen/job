# Roadmap

Current roadmap snapshot moved out of the top-level README so the project root can focus on setup, usage, and architecture.

## Snapshot

Current live counts, source coverage, storage footprint, and enrichment cost notes now live in [docs/SIZING.md](/Users/nd/Developer/job/docs/SIZING.md).

`ROADMAP.md` should stay focused on work sequencing rather than mutable operational numbers.

## Phase 0: Core Models & Migrations

- [x] Project structure (FastAPI + SQLModel + Alembic)
- [x] Data models (Job, SyncRun)
- [x] Alembic migration scripts (P0)
- [x] Unique constraints (source + external_id) (P0)

## Phase 1: Source Abstraction + Greenhouse End-to-End

- [x] Source model + schemas (company list config) (P0)
- [x] Greenhouse Fetcher & Mapper (P0)
- [x] Source repository / service / CRUD API (P0)
- [x] Single source sync / import flow (P0)

## Phase 2: Repository + Dedup + SyncRun State

- [x] JobRepository base CRUD + structured_jd persistence helpers (P1)
- [x] JobRepository dedup queries (P1)
- [x] Offload `description_html` / `raw_payload` blobs to Supabase Storage with DB key/hash pointers (P1)
- [x] SyncRunRepository (P1)
- [x] Same-source dedup (external_id) (P1)
- [x] Full snapshot reconcile for same-source ATS imports (Greenhouse / Ashby / Lever / SmartRecruiters; missing jobs close immediately after successful full sync) (P1)
- [ ] Update SyncRun dedup stats (P2)
- [ ] URL normalization tool (P2)
- [ ] Content fingerprint generation (simhash/minhash) (P2)
- [ ] DedupService implementation (P2)
- [ ] Cross-source dedup (apply_url, fingerprint) (P2)
- [ ] Index optimization (apply_url, fingerprint) (P3)

## Phase 3: Scheduling & Retry

- [x] SyncService orchestration on top of `FullSnapshotSyncService` + `SyncRun` (P1)
- [x] Scheduled ingest runner for local `cron` / platform cron (P1)
- [x] Source-level locking / overlap guard (P1)
- [x] Error handling & retry with `tenacity` (P2)

## Phase 4: Additional Data Sources

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

## Phase 5: API & Monitoring

- [x] Health check (P1)
- [x] Source CRUD API endpoints (P1)
- [x] Job CRUD API endpoints (P1)
- [x] Matching / recommendation API (P1)
- [x] Logging & monitoring (P2)

## Phase 6: Matching & Ranking (Offline / Experimental)

- [x] Structured JD extraction service (P1)
- [x] Batch structured_jd backfill scripts (P1)
- [x] Job embedding generation pipeline (baseline JD-vector recall) (P1)
- [x] Offline matching pipeline: hard filters + vector recall + cosine threshold + deterministic rerank (P2)
- [x] Experimental top-10 LLM enum recommendation rerank (P3)
- [ ] Evaluation / benchmark harness (P2)
- [ ] Retrieval redesign: move away from `JD-only` embedding as the main retrieval primitive (P2)
- [x] Location modeling v1 on `job`: add structured fields for filtering/ranking (historical phase; later migrated to normalized `locations + job_locations`) (P2)
- [x] Country canonicalization v2 on `job`: make `location_country_code` reliable for filtering, including remote single-country rules (P2)
- [x] Country-aware filtering: apply `location_country_code` + `location_workplace_type` in retrieval/filter pipelines (P2)
- [ ] Hybrid retrieval: title / skills / domain / location / structured filters + optional vector recall (P2)
- [x] Embedding storage redesign: move vectors out of the hot `job` row and support model/version isolation (P2)
- [ ] Production-ready matching service (P3)

## Phase 7: Candidate Service & Productization

- [ ] Candidate model design (reference other repos) (P2)
- [ ] Candidate data ingestion / resume parsing (P2)
- [ ] Stored candidate profiles / persistence (P2)
- [ ] Comparison & recommendation features (P3)
- [ ] UI integration for explanations and apply guidance (P3)

## Phase 8: Post-MVP Architecture Cleanup

- [x] Add `source_id` foreign key to `job` and `syncrun` as the authoritative owner key (FK to `sources.id`), then remove legacy `source` compatibility columns after cutover validation.
- [x] Canonical locations v3: add `locations + job_locations` for reusable, multi-location, and explicit multi-country jobs once v1/v2 justify normalized location entities (P3)
- [x] Migrate retrieval/read paths to normalized location links where multi-location coverage, multi-country links, or canonical location reuse justify the extra complexity (P3)
- [x] Canonical Locations cleanup: physical drop of legacy denormalized location fields (`location_text`, `location_country_code`, etc.) on the `job` table after v3 is vetted (P3)
- [x] Blob storage cutover: eliminate `description_html` / `raw_payload` dual-write, backfill pointer coverage, and drop legacy inline blob columns from `job` (P2)
- [ ] GeoNames automation: system for periodic refresh and patching of canonical `Location` seed data (P3)
- [ ] Split hot vs cold job data: keep frequently queried fields hot, move large content blobs / payloads / vectors out of the main row where appropriate (P2)
- [ ] Replace per-job ORM staging with batch-first ingest writes and bulk upsert paths (P1)
- [x] Parallelize blob sync with bounded concurrency so large sources stop paying one network round-trip chain per job (P1)
- [ ] Add blob-sync short-circuit paths to skip unnecessary storage work (P2)
- [x] Enforce one running `SyncRun` per `source_id` with DB partial unique index + create-time conflict handling (P1)
- [ ] Add smarter source scheduling: lower frequency for historically empty / low-yield sources and better treatment for oversized sources (P2)
- [ ] Improve source-specific location parsing for low-confidence text-heavy sources (e.g., remote scope edge cases and missing locations) (P3)
- [x] Physically remove legacy `job.embedding`, `job.embedding_model`, and `job.embedding_updated_at` columns once the `job_embedding` store rollout is stable and all matching/migration paths have been verified in production (P2)
