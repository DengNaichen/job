# Tasks: ATS Ingest (US1 Only)

**Input**: Design documents from `/specs/001-ats-ingest/`
**Prerequisites**: `plan.md` (required), `spec.md` (required)

**Tests**: Tests are required for this feature because the plan mandates strict TDD.
**Organization**: Tasks are grouped by user story to keep implementation independently testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: User story label (`[US1]`, `[US2]`, ...)
- Every task includes an explicit file path

## Scope Note

This `tasks.md` follows the current implementation plan scope (`US1` only). User Stories `US2/US3/US4` in `spec.md` are intentionally deferred by plan and are not implemented in this iteration.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create US1-focused test structure and shared scaffolding before writing red tests.

- [x] T001 Create US1 fetcher test package skeleton in `tests/unit/ingest/fetchers/__init__.py`
- [x] T002 [P] Create US1 sync test package skeleton in `tests/unit/sync/__init__.py`
- [x] T003 [P] Add shared fetcher test fixtures in `tests/unit/ingest/fetchers/conftest.py`
- [x] T004 [P] Add shared sync test fixtures in `tests/unit/sync/conftest.py`
- [x] T005 Create reusable US1 test helpers (retry matrix, in-flight tracker, fetcher registry) in `tests/unit/ingest/fetchers/helpers.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define cross-test contracts that block all US1 implementation work.

**⚠️ CRITICAL**: No US1 implementation task starts until this phase is complete.

- [x] T006 Define HTTP-wrapper enforcement guard baseline in `tests/unit/ingest/fetchers/test_no_raw_http_calls.py`
- [x] T007 Define platform retry status contract (`429/500/502/503/504`) in `tests/unit/ingest/fetchers/test_retry_contract.py`
- [x] T008 Define concurrency-cap measurement utilities for summary+detail fetchers in `tests/unit/ingest/fetchers/test_detail_concurrency_limit.py`

**Checkpoint**: Foundation ready - US1 TDD cycle can start.

---

## Phase 3: User Story 1 - Multi-Source Job Fetching with Retry Resilience (Priority: P1) 🎯 MVP

**Goal**: Ensure all supported ATS fetchers use retry wrappers, fail gracefully after retry exhaustion, and enforce bounded detail concurrency (`default=6`).

**Independent Test**: Run US1 suites to verify transient retries across 8 platforms, graceful failure reporting, and in-flight detail concurrency never exceeding 6.

### Tests for User Story 1 (Write first, make them fail) ⚠️

- [x] T009 [P] [US1] Add failing wrapper-enforcement tests for fetchers in `tests/unit/ingest/fetchers/test_no_raw_http_calls.py`
- [x] T010 [P] [US1] Add failing retry-matrix tests for Greenhouse/Lever/Ashby/SmartRecruiters in `tests/unit/ingest/fetchers/test_platform_retry_matrix.py`
- [x] T011 [P] [US1] Add failing retry-matrix tests for Apple/Uber/TikTok/Eightfold in `tests/unit/ingest/fetchers/test_platform_retry_matrix.py`
- [x] T012 [P] [US1] Add failing retry-exhaustion failure-reporting tests in `tests/unit/sync/test_failure_reporting_and_continuation.py`
- [x] T013 [P] [US1] Add failing batch-continuation tests for mixed source outcomes in `tests/unit/sync/test_failure_reporting_and_continuation.py`
- [x] T014 [P] [US1] Add failing detail concurrency-cap tests (`<=6`) for Apple/Eightfold/SmartRecruiters in `tests/unit/ingest/fetchers/test_detail_concurrency_limit.py`
- [x] T015 [US1] Record red baseline execution output in `reports/001-ats-ingest/us1-red-baseline.txt`

### Implementation for User Story 1 (Make tests pass)

- [x] T016 [US1] Replace raw Greenhouse HTTP call with BaseFetcher retry wrapper in `app/ingest/fetchers/greenhouse.py`
- [x] T017 [US1] Replace raw Lever HTTP call with BaseFetcher retry wrapper in `app/ingest/fetchers/lever.py`
- [x] T018 [US1] Replace raw Ashby HTTP call with BaseFetcher retry wrapper in `app/ingest/fetchers/ashby.py`
- [x] T019 [US1] Replace SmartRecruiters summary raw HTTP call with BaseFetcher retry wrapper in `app/ingest/fetchers/smartrecruiters.py`
- [x] T020 [US1] Align SmartRecruiters detail retry statuses to include `429` in `app/ingest/fetchers/smartrecruiters.py`
- [x] T021 [US1] Align SmartRecruiters default detail concurrency to `6` in `app/ingest/fetchers/smartrecruiters.py`
- [x] T022 [US1] Update fetcher behavior tests to validate wrapper usage and retry semantics in `tests/unit/ingest/fetchers/test_greenhouse.py`
- [x] T023 [US1] Update fetcher behavior tests to validate wrapper usage and retry semantics in `tests/unit/ingest/fetchers/test_lever.py`
- [x] T024 [US1] Update fetcher behavior tests to validate wrapper usage and retry semantics in `tests/unit/ingest/fetchers/test_ashby.py`
- [x] T025 [US1] Update fetcher behavior tests to validate `429` retry and concurrency default in `tests/unit/ingest/fetchers/test_smartrecruiters.py`
- [x] T026 [US1] Verify sync failure reporting semantics under retry exhaustion in `tests/unit/test_sync_service.py`
- [x] T027 [US1] Verify scheduled ingest continuation semantics for mixed outcomes in `tests/unit/test_run_scheduled_ingests.py`
- [x] T028 [US1] Record green baseline execution output in `reports/001-ats-ingest/us1-green-baseline.txt`

**Checkpoint**: US1 is independently functional and testable.

---

## Deferred Stories (Out of This Iteration)

- **US2**: Normalized job mapping with structured locations (deferred by `plan.md` scope)
- **US3**: Full snapshot reconciliation (deferred by `plan.md` scope)
- **US4**: Blob storage offloading (deferred by `plan.md` scope)

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Cleanup and validation affecting US1 deliverable quality.

- [x] T029 [P] Consolidate migrated US1 test coverage notes in `tests/unit/ingest/fetchers/README.md`
- [x] T030 [P] Update contributor guidance for retry wrappers and detail concurrency defaults in `app/ingest/fetchers/README.md`
- [x] T031 Run impacted regression suite and write summary in `reports/001-ats-ingest/us1-regression-summary.txt`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies.
- **Phase 2 (Foundational)**: Depends on Phase 1; blocks all US1 work.
- **Phase 3 (US1)**: Depends on Phase 2 completion.
- **Phase 4 (Polish)**: Depends on US1 completion.

### User Story Dependencies

- **US1 (P1)**: Starts after Phase 2; no dependency on other stories in this iteration.
- **US2/US3/US4**: Deferred by plan scope.

### Within US1

- Tests must be authored and failing before implementation (`T009-T015` before `T016+`).
- Fetcher implementation changes precede legacy suite alignment.
- Story-level validation (`T028`) precedes polish phase.

### Parallel Opportunities

- `T002`, `T003`, `T004` can run in parallel.
- `T009`-`T014` can run in parallel (different files).
- `T016`-`T021` are partially parallelizable by fetcher file.
- `T022`-`T025` are parallelizable by test file.
- `T029` and `T030` can run in parallel.

---

## Parallel Example: User Story 1

```bash
# Red tests in parallel
Task: "T010 in tests/unit/ingest/fetchers/test_platform_retry_matrix.py"
Task: "T011 in tests/unit/ingest/fetchers/test_platform_retry_matrix.py"
Task: "T012 in tests/unit/sync/test_failure_reporting_and_continuation.py"
Task: "T014 in tests/unit/ingest/fetchers/test_detail_concurrency_limit.py"

# Fetcher implementation in parallel by file
Task: "T016 in app/ingest/fetchers/greenhouse.py"
Task: "T017 in app/ingest/fetchers/lever.py"
Task: "T018 in app/ingest/fetchers/ashby.py"
Task: "T019-T021 in app/ingest/fetchers/smartrecruiters.py"
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Complete Phase 1 (Setup).
2. Complete Phase 2 (Foundational).
3. Execute US1 Red tests (`T009-T015`).
4. Implement minimal Green changes (`T016-T027`).
5. Validate US1 independently (`T028`).

### Incremental Delivery

1. Deliver retry-wrapper compliance and transient retry behavior.
2. Deliver graceful failure and continuation guarantees.
3. Deliver detail concurrency cap alignment.
4. Perform polish and regression validation.

### Suggested Validation Commands

- `pytest tests/unit/ingest/fetchers/test_no_raw_http_calls.py tests/unit/ingest/fetchers/test_retry_contract.py tests/unit/ingest/fetchers/test_platform_retry_matrix.py tests/unit/ingest/fetchers/test_detail_concurrency_limit.py -q`
- `pytest tests/unit/sync/test_failure_reporting_and_continuation.py -q`
- `pytest tests/unit/test_sync_service.py -q`
- `pytest tests/unit/test_run_scheduled_ingests.py -q`
