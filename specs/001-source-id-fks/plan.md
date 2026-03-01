# Implementation Plan: Source ID Ownership Migration

**Branch**: `001-source-id-fks-impl` | **Date**: 2026-03-01 | **Spec**: [`/specs/001-source-id-fks/spec.md`](/Users/nd/Developer/job/specs/001-source-id-fks/spec.md)
**Input**: Feature specification from `/specs/001-source-id-fks/spec.md`

## Summary

Move `job` and `syncrun` ownership from the mutable legacy source string to authoritative `source_id` foreign keys while preserving the existing source key for compatibility during rollout.

Implementation will be staged:

1. Expand the schema with nullable `source_id`, indexes, and foreign keys.
2. Backfill existing rows from the stored legacy source key.
3. Dual-write `source_id` plus the legacy key on new job and sync-run writes.
4. Cut authoritative read paths over to `source_id`.
5. Block source mutations that would invalidate compatibility data during the migration window.
6. Preserve API compatibility by exposing `source_id` without removing the legacy source key.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI, SQLModel, SQLAlchemy/Alembic, asyncpg, tenacity  
**Storage**: PostgreSQL for relational data, Supabase Storage for large job blobs  
**Testing**: pytest, pytest-asyncio, unit and integration suites under `tests/`  
**Target Platform**: Backend service and scheduled ingest scripts running on local dev / Linux-style server environments  
**Project Type**: FastAPI web service with database-backed ingest pipelines  
**Performance Goals**: Preserve current full-snapshot ingest semantics with indexed same-source lookups and no new unbounded scans in hot sync paths  
**Constraints**: No data loss, no orphaned rows, no same-day API break, no physical rename of `source` column in the same change that introduces `source_id`  
**Scale/Scope**: Touches Alembic migrations, SQLModel models, repositories, sync services, source lifecycle safeguards, API schemas, and targeted unit/integration tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The repo's `.specify/memory/constitution.md` is still the default placeholder template, so there are no project-specific constitutional gates to enforce.

Operational gates for this feature:

- Migration must be additive first: add nullable columns and backfill before `NOT NULL` enforcement.
- Existing API payloads must remain readable by clients that still depend on the legacy `source` key.
- Same-source reconcile and overlap guard behavior must be covered by updated automated tests before rollout.
- Source mutation rules must prevent `platform` or `identifier` drift for referenced sources during the compatibility window.

## Project Structure

### Documentation (this feature)

```text
specs/001-source-id-fks/
├── plan.md
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

scripts/
└── run_scheduled_ingests.py

tests/
├── integration/
└── unit/
```

**Structure Decision**: Single backend service. The migration spans database revisions in `alembic/versions/`, model/schema updates under `app/`, and validation in `tests/unit/` plus `tests/integration/`.

## Implementation Strategy

### Phase A: Schema Expansion And Backfill

- Add nullable `source_id` to `job` and `syncrun`
- Add FK and index support
- Backfill `source_id` from the stored legacy source key
- Fail fast if any row cannot be resolved to a current `Source`

### Phase B: Authoritative Read/Write Cutover

- Dual-write `source_id` and the legacy source string in ingest paths
- Move same-source job lookups, close-missing logic, and overlap detection to `source_id`
- Keep temporary legacy fallback only where needed for migration safety

### Phase C: Source Lifecycle Guardrails

- Block delete when jobs or sync runs reference a source
- Block `platform` or `identifier` changes for referenced sources during the compatibility window

### Phase D: Compatibility And Verification

- Expose `source_id` in read models without removing the legacy key
- Update tests around sync, repositories, source service, and source API behavior
- Document manual migration validation steps before rollout

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
