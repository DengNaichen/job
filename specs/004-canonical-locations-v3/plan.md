# Implementation Plan: Canonical Locations V3

**Branch**: `004-canonical-locations-v3` | **Date**: 2026-03-02 | **Spec**: [`/specs/004-canonical-locations-v3/spec.md`](/Users/nd/Developer/job/specs/004-canonical-locations-v3/spec.md)
**Input**: Feature specification from `/specs/004-canonical-locations-v3/spec.md`

## Summary

Move location identity from one denormalized profile on `job` into reusable canonical entities by introducing `locations + job_locations`, while preserving v1/v2 job-level location fields as compatibility state during rollout.

The current codebase already has useful staging data (`location_city`, `location_region`, `location_country_code`, `location_workplace_type`, `location_remote_scope`), but it still cannot model reusable or multi-location relationships:

1. One job row can only represent one primary location profile.
2. Equivalent places across jobs are duplicated as strings instead of canonical entities.
3. Physical location and remote-eligibility scope cannot be represented independently as linked entities.
4. Country-aware filtering and future location-aware retrieval still depend on denormalized fields.

Implementation will focus on normalized identity + relationship modeling, not geometry:

1. Add `Location` and `JobLocation` entities with deterministic canonical keys and constraints for reuse/idempotency.
2. Introduce shared canonicalization logic that uses local GeoNames reference data plus repo-owned normalization rules.
3. Persist canonical location links during ingest and keep compatibility fields aligned from one deterministic primary link.
4. Backfill historical jobs into normalized links using v1/v2 structured fields first and `raw_payload` second.
5. Update read/query paths to consume normalized links for multi-location and country-aware behavior without dropping compatibility fields yet.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI, SQLModel, SQLAlchemy/Alembic, asyncpg, pycountry, local GeoNames reference files (downloaded/offline)  
**Storage**: PostgreSQL (authoritative app data), Supabase Storage (large blobs), local artifact files for GeoNames reference metadata  
**Testing**: pytest, pytest-asyncio, unit + integration suites under `tests/`  
**Target Platform**: Backend service and scheduled scripts in local dev / Linux-style server runtime  
**Project Type**: FastAPI backend with mapper-driven ingest + batch backfill scripts  
**Performance Goals**: Reuse canonical location rows across jobs, keep ingest/backfill idempotent, support normalized joins for country/multi-location filtering without query-time reparsing of `location_text`  
**Constraints**: No PostGIS, no geocoding API dependency, no radius/distance ranking, preserve `job.location_*` fields during rollout, keep workplace semantics (`remote/hybrid/onsite`) independent from `employment_type`  
**Scale/Scope**: Touches Alembic migrations, SQLModel entities, repositories, domain canonicalization, ingest sync pipeline, backfill scripts, match/read query surfaces, and docs/tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The repo's `.specify/memory/constitution.md` is still the default placeholder template, so there are no project-specific constitutional gates to enforce.

Operational gates for this feature:

- V3 must introduce `locations` and `job_locations` as reusable normalized entities and make them the long-term authoritative location identity model.
- Canonicalization must be deterministic and rerunnable; unchanged inputs must not create duplicate `locations` rows or duplicate `job_locations` links.
- Every job with links must have at most one deterministic primary link used for compatibility-field alignment and summary behavior.
- Compatibility fields on `job` must remain populated during rollout and must stay aligned with the primary-link rule.
- Country and location-aware query paths must be able to use normalized links; `location_text` reparsing is not an acceptable long-term retrieval strategy.
- PostGIS/geospatial infra remains explicitly out of scope for v3.

## Project Structure

### Documentation (this feature)

```text
specs/004-canonical-locations-v3/
├── plan.md
├── spec.md
└── tasks.md
```

### Source Code (repository root)

```text
alembic/
└── versions/

app/
├── core/
├── models/
├── repositories/
├── services/
│   ├── application/
│   ├── domain/
│   └── infra/
├── schemas/
├── ingest/
│   └── mappers/
└── api/v1/

scripts/
├── backfill_job_locations.py
└── (new) backfill_job_locations_v3.py

tests/
├── integration/
└── unit/
```

**Structure Decision**: Keep location normalization fully app-owned in this repo: canonicalization logic in domain services, authoritative persistence in Postgres `locations + job_locations`, ingest/backfill/query integration through existing service/repository layers, and GeoNames used as local reference metadata only.

## Implementation Strategy

### Phase A: Normalized Schema + Entity Foundations

- Add `Location` model in `app/models/location.py` with deterministic `canonical_key` uniqueness and fields required for reusable identity (`location_kind`, precision level, country/region/city, remote scope, optional GeoNames reference identifiers, display name, normalization metadata).
- Add `JobLocation` model in `app/models/job_location.py` with `job_id + location_id` uniqueness, `is_primary`, deterministic ordering metadata, and provenance/confidence metadata.
- Add Alembic migration for `locations` and `job_locations`, including indexes for canonical lookup, country filter joins, and one-primary-per-job enforcement.
- Update `app/models/__init__.py` plus model docs.

### Phase B: Canonicalization + Primary-Link Domain Rules

- Introduce shared domain logic (for example `app/services/domain/canonical_location.py`) that:
  - builds candidate location identities from structured fields and source payload hints,
  - resolves canonical identity with local GeoNames reference metadata when possible,
  - falls back to deterministic repo-owned normalization for unsupported/partial cases,
  - emits stable `canonical_key` values so formatting differences do not create new entities.
- Define one deterministic primary-link policy (confidence, precision, source order, stable tie-break by canonical key).
- Keep workplace semantics and remote-scope semantics explicit in canonical location identity instead of overloading employment fields.

### Phase C: Ingest Write Path Integration (US1)

- Extend mapper/sync pipeline so a mapped job can yield one or more canonical location candidates.
- In `FullSnapshotSyncService`, persist new/updated job rows and canonical location links in one transaction.
- Reuse existing rows via `locations.canonical_key` upsert semantics.
- Rebuild a job's link set deterministically per ingest run (idempotent merge semantics) and mark exactly one primary link.
- Keep `job.location_*` compatibility fields synchronized from the chosen primary link (or deterministic compatibility fallback rule).

### Phase D: Historical Backfill Integration (US2)

- Add `scripts/backfill_job_locations_v3.py` (or equivalent v3 mode) that:
  - reads v1/v2 structured fields first,
  - uses `raw_payload` extraction second when additional high-confidence locations are available,
  - creates/reuses canonical `locations` rows,
  - upserts `job_locations` links and deterministic primary flags,
  - aligns compatibility fields from primary-link output,
  - is safe to rerun without duplicate drift.
- Add repository helpers for keyset-pagination and backfill candidate selection.

### Phase E: Read/Query Cutover + Documentation (US3)

- Add read-model support for primary location summary + full linked set from normalized tables (without breaking existing job API compatibility fields).
- Update matching/country-aware query paths to filter via normalized links (`job_locations -> locations`) instead of only `job.location_country_code`.
- Keep optional denormalized helpers during rollout, but document normalized tables as the authoritative long-term model.
- Update architecture/roadmap docs to move v3 from deferred to active migration path.

## Open Design Assumptions

- GeoNames reference metadata is consumed from local downloaded files/artifacts and versioned operationally; hosted GeoNames APIs are not used in request-time logic.
- V3 persists only locations referenced by jobs; it does not pre-import every GeoNames place into `locations`.
- One job may link to both physical and remote-scope locations; exactly one link remains primary for compatibility behavior.
- Canonicalization rule improvements should update/reuse existing canonical identities rather than creating formatting-only duplicates.
- Compatibility fields on `job` remain present through rollout even though normalized entities become authoritative for reusable identity.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
