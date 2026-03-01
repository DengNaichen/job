# Implementation Plan: Source ID Ownership Migration

**Branch**: `001-source-id-fks-impl` | **Date**: 2026-03-01 | **Spec**: [`/specs/001-source-id-fks/spec.md`](/Users/nd/Developer/job/specs/001-source-id-fks/spec.md)
**Input**: Feature specification from `/specs/001-source-id-fks/spec.md`

## Summary

Complete the ownership migration from the mutable legacy `source` string to authoritative `source_id` foreign keys on `job` and `syncrun`.

The current codebase is already on the layered service structure:

- `app/services/application/*`
- `app/repositories/*`
- `app/models/*`
- `app/schemas/*`
- tracked `alembic/`

Some transitional `source_id` and `source_key` naming already exists in result objects and tests, but runtime authority still primarily uses the legacy `source` string in sync, full-snapshot reconcile, and source delete protection. This implementation finishes the migration by adding schema support, backfilling existing rows, dual-writing new rows, cutting authoritative reads over to `source_id`, protecting source lifecycle operations, and enforcing `NOT NULL`.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI, SQLModel, SQLAlchemy/Alembic, asyncpg, tenacity  
**Storage**: PostgreSQL for relational data, Supabase Storage for large job blobs  
**Testing**: pytest, pytest-asyncio, unit and integration suites under `tests/`  
**Target Platform**: Backend service and scheduled ingest scripts running on local dev and Linux-style server environments  
**Project Type**: FastAPI web service with database-backed ingest pipelines  
**Performance Goals**: Preserve current full-snapshot ingest semantics with indexed same-source lookups and no new unbounded scans in hot sync paths  
**Constraints**: No data loss, no orphaned rows, no same-day API break, no physical rename of the `source` column in this feature  
**Scale/Scope**: Touches Alembic migrations, SQLModel models, repositories, application services, source lifecycle safeguards, API schemas, unit tests, integration tests, and rollout documentation

## Constitution Check

The repo's `.specify/memory/constitution.md` remains the default placeholder, so there are no additional project-specific constitutional gates to enforce.

Operational gates for this feature:

- Migration must be additive first: add nullable columns and backfill before `NOT NULL` enforcement.
- Existing API payloads must remain readable by clients that still depend on the legacy `source` field.
- Same-source reconcile and overlap guard behavior must be covered by updated automated tests before rollout.
- Source mutation rules must prevent `platform` or `identifier` drift for referenced sources during the compatibility window.
- Constraint enforcement must not proceed unless post-backfill validation confirms no unmatched rows and no duplicate `(source_id, external_job_id)` ownership.

## Current Baseline

The current code already reflects the layered service refactor, but the migration is incomplete:

- [`app/services/application/full_snapshot_sync.py`](/Users/nd/Developer/job/app/services/application/full_snapshot_sync.py) already emits `source_id` and `source_key` in results, but same-source lookup and close-missing still use the legacy `source` string.
- [`app/services/application/sync.py`](/Users/nd/Developer/job/app/services/application/sync.py) still uses the legacy `source` string for overlap detection and sync-run creation.
- [`app/services/application/source.py`](/Users/nd/Developer/job/app/services/application/source.py) still blocks deletion using sync-run checks keyed by the legacy `source` string only.
- [`app/schemas/job.py`](/Users/nd/Developer/job/app/schemas/job.py) and [`app/schemas/sync_run.py`](/Users/nd/Developer/job/app/schemas/sync_run.py) do not yet expose `source_id`.
- [`tests/integration/test_job_api.py`](/Users/nd/Developer/job/tests/integration/test_job_api.py) does not exist yet.

## Project Structure

### Documentation (this feature)

```text
specs/001-source-id-fks/
├── plan.md
├── quickstart.md
├── spec.md
└── tasks.md
```

### Source Code (repository root)

```text
alembic/
├── env.py
└── versions/

app/
├── api/v1/
├── models/
├── repositories/
├── schemas/
└── services/
    └── application/

tests/
├── integration/
└── unit/
```

**Structure Decision**: Single backend service. The migration spans tracked Alembic revisions under `alembic/versions/`, model and schema updates under `app/`, authoritative repository and application-service cutover, API compatibility work under `app/api/v1/`, and validation in `tests/unit/` plus `tests/integration/`.

## Affected Files

### Migrations

- `alembic/versions/*`

### Models and Schemas

- `app/models/job.py`
- `app/models/sync_run.py`
- `app/schemas/job.py`
- `app/schemas/sync_run.py`

### Repositories

- `app/repositories/job.py`
- `app/repositories/sync_run.py`
- `app/repositories/source.py`

### Application Services

- `app/services/application/full_snapshot_sync.py`
- `app/services/application/sync.py`
- `app/services/application/source.py`
- `app/services/application/job.py`

### API

- `app/api/v1/jobs.py`
- `app/api/v1/sources.py`

### Tests

- `tests/unit/test_full_snapshot_sync.py`
- `tests/unit/test_sync_service.py`
- `tests/unit/test_sync_run_repository.py`
- `tests/unit/test_job_repository_dedup.py`
- `tests/unit/test_job_service.py`
- `tests/unit/test_source.py`
- source-aware import tests under `tests/unit/`
- `tests/unit/test_run_scheduled_ingests.py`
- `tests/integration/test_source_api.py`
- `tests/integration/test_job_api.py` (new)

### Rollout Docs

- `specs/001-source-id-fks/quickstart.md` (new)
- `README.md`
- `app/models/README.md`
- `docs/architecture/README.md`
- `docs/ROADMAP.md`

## Implementation Decisions

- Use the tracked repository `alembic/` setup. Do not reintroduce local-only Alembic wording or workflow.
- Keep the physical legacy column name as `source` throughout this feature. Treat it conceptually as a compatibility `source_key`, but do not rename it here.
- Allow temporary authoritative fallback to the legacy `source` string only for rows where `source_id IS NULL`.
- Require post-backfill validation before applying the enforcement revision.
- Use `409 Conflict` for source delete or mutation attempts that are blocked because the source is referenced.
- Add `tests/integration/test_job_api.py` as a new endpoint-level integration suite rather than folding job API coverage into unrelated files.

## Implementation Strategy

### Phase 1: Preflight Audit

- Create operator-facing rollout documentation in `quickstart.md`
- Audit `job.source` and `syncrun.source` against current `sources`
- Block rollout if unmatched legacy keys exist before backfill
- Prepare duplicate-ownership checks for `(source_id, external_job_id)`

### Phase 2: Schema Expansion + Backfill

- Add nullable `source_id` columns to `job` and `syncrun`
- Add foreign keys and supporting indexes
- Backfill `source_id` from the existing legacy source key
- Stop here if unmatched or duplicate ownership rows are found

### Phase 3: Dual-Write

- Ensure new `job` and `syncrun` writes persist both `source_id` and legacy `source`
- Resolve direct job writes from legacy `source` to authoritative `source_id`
- Keep legacy `source` available for compatibility only

### Phase 4: Authoritative Read Path Cutover

- Move same-source job lookup to `source_id`
- Move close-missing logic to `source_id`
- Move overlap detection and sync-run history checks to `source_id`
- Limit fallback to legacy `source` to migration-only rows with null `source_id`

### Phase 5: Source Lifecycle Guardrails + API Compatibility

- Block delete when jobs or sync runs reference a source by `source_id`
- Block `platform` or `identifier` changes for referenced sources during the compatibility window
- Expose `source_id` in read models and job API responses without removing legacy `source`
- Add new job API integration coverage

### Phase 6: Constraint Enforcement

- Add a second Alembic revision after validation
- Set `job.source_id` and `syncrun.source_id` to `NOT NULL`
- Remove temporary fallback logic from runtime authoritative paths
- Remove authoritative dependency on old string-only unique/index behavior

### Phase 7: Cleanup Deferred

- Defer physical rename from `source` to `source_key`
- Defer removing compatibility payload fields until follow-up work
- Track future cleanup in roadmap and architecture docs after enforcement lands

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
