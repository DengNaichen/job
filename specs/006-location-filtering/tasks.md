# Tasks: Location Filtering (Hard Cutover)

**Input**: Design documents from `/Users/nd/Developer/job/specs/006-location-filtering/`  
**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Required. This change is intentionally breaking and must be enforced by schema, service, query, and API tests.

**Organization**: Tasks are grouped by user story and cutover phase so each slice is independently verifiable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: User story label (`[US1]`, `[US2]`, `[US3]`) for story-phase tasks
- Include exact file paths in each task

## Phase 0: Test Architecture (Write First, Blocking)

**Purpose**: Build a dedicated layered test harness for this feature before changing implementation.

- [x] T000 Create feature-scoped test folders under `/Users/nd/Developer/job/tests/location_contract/{contract,integration,behavior}` and add a short README describing layer scope.
- [x] T001 [P] Add contract tests in `/Users/nd/Developer/job/tests/location_contract/contract/` that assert legacy location fields are absent from public schemas.
- [x] T002 [P] Add integration tests in `/Users/nd/Developer/job/tests/location_contract/integration/` that assert jobs/matching API payloads exclude removed location fields.
- [x] T003 [P] Add behavior tests in `/Users/nd/Developer/job/tests/location_contract/behavior/` that assert country prefilter + ambiguous-location semantics remain unchanged.

**Checkpoint**: New layered tests exist and fail against current compatibility contract (red phase).

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Align feature docs with the hard-cut decision and lock implementation scope.

- [x] T004 Update `/Users/nd/Developer/job/specs/006-location-filtering/spec.md` to remove compatibility expectations and reflect hard API cutover semantics.
- [x] T005 Update `/Users/nd/Developer/job/specs/006-location-filtering/plan.md` contract notes (if needed) to match final response shape decision (`primary_location` vs `locations` in matching results).
- [x] T006 Add/refresh breaking-change note in `/Users/nd/Developer/job/docs/ROADMAP.md` (or equivalent release note location) for location contract removal.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define new API contracts first; implementation follows these schemas.

**CRITICAL**: No story implementation should proceed before this phase is complete.

- [x] T007 Update `/Users/nd/Developer/job/app/schemas/job.py` to remove legacy location write fields from `JobCreate`/`JobUpdate` and remove `location_text` from `JobRead`.
- [x] T008 Update `/Users/nd/Developer/job/app/schemas/match.py` to remove flattened location fields from `MatchResultItem`, introduce normalized location payload fields, and forbid silent legacy extras.
- [x] T009 [P] Update `/Users/nd/Developer/job/app/schemas/location.py` with any reusable location response models required by matching result contracts.
- [x] T010 [P] Update `/Users/nd/Developer/job/app/schemas/README.md` to document the new non-compatible location response/write contracts.

**Checkpoint**: Location API contracts are finalized and no longer include legacy compatibility fields.

---

## Phase 3: User Story 1 - Country-Scoped Matching Recommendations (Priority: P1) 🎯 MVP

**Goal**: Keep preferred-country filtering behavior while returning normalized location structure only.

**Independent Test**: Matching requests with and without `preferred_country_code` pass and return normalized location payloads with no legacy flattened fields.

### Tests for User Story 1

- [x] T011 [P] [US1] Promote or mirror coverage from `/Users/nd/Developer/job/tests/location_contract/contract/` into existing schema/query/service test suites where needed.
- [x] T012 [P] [US1] Promote or mirror coverage from `/Users/nd/Developer/job/tests/location_contract/integration/` into `/Users/nd/Developer/job/tests/integration/test_matching_api.py` where needed.

### Implementation for User Story 1

- [x] T013 [US1] Update `/Users/nd/Developer/job/app/services/infra/matching/query.py` SQL projection to produce normalized location payload inputs for match results.
- [x] T014 [US1] Update `/Users/nd/Developer/job/app/services/application/match_service/__init__.py` mapping so `MatchResultItem` is built from normalized location payload.
- [x] T015 [US1] Update `/Users/nd/Developer/job/app/services/infra/matching/llm_rerank.py` job-profile builder to read normalized location payload fields.

**Checkpoint**: Matching contract is hard-cut, and country prefilter behavior remains intact.

---

## Phase 4: User Story 2 - Stable Location Semantics for Ambiguous Inputs (Priority: P2)

**Goal**: Preserve conservative parsing semantics while removing legacy contract dependencies.

**Independent Test**: Ambiguous, multi-country, and supranational location cases remain conservative under the new payload shape.

### Tests for User Story 2

- [x] T016 [P] [US2] Update `/Users/nd/Developer/job/tests/unit/test_job_location.py` assertions that indirectly depended on legacy API field assumptions (if any) and keep conservative parsing cases intact.
- [x] T017 [P] [US2] Update `/Users/nd/Developer/job/tests/unit/test_llm_match_recommendation.py` (or equivalent LLM rerank tests) for normalized location payload input.
- [x] T018 [P] [US2] Update `/Users/nd/Developer/job/tests/unit/test_match_experiment_script.py` output expectations for normalized location result payload.

### Implementation for User Story 2

- [x] T019 [US2] Update `/Users/nd/Developer/job/scripts/match_experiment.py` output formatting/serialization to match the new matching schema location shape.
- [x] T020 [US2] Audit `/Users/nd/Developer/job/app/services/domain/job_location.py` and `/Users/nd/Developer/job/app/services/application/full_snapshot_sync/location_sync.py` for any response-contract-specific legacy assumptions and remove them.

**Checkpoint**: Conservative location semantics are preserved under the new contract-only location shape.

---

## Phase 5: User Story 3 - Hard Cutover for Jobs API Location Contract (Priority: P3)

**Goal**: Remove legacy location compatibility fields from jobs API read/write contracts and mappings.

**Independent Test**: Job create/update/read endpoints work without legacy location fields and return only normalized location data.

### Tests for User Story 3

- [x] T021 [P] [US3] Promote or mirror coverage from `/Users/nd/Developer/job/tests/location_contract/integration/` into `/Users/nd/Developer/job/tests/integration/test_job_api.py` where needed.
- [x] T022 [P] [US3] Update `/Users/nd/Developer/job/tests/unit/test_full_snapshot_sync.py` assertions only where they rely on API contract fields rather than canonical location persistence behavior.

### Implementation for User Story 3

- [x] T023 [US3] Update `/Users/nd/Developer/job/app/api/v1/jobs.py` `_map_job_to_read` to stop hydrating legacy `location_text`.
- [x] T024 [US3] Update `/Users/nd/Developer/job/app/services/application/job_payload.py` to drop legacy-location compatibility cleanup paths no longer needed by API write contracts.
- [x] T025 [US3] Update location-related mapper tests under `/Users/nd/Developer/job/tests/unit/ingest/mappers/` only where `JobCreate` schema changes require replacing legacy fields with normalized hints.

**Checkpoint**: Jobs API exposes normalized location structures only and no longer accepts/returns legacy location compatibility fields.

---

## Phase 6: Polish & Cross-Cutting

**Purpose**: Finish hard-cut rollout quality gates.

- [x] T026 Run layered contract tests first: `uv run pytest tests/location_contract/contract tests/location_contract/integration tests/location_contract/behavior`.
- [x] T027 Run targeted legacy suite: `uv run pytest tests/unit/test_match_schema.py tests/unit/test_match_query.py tests/unit/test_match_service.py tests/unit/test_match_experiment_script.py tests/integration/test_matching_api.py tests/integration/test_job_api.py`.
- [x] T028 Run broader location/matching regression tests and fix fallout in related modules.
- [x] T029 Update any remaining docs/examples that still reference removed fields (`location_text`, `city`, `region`, `country_code`, `workplace_type` in matching output).

---

## Dependencies & Execution Order

- Phase 0 must complete before any implementation work.
- Phase 1 must complete before Phase 2.
- Phase 2 is blocking for all user-story phases.
- US1 should ship first as MVP cutover slice.
- US2 and US3 can proceed in parallel after US1 contract plumbing stabilizes.
- Phase 6 runs after all story phases are complete.

## Parallel Execution Examples

- Run `T001`, `T002`, `T003` in parallel (different new test files).
- Run `T009` and `T010` in parallel during foundational setup.
- Run `T016`, `T017`, `T018` in parallel for semantic regression coverage.
- Run `T021` and `T022` in parallel for jobs-facing test updates.

## Implementation Strategy

- Implement test-first by layer (contract -> integration -> behavior), then code changes.
- Merge as one hard-cut release boundary (no mixed compatibility mode).
- Keep query/filter behavior stable while changing response shape.
- Treat failing tests as migration checklist, not as optional cleanup.
