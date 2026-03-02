# Implementation Plan: Job Country Canonicalization V2

**Branch**: `003-country-canonicalization-v2-impl` | **Date**: 2026-03-02 | **Spec**: [`/specs/003-country-canonicalization-v2/spec.md`](/Users/nd/Developer/job/specs/003-country-canonicalization-v2/spec.md)
**Input**: Feature specification from `/specs/003-country-canonicalization-v2/spec.md`

## Summary

Make `job.location_country_code` reliable for country-aware filtering by normalizing high-confidence single-country inputs to a canonical uppercase country code on the existing `job` row.

The current codebase already has the field and already populates it in ingest and backfill flows, but the behavior is inconsistent:

1. Some source mappers persist raw country names such as `Canada` or `United States` instead of a canonical code.
2. The shared location helper still uses naive text heuristics that can manufacture wrong country values from abbreviations.
3. Historical repair logic protects existing values, but it does not yet distinguish canonical high-confidence country values from weak or invalid ones.

Implementation will therefore focus on rule quality and reuse, not schema expansion:

1. Add a canonical country metadata source plus repo-local alias and guard rules.
2. Centralize country normalization in shared domain logic that records confidence and source type.
3. Update mappers so explicit source-native country fields normalize to canonical codes and conservative text parsing only fills unambiguous single-country cases.
4. Update historical backfill so null, invalid, or weak country values can be repaired without downgrading already-good rows.
5. Ensure read/query surfaces rely on `location_country_code` directly and document that multi-location normalization remains deferred to v3.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI, SQLModel, SQLAlchemy/Alembic, asyncpg, `pycountry` for ISO metadata  
**Storage**: PostgreSQL for relational data, Supabase Storage for large job blobs  
**Testing**: pytest, pytest-asyncio, unit and integration suites under `tests/`  
**Target Platform**: Backend service and scheduled ingest scripts running on local dev / Linux-style server environments  
**Project Type**: FastAPI web service with database-backed ingest pipelines  
**Performance Goals**: Avoid query-time reparsing of `location_text`, keep ingest-time normalization cheap, and make country filtering safe to add on top of `job.location_country_code`  
**Constraints**: No new location tables, no PostGIS, no geocoding, no full city/region canonicalization, preserve `location_text` and remote/workplace semantics, keep multi-country cases null unless source-native structure already provides a deterministic primary country  
**Scale/Scope**: Touches dependency management, shared location/country normalization logic, source mappers, the existing location backfill script, repository batch helpers, match/read query surfaces, and targeted tests/docs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The repo's `.specify/memory/constitution.md` is still the default placeholder template, so there are no project-specific constitutional gates to enforce.

Operational gates for this feature:

- V2 must stay on the existing `job.location_country_code` field and must not introduce `locations` or `job_locations`.
- Explicit source-native country fields outrank inferred parsing from `location_text` or remote-scope text.
- Multi-country or supranational text must not be collapsed into one fabricated country value; the only allowed exception is the current spec's deterministic primary-country rule when that country is already explicit in source-native structure.
- Existing high-confidence canonical values must not be overwritten by lower-confidence inferred results during backfill.
- `location_text`, `location_city`, `location_region`, `location_workplace_type`, and `location_remote_scope` must remain intact through normalization.

## Project Structure

### Documentation (this feature)

```text
specs/003-country-canonicalization-v2/
├── plan.md
├── spec.md
└── tasks.md
```

### Source Code (repository root)

```text
app/
├── api/v1/
├── ingest/mappers/
├── repositories/
├── schemas/
└── services/

scripts/
└── backfill_job_locations.py

tests/
├── integration/
└── unit/
```

**Structure Decision**: Single backend service. V2 is an additive refinement of the existing v1 location model, so the work should stay within the current `job` row, shared domain helpers, mapper layer, backfill script, and query/read surfaces that already consume location fields.

## Implementation Strategy

### Phase A: Canonical Country Primitives

- Add `pycountry` as the ISO metadata reference source
- Introduce shared country normalization logic, preferably in a dedicated module such as `app/services/domain/country_normalization.py`
- Keep repo-local alias and guard rules authoritative for product-specific behavior such as `UK -> GB`, `UAE -> AE`, and rejecting ambiguous short tokens from free text
- Refactor `app/services/domain/job_location.py` so text parsing and remote-scope handling call the same country normalization rules as explicit source-native fields

### Phase B: Source Mapper Rollout

- Normalize explicit country values coming from structured source payloads before writing `location_country_code`
- Stop writing raw labels such as `Canada` or `United States` into `location_country_code`
- Allow conservative text-based country inference only for one clearly named country
- Preserve `location_remote_scope` and `location_workplace_type` independently from country identity
- Leave multi-country or region-only cases null unless a deterministic primary country is already explicit in source-native structure

### Phase C: Historical Repair

- Reuse the same shared country normalization logic from ingest during backfill
- Treat null, invalid, or non-canonical historical values as upgrade candidates
- Prefer source-native `raw_payload` re-extraction over reparsing display text
- Prevent lower-confidence text inference from replacing an already-good canonical country code

### Phase D: Query And Read Readiness

- Keep read/query code consuming `location_country_code` as the one canonical filter field on `job`
- Update matching and related query payloads to expect canonical alpha-2 codes
- If the matching stack is the first country-aware filter surface, wire any country filter directly to `location_country_code` rather than reparsing `location_text`

### Phase E: Documentation And Rollout Notes

- Document that v2 canonicalizes only the country field already on `job`
- Explicitly defer split tables and reusable canonical location entities to v3
- Capture any alias gaps or source-specific exceptions as follow-up work rather than broadening v2 into full location normalization

## Open Design Assumptions

- `location_country_code` remains the authoritative single-country filter field introduced in v1; no schema migration is required for v2.
- Canonical output should be uppercase ISO 3166-1 alpha-2 style codes unless the spec is revised later.
- Internal normalization should carry confidence/source information even if only the canonical code is persisted on `job`.
- `pycountry` should be treated as a reference dataset, not as the whole policy engine; repo-local alias and ambiguity rules remain authoritative.
- The first country-aware query surface for v2 will likely be the existing matching/retrieval stack rather than a new dedicated location API.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
