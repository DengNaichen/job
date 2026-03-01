# Implementation Plan: Job Location Modeling V1

**Branch**: `002-location-modeling-v1-impl` | **Date**: 2026-03-01 | **Spec**: [`/specs/002-location-modeling-v1/spec.md`](/Users/nd/Developer/job/specs/002-location-modeling-v1/spec.md)
**Input**: Feature specification from `/specs/002-location-modeling-v1/spec.md`

## Summary

Add a best-effort structured location profile directly onto `job` while preserving `location_text` as the compatibility and display field.

Implementation will be staged:

1. Expand the `job` schema with nullable structured location columns and a normalized workplace-type enum.
2. Introduce shared extraction/parsing helpers so mappers can populate structured location data conservatively.
3. Update source mappers to use source-native structure first and text parsing second.
4. Backfill existing jobs from `raw_payload` first, then `location_text`, without overwriting higher-confidence values.
5. Expose the new fields in read/query models needed by future retrieval work while keeping current API compatibility.
6. Document the rollout and explicitly defer `locations + job_locations` to a later feature.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI, SQLModel, SQLAlchemy/Alembic, asyncpg  
**Storage**: PostgreSQL for relational data, Supabase Storage for large job blobs  
**Testing**: pytest, pytest-asyncio, unit and integration suites under `tests/`  
**Target Platform**: Backend service and scheduled ingest scripts running on local dev / Linux-style server environments  
**Project Type**: FastAPI web service with database-backed ingest pipelines  
**Performance Goals**: Keep hot ingest work cheap, avoid query-time reparsing of `location_text`, and prepare indexed structured location fields for later retrieval work  
**Constraints**: No geocoding in hot paths, no LLM-based location parsing, no destructive rewrite of existing `location_text`, no canonical `locations` dimension in v1  
**Scale/Scope**: Touches Alembic migrations, SQLModel models, job schemas, source mappers, a new shared location helper, a backfill script, match/query read paths, and targeted tests/docs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The repo's `.specify/memory/constitution.md` is still the default placeholder template, so there are no project-specific constitutional gates to enforce.

Operational gates for this feature:

- Schema rollout must be additive first: nullable columns before any future retrieval logic depends on them.
- Source-native structured fields outrank inferred text parsing during ingest and backfill.
- `location_text` must remain available in job read paths during the v1 rollout.
- Workplace mode must be modeled independently from `employment_type`.
- V1 must stop at one structured location profile per job and explicitly defer canonical multi-location modeling.

## Project Structure

### Documentation (this feature)

```text
specs/002-location-modeling-v1/
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
├── ingest/mappers/
├── models/
├── repositories/
├── schemas/
└── services/

scripts/
└── backfill_structured_jd.py

tests/
├── integration/
├── unit/
└── test_mappers_*.py
```

**Structure Decision**: Single backend service. This feature is centered on `job` model/storage changes, shared location extraction logic, mapper updates, and read/query surfaces that will later support location-aware retrieval.

## Implementation Strategy

### Phase A: Schema And Shared Primitives

- Add nullable structured location columns to `job`
- Add a workplace-type enum in the model/schema layer
- Introduce a shared location extraction/parsing helper used by both ingest and backfill

### Phase B: Source Mapper Rollout

- Update source mappers to populate structured location fields from explicit payload structure where available
- Apply conservative text parsing only for well-known low-risk patterns
- Separate workplace-mode extraction from `employment_type`

### Phase C: Historical Backfill

- Add a dedicated backfill script for structured job location fields
- Prefer `raw_payload` re-extraction over reparsing `location_text`
- Protect previously populated high-confidence values from lower-confidence overrides

### Phase D: Retrieval Readiness And Compatibility

- Expose structured location fields in read schemas and query payloads that will feed future retrieval work
- Keep `location_text` available for existing clients and operator workflows
- Update docs to reflect that v1 is a staging layer, not full location normalization

## Open Design Assumptions

- This plan assumes the v1 field names from the spec: `location_city`, `location_region`, `location_country_code`, `location_workplace_type`, and `location_remote_scope`.
- This plan assumes `location_workplace_type` should be modeled as a string enum in the database/application layer rather than as a free-text field.
- This plan assumes a deterministic primary-location rule is good enough for sources that expose multiple locations; richer multi-location support remains future work.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
