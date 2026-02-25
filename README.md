# Job Service

Job aggregation microservice.

## Roadmap

### Phase 0: Core Models & Migrations

- [x] Project structure (FastAPI + SQLModel + Alembic)
- [x] Data models (Job, SyncRun)
- [ ] Alembic migration scripts (P0)
- [ ] Unique constraints (source + external_id) (P0)

### Phase 1: Source Abstraction + Greenhouse End-to-End

- [ ] Source model (company list config) (P0)
- [x] Greenhouse Fetcher & Mapper (P0)
- [ ] Basic Repository (CRUD) (P0)
- [ ] Single source sync flow (P0)

### Phase 2: Repository + Dedup + SyncRun State

- [ ] JobRepository (CRUD + dedup queries) (P1)
- [ ] SyncRunRepository (P1)
- [ ] URL normalization tool (P1)
  - [ ] Unify scheme (https) (P1)
  - [ ] Remove tracking params (utm_*, ref, source) (P1)
  - [ ] Normalize domain (www. prefix) (P2)
- [ ] Content fingerprint generation (simhash/minhash) (P1)
- [ ] DedupService implementation (P1)
  - [ ] Same-source dedup (external_id) (P1)
  - [ ] Cross-source dedup (apply_url, fingerprint) (P1)
  - [ ] Update SyncRun dedup stats (P1)
- [ ] Index optimization (apply_url, fingerprint) (P2)

### Phase 3: Scheduling & Retry (pgBoss)

- [ ] SyncService orchestration (P1)
- [ ] Scheduled tasks (pgBoss cron) (P1)
- [ ] Error handling & retry (P2)

### Phase 4: Additional Data Sources

- [ ] Lever (P1)
- [ ] JobSpy integration (P1)
- [ ] Workday (requires special handling) (P1)
- [ ] Ashby (P2)
- [ ] SmartRecruiters (P2)
- [ ] Jöbö API (P2)
- [ ] Recruitee (P3)
- [ ] Workable (P3)

### Phase 5: API & Monitoring

- [ ] REST API endpoints (P1)
- [ ] Health check (P1)
- [ ] Logging & monitoring (P2)

### Phase 6: Candidate Service (Independent Planning)

- [ ] Candidate model design (reference other repos) (P2)
- [ ] Candidate data ingestion (P2)
- [ ] Job-candidate matching service (P3)
- [ ] Comparison & recommendation features (P3)
- [ ] LLMs (P3)
