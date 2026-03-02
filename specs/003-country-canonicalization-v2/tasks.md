# Tasks: Job Country Canonicalization V2

**Input**: Design documents from `/specs/003-country-canonicalization-v2/`
**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Tests are required for this feature because the spec depends on conservative normalization, alias handling, safe backfill behavior, and query paths that can trust `location_country_code`.

**Organization**: Tasks are grouped by user story so each slice can be validated independently once the shared country normalization rules exist.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel
- **[Story]**: Maps to the user story in `spec.md`
- Every task lists concrete file paths that should be changed or created

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Establish one shared canonical country policy before changing mappers, backfill behavior, or query/read paths.

- [x] T001 Add `pycountry` to `pyproject.toml` and refresh `uv.lock` so the repo has a stable ISO country metadata source for canonical normalization.
- [x] T002 Create shared country normalization primitives in `app/services/domain/country_normalization.py` for alias mapping, ambiguity guards, multi-country detection, and confidence/source tracking.
- [x] T003 Refactor `app/services/domain/job_location.py` to compose the shared country normalizer for explicit country fields, conservative location-text parsing, and remote-scope extraction while preserving the existing `StructuredLocation` contract.
- [x] T004 [P] Update `app/models/README.md` and `app/schemas/README.md` to document that `location_country_code` now stores a canonical single-country code rather than raw display text.

**Checkpoint**: Shared country normalization rules exist and can be reused consistently by ingest, backfill, and query/read code without any schema change.

---

## Phase 2: User Story 1 - Normalize Country Codes For New And Updated Jobs (Priority: P1) 🎯 MVP

**Goal**: Ensure new and updated jobs store canonical country codes only for high-confidence single-country cases.

**Independent Test**: Ingest representative fixtures containing explicit country fields, country names inside location text, single-country remote scopes, and ambiguous abbreviations, then verify that canonical alpha-2 country codes appear only when the input is unambiguous.

### Tests for User Story 1

- [x] T005 [P] [US1] Expand `tests/unit/test_job_location.py` to cover explicit country alias mapping, canonical code output, ambiguous abbreviations such as `CA`, single-country remote scope, multi-country remote scope, and supranational-region cases.
- [x] T006 [P] [US1] Update `tests/unit/ingest/mappers/test_company_apis.py` and `tests/unit/ingest/mappers/test_smartrecruiters.py` so structured source-native country fields normalize to canonical alpha-2 codes instead of raw names.
- [x] T007 [P] [US1] Update `tests/unit/ingest/mappers/test_eightfold.py`, `tests/unit/ingest/mappers/test_lever.py`, `tests/unit/ingest/mappers/test_greenhouse.py`, and `tests/unit/ingest/mappers/test_ashby.py` to cover conservative text inference for one clear country and null outputs for ambiguous multi-country cases.
- [x] T008 [P] [US1] Update `tests/unit/test_job_service.py` and `tests/integration/test_job_api.py` if needed so direct create/update and read paths continue to round-trip canonical country codes without reverting to display names.

### Implementation for User Story 1

- [x] T009 [US1] Update `app/ingest/mappers/apple.py`, `app/ingest/mappers/smartrecruiters.py`, `app/ingest/mappers/uber.py`, and `app/ingest/mappers/tiktok.py` to normalize explicit source-native country fields through the shared country helper.
- [x] T010 [US1] Update `app/ingest/mappers/eightfold.py`, `app/ingest/mappers/lever.py`, `app/ingest/mappers/greenhouse.py`, and `app/ingest/mappers/ashby.py` to use conservative text and remote-scope normalization, preserving null for ambiguous multi-country or region-only cases.
- [x] T011 [US1] Update `app/ingest/mappers/base.py` and any shared mapper plumbing needed so mappers stop hand-writing raw country strings into `location_country_code` and instead funnel through one canonical normalization path.

**Checkpoint**: New ingests write canonical country codes for high-confidence single-country cases and keep ambiguous cases null without losing compatibility text.

---

## Phase 3: User Story 2 - Repair Historical Country Codes Safely (Priority: P2)

**Goal**: Upgrade historical rows to canonical country codes where confidence is high, without downgrading already-good data.

**Independent Test**: Run the country normalization backfill against mixed-confidence fixtures and verify that null, invalid, or non-canonical historical values are repaired, ambiguous rows stay null, and reruns do not oscillate.

- [x] T012 [P] [US2] Expand `tests/unit/test_backfill_job_locations.py` to cover upgrading raw country names/codes to canonical alpha-2 values, repairing invalid or weak historical data, preserving canonical high-confidence values, and leaving multi-country or supranational rows untouched.
- [x] T013 [P] [US2] Update `tests/unit/test_import_company_api_jobs.py`, `tests/unit/test_import_greenhouse_jobs.py`, `tests/unit/test_import_lever_jobs.py`, `tests/unit/test_import_ashby_jobs.py`, `tests/unit/test_import_smartrecruiters_jobs.py`, and `tests/unit/test_import_eightfold_jobs.py` so persisted/imported expectations reflect canonical country codes.

### Implementation for User Story 2

- [x] T014 [US2] Update `scripts/backfill_job_locations.py` so `location_country_code` is repaired from `raw_payload` first and `location_text` or `location_remote_scope` second, while protecting existing high-confidence canonical values from lower-confidence overrides.
- [x] T015 [US2] Extend `app/repositories/job.py` with any batch selection helpers needed to target rows whose `location_country_code` is null, invalid, or non-canonical without repeatedly scanning unrelated jobs.
- [x] T016 [US2] Reuse `app/services/domain/country_normalization.py` and `app/services/domain/job_location.py` from the backfill path so ingest and historical repair follow identical alias, ambiguity, and confidence rules.

**Checkpoint**: Historical jobs can be upgraded to canonical country codes safely and rerun without confidence downgrades or value oscillation.

---

## Phase 4: User Story 3 - Defer Full Canonical Location Modeling (Priority: P3)

**Goal**: Make canonical country data consumable by query/read paths while explicitly keeping split tables and full multi-location normalization out of scope.

**Independent Test**: Verify that country-aware query paths can rely on `location_country_code` directly and that no part of the rollout requires `locations + job_locations`, geocoding, or spatial infrastructure.

### Tests for User Story 3

- [x] T017 [P] [US3] Update `tests/unit/test_match_query.py`, `tests/unit/test_match_schema.py`, and `tests/unit/test_match_service.py` so match-oriented rows and response models expect canonical alpha-2 country codes.
- [x] T018 [P] [US3] Update `tests/unit/test_llm_match_recommendation.py`, `tests/unit/test_match_experiment_script.py`, and `tests/integration/test_matching_api.py` to keep downstream payloads compatible once country codes are canonical and, if added in this increment, country filters flow through the matching stack.

### Implementation for User Story 3

- [x] T019 [US3] Update `app/schemas/match.py`, `app/services/application/match_service.py`, `app/services/infra/match_query.py`, and `app/services/infra/llm_match_recommendation.py` so country-aware query code relies on `location_country_code` directly rather than reparsing `location_text`, and add optional country filter plumbing if the matching endpoint is the first rollout surface.
- [x] T020 [US3] Update `app/api/v1/matching.py`, `docs/architecture/README.md`, and `docs/ROADMAP.md` to document that v2 stops at canonical country normalization on `job` and explicitly defers reusable canonical location entities and split tables to v3.

**Checkpoint**: Canonical country data is consumable by query/read paths, while full canonical location modeling remains clearly deferred.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validate the rollout end to end and record follow-up normalization gaps without broadening feature scope.

- [x] T021 [P] Run targeted test suites for changed paths with `./scripts/uv run pytest tests/unit/test_job_location.py tests/unit/ingest/mappers/test_company_apis.py tests/unit/ingest/mappers/test_smartrecruiters.py tests/unit/ingest/mappers/test_eightfold.py tests/unit/ingest/mappers/test_lever.py tests/unit/ingest/mappers/test_greenhouse.py tests/unit/ingest/mappers/test_ashby.py tests/unit/test_job_service.py tests/integration/test_job_api.py tests/unit/test_backfill_job_locations.py tests/unit/test_import_company_api_jobs.py tests/unit/test_import_greenhouse_jobs.py tests/unit/test_import_lever_jobs.py tests/unit/test_import_ashby_jobs.py tests/unit/test_import_smartrecruiters_jobs.py tests/unit/test_import_eightfold_jobs.py tests/unit/test_match_query.py tests/unit/test_match_schema.py tests/unit/test_match_service.py tests/unit/test_llm_match_recommendation.py tests/unit/test_match_experiment_script.py tests/integration/test_matching_api.py`.
- [ ] T022 Do a manual dry run of `scripts/backfill_job_locations.py` against a small dataset and record which rows upgraded from raw names or weak codes to canonical codes and which ambiguous rows intentionally stayed null.
- [ ] T023 Capture follow-up work in `docs/ROADMAP.md` or `specs/004-canonical-locations-v3/spec.md` for normalized location entities, multi-country link modeling, and any broader retrieval/filter rollout that should not block v2.

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 blocks all user story work because mapper rollout, backfill, and query/read changes all depend on one shared normalization policy.
- User Story 1 depends on Phase 1 and delivers the MVP canonicalization behavior for new ingests.
- User Story 2 depends on Phase 1 and should reuse the same normalization logic already exercised by User Story 1.
- User Story 3 depends on canonical ingest outputs from User Story 1 and is safest once the backfill behavior from User Story 2 is stable enough for mixed old/new data.
- Polish depends on the phases you intend to ship in this increment.

### User Story Dependencies

- **US1 (P1)**: Required MVP slice. No dependency on other user stories once Phase 1 is complete.
- **US2 (P2)**: Depends on the shared normalization primitives from Phase 1 and should follow the same ingest rules established in US1.
- **US3 (P3)**: Depends on the canonical field behavior stabilized by US1 and benefits from US2 so query results are consistent across historical rows.

### Parallel Opportunities

- T001 and T004 can run in parallel once the canonical country format is finalized.
- T005, T006, T007, and T008 can run in parallel as US1 coverage work.
- T012 and T013 can run in parallel for backfill-related validation.
- T017 and T018 can run in parallel for query/read compatibility coverage.

## Implementation Strategy

### MVP First

1. Finish Phase 1.
2. Finish User Story 1.
3. Run the shared-helper and mapper tests to prove new ingests persist canonical country codes without breaking `location_text` or remote/workplace semantics.

### Incremental Delivery

1. Ship shared normalization rules and mapper rollout.
2. Ship historical country repair tooling.
3. Ship query/read alignment for canonical country consumption.
4. Ship documentation updates that keep v2 scoped to the existing `job` row and defer split tables to v3.

## Notes

- V2 should not introduce any Alembic migration or new location tables.
- `location_country_code` should store canonical country codes only, not raw display labels.
- Prefer source-native structured country extraction over generalized text parsing.
- Treat ambiguous geography as null rather than manufacturing a country value.
- Preserve `location_text` and `location_remote_scope` for display and compatibility semantics.
- Keep full multi-location and reusable canonical location modeling in v3 even if some source payloads expose richer location structure today.
