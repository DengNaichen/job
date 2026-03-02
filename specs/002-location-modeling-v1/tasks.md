# Tasks: Job Location Modeling V1

**Input**: Design documents from `/specs/002-location-modeling-v1/`
**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Tests are required for this feature because the spec depends on conservative extraction, safe backfill behavior, and compatibility across ingest, read APIs, and future retrieval-oriented query paths.

**Organization**: Tasks are grouped by user story so each slice can be validated independently once the schema and shared location primitives exist.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel
- **[Story]**: Maps to the user story in `spec.md`
- Every task lists concrete file paths that should be changed or created

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Add schema support and shared location primitives before changing mapper behavior or historical data.

- [x] T001 Create an Alembic revision in `alembic/versions/` that adds nullable `job` columns for `location_city`, `location_region`, `location_country_code`, `location_workplace_type`, and `location_remote_scope`.
- [x] T002 [P] Update `app/models/job.py` to add the new structured location fields and define the workplace-type enum/defaults used by the application layer.
- [x] T003 [P] Update `app/schemas/job.py` so `JobCreate`, `JobRead`, and `JobUpdate` support the structured location fields while preserving `location_text`.
- [x] T004 [P] Update `app/models/README.md` and `app/schemas/README.md` to document the new job-level location fields and clarify that `location_text` remains compatibility/display text.
- [x] T005 Create shared extraction/parsing helpers in `app/services/domain/job_location.py` that can build one best-effort structured location profile from source-native payloads or conservative text parsing.

**Checkpoint**: The database, model layer, schemas, and shared location helper are ready for mapper rollout and backfill work.

---

## Phase 2: User Story 1 - Persist Filterable Location Structure on `job` (Priority: P1) 🎯 MVP

**Goal**: Persist structured location fields during ingest without breaking current job creation or compatibility fields.

**Independent Test**: Ingest representative source fixtures and verify that structured location fields are populated when source-native structure exists, while ambiguous text remains primarily in `location_text`.

### Tests for User Story 1

- [x] T006 [P] [US1] Update `tests/test_mappers.py`, `tests/test_mappers_lever.py`, and `tests/test_mappers_ashby.py` to cover conservative parsing for text-heavy sources, including remote and workplace-type cases.
- [x] T007 [P] [US1] Update `tests/test_mappers_smartrecruiters.py`, `tests/test_mappers_company_apis.py`, and `tests/test_mappers_eightfold.py` to cover direct extraction of structured location data from payloads that already expose city/region/country-like fields.
- [x] T008 [P] [US1] Add focused unit coverage for the shared helper in `tests/unit/test_job_location.py`, including confidence ordering and remote-scope parsing behavior.
- [x] T009 [P] [US1] Update `tests/unit/test_job_service.py` for create/update behavior that now round-trips the new structured location fields.

### Implementation for User Story 1

- [x] T010 [US1] Update `app/ingest/mappers/smartrecruiters.py`, `app/ingest/mappers/apple.py`, `app/ingest/mappers/uber.py`, and `app/ingest/mappers/tiktok.py` to populate structured location fields from explicit source-native location structure.
- [x] T011 [US1] Update `app/ingest/mappers/eightfold.py`, `app/ingest/mappers/ashby.py`, `app/ingest/mappers/lever.py`, and `app/ingest/mappers/greenhouse.py` to use conservative text parsing and separate workplace-mode extraction from `employment_type`.
- [x] T012 [US1] Update `app/ingest/mappers/base.py` and any shared mapper plumbing needed so all mappers can emit the new location fields consistently via `JobCreate`.
- [x] T013 [US1] Update `app/services/application/job.py` and `app/api/v1/jobs.py` so direct job create/update paths accept and persist the structured location fields without dropping `location_text`.

**Checkpoint**: New ingests persist a single structured location profile on `job`, with `location_text` retained for compatibility.

---

## Phase 3: User Story 2 - Backfill Existing Jobs Safely (Priority: P2)

**Goal**: Populate structured location fields for historical jobs using safe, rerunnable logic that favors source-native structure over inferred parsing.

**Independent Test**: Run the backfill against mixed-confidence fixtures and verify idempotency plus protection against low-confidence overwrites.

### Tests for User Story 2

- [x] T014 [P] [US2] Add unit coverage in `tests/unit/test_backfill_job_locations.py` for confidence ordering, idempotent reruns, and ambiguous remote-scope cases.
- [x] T015 [P] [US2] Update `tests/unit/test_import_company_api_jobs.py`, `tests/unit/test_import_greenhouse_jobs.py`, `tests/unit/test_import_lever_jobs.py`, `tests/unit/test_import_ashby_jobs.py`, `tests/unit/test_import_smartrecruiters_jobs.py`, and `tests/unit/test_import_eightfold_jobs.py` if their job payload expectations need to include the new structured location fields.

### Implementation for User Story 2

- [x] T016 [US2] Create `scripts/backfill_job_locations.py` to backfill structured location fields from `raw_payload` first and `location_text` second, with explicit confidence guards.
- [x] T017 [US2] Extend `app/repositories/job.py` with batch selection and persistence helpers needed by the location backfill script.
- [x] T018 [US2] Reuse `app/services/domain/job_location.py` from the backfill path so ingest and historical repair apply the same extraction rules.

**Checkpoint**: Historical jobs can be upgraded safely without requiring a same-day full reimport.

---

## Phase 4: User Story 3 - Defer Full Multi-Location Normalization (Priority: P3)

**Goal**: Make structured location data consumable by read/query surfaces while clearly deferring canonical location tables and many-to-many modeling.

**Independent Test**: Verify that read APIs and matching-oriented query payloads can surface the new fields without reparsing `location_text` and without introducing `locations + job_locations`.

### Tests for User Story 3

- [x] T019 [P] [US3] Update `tests/unit/test_match_query.py`, `tests/unit/test_match_schema.py`, and `tests/unit/test_match_service.py` to cover structured location fields in match-oriented rows and response serialization.
- [x] T020 [P] [US3] Update `tests/unit/test_llm_match_recommendation.py` and `tests/unit/test_match_experiment_script.py` to keep downstream payload building compatible once structured location fields are available.
- [x] T021 [P] [US3] Update `tests/integration/test_matching_api.py` and add job-read coverage if needed so API payloads continue exposing `location_text` while optionally surfacing structured location fields.

### Implementation for User Story 3

- [x] T022 [US3] Update `app/schemas/match.py`, `app/services/infra/match_query.py`, `app/services/application/match_service.py`, and `app/services/infra/llm_match_recommendation.py` so structured location fields are available to future retrieval/ranking code without reparsing `location_text`.
- [x] T023 [US3] Update `docs/architecture/README.md`, `README.md`, and `docs/ROADMAP.md` references as needed to reflect that v1 stops at job-level structured fields and explicitly defers `locations + job_locations`.
- [x] T024 [US3] Add an implementation note in `specs/002-location-modeling-v1/plan.md` or adjacent docs clarifying the deterministic primary-location rule and the explicit deferral of canonical location reuse.

**Checkpoint**: Structured job location data is queryable and documented, but v1 still avoids canonical location tables.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validate the end-to-end rollout and capture follow-up cleanup work.

- [ ] T025 [P] Run targeted test suites for changed paths with `./scripts/uv run pytest tests/test_mappers.py tests/test_mappers_lever.py tests/test_mappers_ashby.py tests/test_mappers_smartrecruiters.py tests/test_mappers_company_apis.py tests/test_mappers_eightfold.py tests/unit/test_job_location.py tests/unit/test_job_service.py tests/unit/test_backfill_job_locations.py tests/unit/test_match_query.py tests/unit/test_match_schema.py tests/unit/test_match_service.py tests/unit/test_llm_match_recommendation.py tests/unit/test_match_experiment_script.py tests/integration/test_matching_api.py`.
- [ ] T026 Do a manual backfill dry run with `scripts/backfill_job_locations.py` against a small dataset and record any source-specific parsing gaps that should remain as follow-up work rather than block v1.
- [ ] T027 Capture future work in `docs/ROADMAP.md` or follow-up specs for canonical location reuse, multi-location jobs, and any location indexing that only becomes justified once retrieval filters are actually implemented.

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 blocks all user story work because the new columns and shared location helper define the feature shape.
- User Story 1 depends on Phase 1 and delivers the MVP ingest behavior.
- User Story 2 depends on Phase 1 and should reuse the same extraction helper introduced for User Story 1.
- User Story 3 depends on Phase 1 and should land after or alongside User Story 1 once the read-model shape is stable.
- Polish depends on the phases you intend to ship in this increment.

### User Story Dependencies

- **US1 (P1)**: Required MVP slice. No dependency on other user stories.
- **US2 (P2)**: Depends on the schema/helper work from Phase 1 and benefits from the same mapper rules established in US1.
- **US3 (P3)**: Depends on the final field set from Phase 1 and should follow once ingest behavior is stable.

### Parallel Opportunities

- T002, T003, T004, and T005 can run in parallel after the field names are finalized.
- T006, T007, T008, and T009 can run in parallel as test coverage for US1.
- T014 and T015 can run in parallel for backfill-related validation.
- T019, T020, and T021 can run in parallel for retrieval/read compatibility coverage.

## Implementation Strategy

### MVP First

1. Finish Phase 1.
2. Finish User Story 1.
3. Run the mapper and job-service tests to prove the new fields persist correctly without breaking `location_text`.

### Incremental Delivery

1. Ship additive schema support and shared extraction logic.
2. Ship source mapper rollout for new ingests.
3. Ship historical backfill tooling.
4. Ship retrieval-readiness and documentation updates.

## Notes

- Do not collapse workplace mode back into `employment_type`.
- Prefer source-native structured extraction over generalized text parsing.
- Treat uncertain geography as null rather than manufacturing canonical values.
- Keep `locations + job_locations` out of this feature even if some sources expose multiple locations.
