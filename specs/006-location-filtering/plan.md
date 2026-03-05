# Implementation Plan: Location Filtering (Hard Cutover)

**Branch**: `006-location-filtering` | **Date**: 2026-03-05 | **Spec**: [`/Users/nd/Developer/job/specs/006-location-filtering/spec.md`](/Users/nd/Developer/job/specs/006-location-filtering/spec.md)
**Input**: Backfilled feature spec aligned to current codebase; updated product direction requires removing compatibility location fields from API contracts.

## Summary

Perform a hard API contract cutover from legacy, flattened location fields to normalized location structures.

This plan intentionally does **not** keep backward compatibility for:

- `jobs` response field: `location_text`
- `matching` response fields: `location_text`, `city`, `region`, `country_code`, `workplace_type`

The system will return normalized location structures sourced from canonical location tables/links.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI, SQLModel, Pydantic  
**Storage**: PostgreSQL (`job`, `locations`, `job_locations`)  
**Testing**: pytest (unit + integration)  
**Project Type**: FastAPI backend service  
**Constraint**: Hard-cut API change (no compatibility layer)

## Layered Test Strategy (Write First)

To avoid regressions from a breaking contract change, tests are written first and organized by scope:

1. **Contract tests (schema-level, fast)**
   - Assert removed fields are absent from public Pydantic models.
   - Assert normalized location fields are present.
   - Enforce strict response contract for matching result items (no silent legacy extras).

2. **Integration tests (API shape)**
   - Assert `/api/v1/jobs` and `/api/v1/matching/recommendations` response payloads no longer include legacy location fields.
   - Assert normalized location structures are present and populated.

3. **Behavior tests (service/query)**
   - Assert country prefilter behavior remains intact.
   - Assert ambiguous location handling remains conservative.

All implementation changes must be gated by these layers passing in order: contract -> integration -> behavior.

## Contract Target (Post-Cutover)

### Jobs API

- Keep: `locations` (normalized list)
- Remove: `location_text` from `JobRead`
- Remove legacy write-time location fields from `JobCreate` / `JobUpdate`
  (`location_text`, `location_city`, `location_region`, `location_country_code`, `location_workplace_type`, `location_remote_scope`)

### Matching API

- Remove flattened location fields from `MatchResultItem`:
  `location_text`, `city`, `region`, `country_code`, `workplace_type`
- Introduce normalized `locations` list on result item, sourced from canonical
  `job_locations + locations` joins (no alternate compatibility shape)

## Implementation Phases

## Phase 1: Contract & Schema Layer

Goal: Define final response/request contracts first.

- Update `app/schemas/job.py`:
  - Drop `location_text` from `JobRead`
  - Drop deprecated legacy location fields from `JobCreate` and `JobUpdate`
- Update `app/schemas/match.py`:
  - Replace flattened location fields on `MatchResultItem` with normalized location object(s)
  - Tighten result model extra-field policy so removed legacy keys are not silently returned
- Ensure model docs reflect contract:
  - `app/schemas/README.md`

## Phase 2: API Mapping & Query Surfaces

Goal: Make handlers/services produce new contracts only.

- Update `app/api/v1/jobs.py` mapping:
  - Stop hydrating `location_text` in `_map_job_to_read`
- Update `app/services/infra/matching/query.py`:
  - Return columns needed for normalized location payload
  - Stop selecting legacy flattened output-only aliases
- Update `app/services/application/match_service/__init__.py` mapping if needed

## Phase 3: Downstream Consumers in Service Layer

Goal: Remove assumptions of flattened location fields in internal enrichers.

- Update `app/services/infra/matching/llm_rerank.py` payload builder to consume normalized location structure
- Update any helper code that still expects `location_text` on match rows

## Phase 4: Tests & Validation

Goal: Re-baseline contract tests to the new, breaking API.

- Update unit tests:
  - `tests/unit/test_match_schema.py`
  - `tests/unit/test_match_query.py`
  - `tests/unit/test_match_service.py`
  - `tests/unit/test_match_experiment_script.py`
  - `tests/unit/test_llm_match_recommendation.py` (if location payload assumptions exist)
- Update integration tests:
  - `tests/integration/test_matching_api.py`
  - `tests/integration/test_job_api.py` (if schema assertions need adjustment)
- Run full test subset for jobs/matching/location modules

## Risks & Mitigations

- Risk: Immediate client breakage.
  - Mitigation: Explicit release notes and endpoint contract announcement before merge.
- Risk: Hidden dependencies in scripts/tests expecting flattened fields.
  - Mitigation: grep-based audit + failing tests as enforcement gate.
- Risk: LLM rerank prompt quality regression after payload shape change.
  - Mitigation: targeted unit tests around payload generation and recommendation path.

## Done Criteria

- No legacy location compatibility fields in exposed job/matching API schemas.
- Matching responses expose only normalized location structure.
- Jobs read responses expose `locations` only.
- Updated tests pass for jobs + matching + location flows.
- Docs updated to match breaking contract.
