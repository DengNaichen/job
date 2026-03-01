# Tasks: Source ID Ownership Migration

**Input**: Design documents from `/specs/001-source-id-fks/`
**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Tests are required for this feature because the spec explicitly depends on preserving ingest behavior, source lifecycle safety, and API compatibility during migration.

**Organization**: Tasks are grouped by user story so each slice can be validated independently once the foundational migration work is in place.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel
- **[Story]**: Maps to the user story in `spec.md`
- Every task lists concrete file paths that should be changed or created

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Introduce schema support and shared repository/model primitives before changing behavior.

- [ ] T001 Create an Alembic revision in `alembic/versions/` that adds nullable `source_id` to `job` and `syncrun`, adds FK constraints to `sources.id`, and adds supporting `source_id` indexes.
- [ ] T002 [P] Update `app/models/job.py` and `app/models/sync_run.py` to add `source_id` and clarify that the legacy `source` string is compatibility state rather than the authoritative owner key.
- [ ] T003 [P] Update `app/schemas/job.py` and `app/schemas/sync_run.py` so read models can expose `source_id` while preserving the legacy `source` field.
- [ ] T004 [P] Extend `app/repositories/job.py` and `app/repositories/sync_run.py` with `source_id`-based lookup helpers and source-reference existence checks needed by later service changes.
- [ ] T005 Add rollout validation notes in `specs/001-source-id-fks/quickstart.md` covering pre-backfill audit queries, backfill verification, and post-cutover smoke checks.

**Checkpoint**: Database, models, schemas, and repository helpers are ready for behavior changes.

---

## Phase 2: User Story 1 - Preserve Same-Source Ownership Correctly (Priority: P1) 🎯 MVP

**Goal**: Make `source_id` the authoritative key for same-source ingest behavior without breaking current sync semantics.

**Independent Test**: Run targeted unit tests for full snapshot sync, sync-run repository, and sync service behavior to prove upsert, close-missing, and overlap detection use `source_id`.

### Tests for User Story 1

- [ ] T006 [P] [US1] Update `tests/unit/test_full_snapshot_sync.py` for `source_id`-based existing-job lookup, close-missing behavior, and legacy-key dual-write expectations.
- [ ] T007 [P] [US1] Update `tests/unit/test_sync_service.py` and `tests/unit/test_sync_run_repository.py` for `source_id`-based overlap detection and sync-run persistence.
- [ ] T008 [P] [US1] Extend `tests/unit/test_job_repository_dedup.py` with coverage for same-source uniqueness and stale-job closure keyed by `source_id`.

### Implementation for User Story 1

- [ ] T009 [US1] Implement dual-write and `source_id`-based same-source reconcile in `app/services/application/full_snapshot_sync.py`.
- [ ] T010 [US1] Update `app/repositories/job.py` so same-source list and close-missing methods use `source_id` as the authoritative filter.
- [ ] T011 [US1] Update `app/services/application/sync.py` and `app/repositories/sync_run.py` so running-run lookup and sync-run creation use `source_id` plus the legacy source string.
- [ ] T012 [US1] Add migration/backfill logic in the new Alembic revision under `alembic/versions/` so existing `job` and `syncrun` rows are populated from the legacy source key before constraints tighten.
- [ ] T013 [US1] Update source-aware script and import test fixtures in `tests/unit/test_import_company_api_jobs.py`, `tests/unit/test_import_greenhouse_jobs.py`, `tests/unit/test_import_lever_jobs.py`, `tests/unit/test_import_ashby_jobs.py`, `tests/unit/test_import_smartrecruiters_jobs.py`, `tests/unit/test_import_eightfold_jobs.py`, and `tests/unit/test_run_scheduled_ingests.py`.

**Checkpoint**: Same-source ingest behavior is authoritative on `source_id` and remains independently testable.

---

## Phase 3: User Story 2 - Protect Source Lifecycle Operations (Priority: P2)

**Goal**: Prevent deletes or source field mutations from orphaning historical jobs and sync runs during the migration window.

**Independent Test**: Attempt to delete or mutate a referenced source through service and API tests and verify the operation is rejected.

### Tests for User Story 2

- [ ] T014 [P] [US2] Update `tests/unit/test_source.py` to cover deletion blocking plus rejection of `platform` and `identifier` updates for referenced sources.
- [ ] T015 [P] [US2] Update `tests/integration/test_source_api.py` to cover API-level failures for deleting or mutating referenced sources.

### Implementation for User Story 2

- [ ] T016 [US2] Add source-reference existence helpers in `app/repositories/job.py` and `app/repositories/sync_run.py` for checking dependent jobs and sync runs by `source_id`.
- [ ] T017 [US2] Enforce referenced-source delete and mutation guards in `app/services/application/source.py`.
- [ ] T018 [US2] Surface the new mutation failure path cleanly in `app/api/v1/sources.py`, including an explicit error response for blocked `platform` or `identifier` changes.

**Checkpoint**: Source lifecycle operations are safe even while the legacy source key still exists.

---

## Phase 4: User Story 3 - Preserve Compatibility During Rollout (Priority: P3)

**Goal**: Keep current consumers working while exposing `source_id` to newer code paths.

**Independent Test**: Verify that read models expose `source_id` plus the legacy source key, and that direct job creation can resolve ownership without forcing an immediate client break.

### Tests for User Story 3

- [ ] T019 [P] [US3] Update `tests/unit/test_job_service.py` for `source_id` exposure and any source-resolution logic added to direct job creation.
- [ ] T020 [P] [US3] Add API compatibility coverage in `tests/integration/test_job_api.py` for job read/create payloads that include `source_id` while preserving the legacy source key.

### Implementation for User Story 3

- [ ] T021 [US3] Update `app/services/application/job.py`, `app/repositories/source.py`, and `app/api/v1/jobs.py` so direct job creation can resolve a source to `source_id` without dropping legacy `source` compatibility.
- [ ] T022 [US3] Finalize read-model compatibility in `app/schemas/job.py`, `app/schemas/sync_run.py`, and any supporting serialization code under `app/api/v1/`.
- [ ] T023 [US3] Update reference docs in `README.md`, `app/models/README.md`, and `docs/architecture/README.md` to describe `source_id` as the authoritative owner key and the legacy string as compatibility state.

**Checkpoint**: New and old consumers can coexist while the system internally relies on `source_id`.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validate the rollout and clean up migration scaffolding.

- [ ] T024 [P] Run targeted test suites for changed paths with `./scripts/uv run pytest tests/unit/test_full_snapshot_sync.py tests/unit/test_sync_service.py tests/unit/test_sync_run_repository.py tests/unit/test_source.py tests/unit/test_job_service.py tests/integration/test_source_api.py tests/integration/test_job_api.py`.
- [ ] T025 Verify manual migration steps in `specs/001-source-id-fks/quickstart.md`, including pre-backfill audits, post-backfill null checks, and source mutation smoke tests.
- [ ] T026 Capture follow-up cleanup items in `docs/ROADMAP.md` for the later physical rename from legacy `source` to `source_key` and eventual removal of migration fallback code.

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 blocks all user story work because the schema and repository primitives must exist first.
- User Story 1 depends on Phase 1 and establishes the authoritative `source_id` behavior.
- User Story 2 depends on Phase 1 and should land after or alongside User Story 1 because it uses the new reference checks.
- User Story 3 depends on Phase 1 and should follow once model/schema shape is stable.
- Polish depends on the stories you intend to ship in this increment.

### User Story Dependencies

- **US1 (P1)**: Required MVP slice. No dependency on other user stories.
- **US2 (P2)**: Depends on repository reference helpers and should be validated against migrated ownership.
- **US3 (P3)**: Depends on the final read/write model shape from US1.

### Parallel Opportunities

- T002, T003, and T004 can run in parallel after the migration shape is decided.
- T006, T007, and T008 can run in parallel as test updates for US1.
- T014 and T015 can run in parallel for source lifecycle coverage.
- T019 and T020 can run in parallel for compatibility coverage.

## Implementation Strategy

### MVP First

1. Finish Phase 1.
2. Finish User Story 1.
3. Run the US1 tests and validate that same-source sync behavior is unchanged except for the owner key.

### Incremental Delivery

1. Ship schema expansion and `source_id` backfill support.
2. Ship authoritative `source_id` sync behavior.
3. Ship source lifecycle guardrails.
4. Ship compatibility refinements and documentation cleanup.

## Notes

- Keep the physical rename from `source` to `source_key` out of this change set.
- Prefer additive migrations over destructive edits.
- Treat any unmatched legacy source key during backfill as a blocker, not a warning.
