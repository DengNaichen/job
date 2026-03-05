# Research: JD Structured Extraction (002)

## Scope

Determine what data model is required for feature `002-jd-structured-extraction`, given the repository already contains structured JD schemas and persistence logic.

## Inputs Reviewed

- Core schema and projection logic:
  - `app/schemas/structured_jd.py`
- Persistence and application orchestration:
  - `app/services/application/jd_parsing/structured_jd.py`
  - `app/services/application/jd_parsing/orchestrator.py`
  - `app/services/application/jd_parsing/batch.py`
  - `app/services/application/jd_parsing/single.py`
- Existing persisted fields:
  - `app/models/job.py`
  - `app/repositories/job.py`
- Existing data-model doc pattern:
  - `docs/data-model/location.md`
  - `specs/006-location-filtering/data-model.md`
- Roadmap and docs references:
  - `docs/ROADMAP.md`
  - `README.md`
- Focused verification tests:
  - `tests/unit/test_jd_parser.py`
  - `tests/unit/test_structured_jd_schema.py`
  - `tests/unit/test_job_service.py`

## Current-State Findings

1. Structured JD extraction core is already implemented
- Typed schema (`StructuredJD`, `BatchStructuredJDItem`) exists.
- Compact LLM contract models (`CompactStructuredJD`, `CompactBatchStructuredJD`) exist.
- Rule-based deterministic extraction exists and merges with LLM outputs.
- Persistence to `job.structured_jd` plus typed projection columns already exists.

2. Persisted model already includes canonical typed fields on `job`
- `sponsorship_not_available`
- `job_domain_raw`
- `job_domain_normalized`
- `min_degree_level`
- `min_degree_rank`
- `structured_jd_version`
- `structured_jd` (JSONB)
- `structured_jd_updated_at`

3. Query-time consumers already rely on this model
- Matching query filters on `COALESCE(j.structured_jd_version, 0) >= 3`.

4. Productization gap is orchestration entrypoints, not schema primitives
- README references `scripts/backfill_structured_jd.py` and `scripts/batch_parse_jd.py`, but these scripts are currently absent.

## Decision 1: 002 should not introduce a new persistence table for MVP

Rationale:
- Existing `job` schema already stores both compact structured payload and typed query columns.
- Current matching path depends on these fields and is compatible with existing data.
- Adding a new table now would create migration and dual-write complexity without clear functional gain.

Alternatives considered:
- Add `job_structured_jd` table now: rejected for MVP due to operational complexity and no immediate query requirement.

## Decision 2: Define 002 data model in two layers (recommended)

1) Canonical model doc in `docs/data-model/structured-jd.md`
- Source of truth for long-lived entities and value objects.

2) Feature delta doc in `specs/002-jd-structured-extraction/data-model.md`
- Only documents what 002 changes/relies on.
- References canonical docs to avoid duplication.

Rationale:
- Matches existing pattern used by `006-location-filtering`.
- Keeps feature specs concise while preserving reusable domain documentation.

## Decision 3: 002 data model should include these explicit objects

### Persisted Entity (existing)
- `Job` structured extraction fields (listed above).

### Persisted Subdocument (existing)
- `StructuredJDPayload` inside `job.structured_jd`:
  - `required_skills`
  - `preferred_skills`
  - `experience_requirements`
  - `education_requirements`
  - `key_responsibilities`
  - `keywords`
  - `experience_years`
  - `seniority_level`
  - `job_domain_raw`

### Typed Projection (existing)
- `StructuredJDProjection` materialized to job columns:
  - sponsorship/domain/degree/version fields used by filtering and ranking.

### Pipeline Value Objects (existing, not persisted)
- `CompactStructuredJD`
- `CompactBatchStructuredJD`
- `BatchStructuredJDItem`
- `BatchStructuredJD`

## Decision 4: Defer parse-run audit model to post-MVP unless required

Potential future model (deferred):
- `StructuredJDParseRun` table with run-level audit:
  - `id`, `started_at`, `finished_at`, `status`, `processed_count`, `failed_count`, `error_summary`
- Optional per-job parse status fields (or side table) for retries and observability.

Rationale:
- Useful for ops at scale, but not required to ship 002 core behavior.
- Can be introduced once CLI/API orchestration is implemented and telemetry needs are concrete.

## Recommended 002 Data-Model Deliverables

1. Add canonical doc:
- `docs/data-model/structured-jd.md`

2. Add feature delta doc:
- `specs/002-jd-structured-extraction/data-model.md`

3. In 002 spec, explicitly state:
- No new DB table for MVP.
- `job` remains source of truth for structured extraction outputs.
- Versioning contract remains `structured_jd_version = 3` baseline.

## Validation Evidence

Executed:

```bash
./.venv/bin/pytest tests/unit/test_jd_parser.py tests/unit/test_structured_jd_schema.py tests/unit/test_job_service.py -q
```

Result: `17 passed`

## Result

For 002, the required data model is primarily documentation and contract formalization of already-implemented `Job + StructuredJD` structures. New persistence tables are not required for MVP.
