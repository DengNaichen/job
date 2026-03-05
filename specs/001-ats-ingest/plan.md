# Implementation Plan: ATS Ingest (US1-US4)

**Branch**: `001-ats-ingest` | **Date**: 2026-03-05 | **Spec**: `specs/001-ats-ingest/spec.md`
**Input**: Feature specification from `specs/001-ats-ingest/spec.md`

## Summary

Deliver full ATS ingest scope across US1-US4:

- resilient multi-platform fetching with retry wrappers and bounded detail concurrency,
- normalized mapper output with structured location hints,
- full snapshot reconciliation (insert/update/close + dedupe),
- blob storage offloading for large payload fields.

Implementation strategy remains TDD-first, but this plan now covers the complete feature contract instead of US1-only.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI, SQLModel, httpx, tenacity, pycountry, pytest, pytest-asyncio, respx  
**Storage**: PostgreSQL via SQLModel/AsyncSession + external blob storage backend  
**Testing**: pytest + pytest-asyncio + respx  
**Target Platform**: Backend service runtime (Linux/macOS)  
**Project Type**: Backend ingest pipeline  
**Performance Goals**:

- detail fetch concurrency default `6` for summary+detail fetchers,
- blob sync staging concurrency default `16` with bounded parallelism.

**Constraints**:

- all concrete fetcher HTTP calls must route through BaseFetcher wrappers,
- ambiguous/multi-country normalization must be conservative,
- snapshot close behavior must be source-scoped and idempotent,
- all behavior changes must be covered by automated tests.

**Scale/Scope**: 8 ATS platforms (Greenhouse, Lever, Ashby, Apple, Uber, TikTok, Eightfold, SmartRecruiters), high-volume ingest (hundreds of thousands of jobs).

## Constitution Check

Current `.specify/memory/constitution.md` is a placeholder template and does not define enforceable MUST clauses.

Quality gates applied for this plan:

- Test-first workflow for behavior changes.
- Backward-compatible request/response behavior for ingest/matching dependencies.
- No regressions in US1 + mapper + snapshot + blob suites.

Gate status: PASS.

## Project Structure

### Documentation (this feature)

```text
specs/001-ats-ingest/
├── spec.md
├── plan.md
└── tasks.md
```

### Source Code (repository root)

```text
app/
├── ingest/
│   ├── fetchers/
│   └── mappers/
├── services/application/
│   ├── sync/service.py
│   ├── full_snapshot_sync/
│   │   ├── service.py
│   │   ├── mapping.py
│   │   ├── staging.py
│   │   ├── finalize.py
│   │   └── location_sync.py
│   └── blob/job_blob.py
├── services/infra/blob_storage/
└── repositories/
    ├── job.py
    └── sync_run.py

tests/
└── unit/
    ├── ingest/fetchers/
    ├── ingest/mappers/
    ├── sync/
    │   ├── test_sync_service.py
    │   ├── test_run_scheduled_ingests.py
    │   └── test_full_snapshot_sync.py
    ├── repositories/test_job_repository_dedup.py
    ├── services/application/blob/test_blob_storage.py
    └── scripts/test_migrate_job_blobs_to_storage.py
```

**Structure Decision**: Keep monorepo backend layout. Complete the feature by aligning documentation, tasks, and test evidence with already-landed US1-US4 architecture.

## Scope and Acceptance Mapping

### US1 - Multi-source fetching with retry resilience

- 8 fetchers comply with retry wrappers.
- Retryable statuses include `429/500/502/503/504`.
- Retry exhaustion is source-level failure (no process crash).
- Summary+detail concurrency is bounded (default `6`).

### US2 - Normalized mapping with structured locations

- Mappers output canonical `JobCreate` fields (`external_job_id`, `title`, `apply_url`, `source_id`).
- `location_hints` emitted when location data exists.
- `description_html` / `description_plain` coverage maintained.

### US3 - Full snapshot reconciliation

- same-source runs insert/update/open jobs from latest snapshot,
- missing jobs are closed on successful run,
- duplicate `external_job_id` values are deduped before staging.

### US4 - Blob storage offloading

- `description_html` and `raw_payload` moved to blob storage with hash/key pointers,
- upload behavior is concurrency-bounded,
- failures during blob stage roll back snapshot transaction safely.

## Execution Strategy

### Phase 0 - Baseline Verification

- Verify current implementation against US1-US4 acceptance criteria.
- Identify any remaining delta between `spec.md`, `plan.md`, and `tasks.md`.

### Phase 1 - Gap Closure

- Close any uncovered acceptance criteria (if found).
- Ensure contract-level tests exist for all four stories.

### Phase 2 - Task/Docs Alignment

- Regenerate `tasks.md` for US1-US4 scope (previous US1-only task plan is outdated).
- Keep reports and contributor guidance synchronized with final structure.

### Phase 3 - Regression Stabilization

- Run impacted unit suites and record evidence.
- Confirm no regressions in scheduled ingest and sync service behavior.

## Validation Plan

Minimum validation commands:

- `pytest tests/unit/ingest/fetchers -q`
- `pytest tests/unit/ingest/mappers -q`
- `pytest tests/unit/sync -q`
- `pytest tests/unit/repositories/test_job_repository_dedup.py tests/unit/services/application/blob/test_blob_storage.py tests/unit/scripts/test_migrate_job_blobs_to_storage.py -q`

Pass criteria:

- US1-US4 acceptance criteria have automated test evidence.
- All impacted suites pass without flaky concurrency failures.
- No behavior regression in source-level sync run outcomes.

## Risks and Mitigations

- Risk: stale US1-only tasks cause planning drift.
  - Mitigation: regenerate tasks for full US1-US4 scope before further implementation cycles.
- Risk: country/location normalization edge cases regress under mapper changes.
  - Mitigation: keep ambiguity/multi-country tests mandatory in CI.
- Risk: blob offload failures create partial writes.
  - Mitigation: preserve transactional rollback and failure-path tests.
