# Tasks: ATS Ingest (US1-US4)

**Input**: Design documents from `/specs/001-ats-ingest/`  
**Prerequisites**: `plan.md` (required), `spec.md` (required)

**Tests**: Tests are required for this feature because the specification includes independent test criteria per story and measurable outcomes tied to automated coverage.  
**Organization**: Tasks are grouped by user story so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story?] Description with file path`

- **[P]**: Parallelizable (different files, no dependency on incomplete tasks)
- **[Story]**: User story label (`[US1]`, `[US2]`, `[US3]`, `[US4]`)

## Scope Note

Although the current iteration may ship MVP after US1, this task plan covers US1-US4 to match the full feature contract in `spec.md` + `plan.md`.

---

## Phase 1: Setup (Project Initialization)

**Purpose**: Establish shared execution scaffolding and reporting paths for US1-US4 delivery.

- [x] T001 Create ATS ingest execution report scaffold in `reports/001-ats-ingest/README.md`
- [x] T002 [P] Add reusable ATS ingest regression runner script in `scripts/qa/run_ats_ingest_regression.sh`
- [x] T003 [P] Add shared ingest unit fixture entrypoint in `tests/unit/ingest/conftest.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define cross-story contracts and helpers that block implementation work for all user stories.

**⚠️ CRITICAL**: No user story work starts until this phase is complete.

- [x] T004 Define 8-platform fetcher registry helper contract in `tests/unit/ingest/fetchers/helpers.py`
- [x] T005 [P] Define transient retry status contract (`429/500/502/503/504`) in `tests/unit/ingest/fetchers/test_retry_contract.py`
- [x] T006 [P] Define no-raw-http enforcement contract for concrete fetchers in `tests/unit/ingest/fetchers/test_no_raw_http_calls.py`
- [x] T007 [P] Define mapper output contract fixture (`external_job_id/title/apply_url/source_id/location_hints`) in `tests/unit/ingest/mappers/conftest.py`
- [x] T008 Define foundational validation report baseline in `reports/001-ats-ingest/foundational-validation.txt`

**Checkpoint**: Shared contracts and fixtures are ready; story-level TDD can begin.

---

## Phase 3: User Story 1 - Multi-Source Job Fetching with Retry Resilience (Priority: P1) 🎯 MVP

**Goal**: Ensure all supported ATS fetchers use retry wrappers, fail gracefully after retry exhaustion, and enforce bounded detail concurrency.

**Independent Test**: Run fetcher/sync suites and verify transient retries across 8 platforms, graceful source failure reporting, and detail concurrency cap behavior.

### Tests for User Story 1 (write first)

- [x] T009 [P] [US1] Add wrapper-enforcement and retry-matrix tests for Greenhouse/Lever/Ashby in `tests/unit/ingest/fetchers/test_platform_retry_matrix.py`
- [x] T010 [P] [US1] Add wrapper-enforcement and retry-matrix tests for Apple/Uber/TikTok/Eightfold/SmartRecruiters in `tests/unit/ingest/fetchers/test_platform_retry_matrix.py`
- [x] T011 [P] [US1] Add detail concurrency cap tests for summary+detail fetchers in `tests/unit/ingest/fetchers/test_detail_concurrency_limit.py`
- [x] T012 [P] [US1] Add retry-exhaustion and continuation tests for source syncs in `tests/unit/sync/test_failure_reporting_and_continuation.py`

### Implementation for User Story 1

- [x] T013 [US1] Route Greenhouse requests through BaseFetcher retry wrappers in `app/ingest/fetchers/greenhouse.py`
- [x] T014 [US1] Route Lever requests through BaseFetcher retry wrappers in `app/ingest/fetchers/lever.py`
- [x] T015 [US1] Route Ashby requests through BaseFetcher retry wrappers in `app/ingest/fetchers/ashby.py`
- [x] T016 [US1] Align SmartRecruiters summary/detail retry and default detail concurrency in `app/ingest/fetchers/smartrecruiters.py`
- [x] T017 [US1] Align source-level retry exhaustion failure semantics in `app/services/application/sync/service.py`
- [x] T018 [US1] Align scheduled ingest continuation behavior for mixed source outcomes in `scripts/run_scheduled_ingests.py`
- [x] T019 [US1] Record US1 regression evidence in `reports/001-ats-ingest/us1-regression-summary.txt`

**Checkpoint**: US1 is independently functional and releasable as MVP.

---

## Phase 4: User Story 2 - Normalized Job Mapping with Structured Locations (Priority: P2)

**Goal**: Ensure all mapper outputs are canonical and include structured location hints plus normalized description fields.

**Independent Test**: Run mapper suites across all supported ATS payload variants and verify canonical `JobCreate` output shape.

### Tests for User Story 2 (write first)

- [x] T020 [P] [US2] Add canonical output and location-hints tests for Greenhouse/Lever/Ashby mappers in `tests/unit/ingest/mappers/test_greenhouse.py`
- [x] T021 [P] [US2] Add canonical output and location-hints tests for SmartRecruiters/Eightfold mappers in `tests/unit/ingest/mappers/test_smartrecruiters.py`
- [x] T022 [P] [US2] Add canonical output and location-hints tests for Apple/Uber/TikTok mappers in `tests/unit/ingest/mappers/test_company_apis.py`

### Implementation for User Story 2

- [x] T023 [US2] Implement canonical field mapping and structured location hints for Greenhouse in `app/ingest/mappers/greenhouse.py`
- [x] T024 [P] [US2] Implement canonical field mapping and structured location hints for Lever in `app/ingest/mappers/lever.py`
- [x] T025 [P] [US2] Implement canonical field mapping and structured location hints for Ashby in `app/ingest/mappers/ashby.py`
- [x] T026 [P] [US2] Implement canonical field mapping and structured location hints for SmartRecruiters/Eightfold/company APIs in `app/ingest/mappers/smartrecruiters.py`
- [x] T027 [US2] Enforce source stamping (`source_id` + compatibility `source`) during mapping pipeline in `app/services/application/full_snapshot_sync/mapping.py`
- [x] T028 [US2] Record US2 mapper validation evidence in `reports/001-ats-ingest/us2-mapper-summary.txt`

**Checkpoint**: US2 is independently functional with mapper-level acceptance coverage.

---

## Phase 5: User Story 3 - Full Snapshot Reconciliation (Priority: P3)

**Goal**: Ensure snapshot sync correctly inserts, updates, closes, and deduplicates jobs per source.

**Independent Test**: Run snapshot sync tests with evolving source snapshots and verify insert/update/close and dedupe behavior.

### Tests for User Story 3 (write first)

- [x] T029 [US3] Add insert/update/close/reopen snapshot behavior tests in `tests/unit/sync/test_full_snapshot_sync.py`
- [x] T030 [P] [US3] Add dedupe-by-external-id repository regression tests in `tests/unit/repositories/test_job_repository_dedup.py`
- [x] T031 [P] [US3] Add sync-service failure/rollback reconciliation tests in `tests/unit/sync/test_sync_service.py`

### Implementation for User Story 3

- [x] T032 [US3] Implement dedupe and payload normalization for snapshot mapping in `app/services/application/full_snapshot_sync/mapping.py`
- [x] T033 [US3] Implement staged upsert behavior for new/existing jobs in `app/services/application/full_snapshot_sync/staging.py`
- [x] T034 [US3] Implement close-missing reconcile finalization in `app/services/application/full_snapshot_sync/finalize.py`
- [x] T035 [US3] Wire end-to-end snapshot reconcile orchestration in `app/services/application/full_snapshot_sync/service.py`
- [x] T036 [US3] Record US3 reconciliation validation evidence in `reports/001-ats-ingest/us3-reconciliation-summary.txt`

**Checkpoint**: US3 is independently functional with lifecycle-correct reconciliation.

---

## Phase 6: User Story 4 - Blob Storage Offloading (Priority: P4)

**Goal**: Ensure large fields are offloaded to blob storage with bounded concurrency and safe rollback behavior.

**Independent Test**: Run blob-specific tests and full snapshot blob-path tests to verify pointer persistence, bounded uploads, and rollback safety.

### Tests for User Story 4 (write first)

- [x] T037 [P] [US4] Add blob builder hash/gzip contract coverage in `tests/unit/services/application/blob/test_blob_storage.py`
- [x] T038 [P] [US4] Add blob staging concurrency and rollback tests in `tests/unit/sync/test_full_snapshot_sync.py`
- [x] T039 [P] [US4] Add blob migration command regression tests in `tests/unit/scripts/test_migrate_job_blobs_to_storage.py`

### Implementation for User Story 4

- [x] T040 [US4] Implement deterministic blob builder payload generation in `app/services/infra/blob_storage/builder.py`
- [x] T041 [US4] Implement blob pointer sync/load semantics for job payloads in `app/services/application/blob/job_blob.py`
- [x] T042 [US4] Integrate bounded blob sync concurrency into snapshot staging in `app/services/application/full_snapshot_sync/staging.py`
- [x] T043 [US4] Implement resilient Supabase blob info/upload retry handling in `app/services/infra/blob_storage/supabase.py`
- [x] T044 [US4] Record US4 blob offload validation evidence in `reports/001-ats-ingest/us4-blob-summary.txt`

**Checkpoint**: US4 is independently functional with storage offload guarantees.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final cross-story quality improvements and release validation.

- [x] T045 [P] Consolidate US1-US4 contributor guidance in `app/ingest/fetchers/README.md`
- [x] T046 [P] Update ingest architecture reference notes in `docs/data-model/location.md`
- [x] T047 Run full ATS ingest regression suite and write final summary in `reports/001-ats-ingest/final-regression-summary.txt`
- [x] T048 Run quickstart-equivalent validation commands and capture output in `reports/001-ats-ingest/quickstart-validation.txt`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies.
- **Phase 2 (Foundational)**: Depends on Phase 1 and blocks all user stories.
- **Phase 3-6 (User Stories)**: Depend on Phase 2 completion.
- **Phase 7 (Polish)**: Depends on completion of all targeted user stories.

### User Story Dependencies

- **US1 (P1)**: Starts after Foundational; no dependency on other stories.
- **US2 (P2)**: Starts after Foundational; depends only on shared mapper contracts.
- **US3 (P3)**: Starts after Foundational; depends on mapping pipeline readiness.
- **US4 (P4)**: Starts after Foundational; depends on snapshot staging integration points.

### Within Each User Story

- Test tasks first and failing before implementation tasks.
- Data/contract logic before orchestration/reporting tasks.
- Story-level regression evidence task completes the story checkpoint.

### Parallel Opportunities

- Setup tasks `T002-T003` can run in parallel.
- Foundational tasks `T005-T007` can run in parallel.
- US1 test tasks `T009-T012` can run in parallel.
- US2 test tasks `T020-T022` and mapper implementation tasks `T024-T026` can run in parallel.
- US3 test tasks `T030-T031` can run in parallel.
- US4 test tasks `T037-T039` can run in parallel.
- Polish tasks `T045-T046` can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Run US1 test authoring in parallel
Task: "T009 in tests/unit/ingest/fetchers/test_platform_retry_matrix.py"
Task: "T010 in tests/unit/ingest/fetchers/test_platform_retry_matrix.py"
Task: "T011 in tests/unit/ingest/fetchers/test_detail_concurrency_limit.py"
Task: "T012 in tests/unit/sync/test_failure_reporting_and_continuation.py"

# Implement fetcher-specific changes in parallel by file
Task: "T013 in app/ingest/fetchers/greenhouse.py"
Task: "T014 in app/ingest/fetchers/lever.py"
Task: "T015 in app/ingest/fetchers/ashby.py"
Task: "T016 in app/ingest/fetchers/smartrecruiters.py"
```

## Parallel Example: User Story 2

```bash
# Mapper test coverage in parallel
Task: "T020 in tests/unit/ingest/mappers/test_greenhouse.py"
Task: "T021 in tests/unit/ingest/mappers/test_smartrecruiters.py"
Task: "T022 in tests/unit/ingest/mappers/test_company_apis.py"

# Mapper implementation in parallel by file
Task: "T024 in app/ingest/mappers/lever.py"
Task: "T025 in app/ingest/mappers/ashby.py"
Task: "T026 in app/ingest/mappers/smartrecruiters.py"
```

## Parallel Example: User Story 3

```bash
# Reconciliation tests in parallel
Task: "T030 in tests/unit/repositories/test_job_repository_dedup.py"
Task: "T031 in tests/unit/sync/test_sync_service.py"

# Reconciliation implementation sequence
Task: "T032 in app/services/application/full_snapshot_sync/mapping.py"
Task: "T033 in app/services/application/full_snapshot_sync/staging.py"
Task: "T034 in app/services/application/full_snapshot_sync/finalize.py"
Task: "T035 in app/services/application/full_snapshot_sync/service.py"
```

## Parallel Example: User Story 4

```bash
# Blob coverage in parallel
Task: "T037 in tests/unit/services/application/blob/test_blob_storage.py"
Task: "T038 in tests/unit/sync/test_full_snapshot_sync.py"
Task: "T039 in tests/unit/scripts/test_migrate_job_blobs_to_storage.py"

# Blob implementation sequence
Task: "T040 in app/services/infra/blob_storage/builder.py"
Task: "T041 in app/services/application/blob/job_blob.py"
Task: "T042 in app/services/application/full_snapshot_sync/staging.py"
Task: "T043 in app/services/infra/blob_storage/supabase.py"
```

---

## Implementation Strategy

### MVP First (US1)

1. Complete Phase 1 (Setup).
2. Complete Phase 2 (Foundational).
3. Deliver Phase 3 (US1).
4. Validate US1 independently before expanding scope.

### Incremental Delivery

1. US1: Fetch reliability + retry resilience.
2. US2: Mapper normalization + structured locations.
3. US3: Reconciliation lifecycle correctness.
4. US4: Blob offload correctness and resilience.
5. Polish: final cross-cutting validation and docs.

### Team Parallel Strategy

1. Team completes Setup + Foundational together.
2. Parallelize by story owner after Phase 2, with file-level conflict avoidance.
3. Merge each story at checkpoint completion with report artifacts.
