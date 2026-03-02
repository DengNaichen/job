# Tasks: Embedding Storage Redesign

**Input**: Design documents from `/specs/005-embedding-storage-redesign/`
**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Tests are required for this feature because the spec depends on active-target isolation, rerunnable historical migration, and a clean query cutover away from `job.embedding`.

**Organization**: Tasks are grouped by user story so each slice can be validated independently once the shared schema and target-selection primitives exist.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel
- **[Story]**: Maps to the user story in `spec.md`
- Every task lists concrete file paths that should be changed or created

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Establish the new persisted embedding store and one shared active-target policy before changing write paths, historical rollout, or matching recall.

- [x] T001 Create `app/models/job_embedding.py`, export it from `app/models/__init__.py`, and document the new table in `app/models/README.md`.
- [x] T002 Add a new Alembic migration under `alembic/versions/` to create the `job_embedding` table, vector indexes/constraints for active-target uniqueness, and a rollout-safe coexistence with legacy `job.embedding*` columns.
- [x] T003 Create `app/repositories/job_embedding.py`, update `app/repositories/__init__.py`, and extend `app/services/infra/embedding.py` with one stable active embedding target descriptor derived from the current embedding model/dimension configuration.

**Checkpoint**: The repo has a dedicated persisted job-embedding entity, migration support, and one shared target-selection rule that can be reused by write, migration, and query code.

---

## Phase 2: User Story 1 - Persist Job Embeddings Outside `job` For New Writes (Priority: P1) 🎯 MVP

**Goal**: Ensure new embedding writes persist to `job_embedding` for the active target instead of treating `job.embedding` as the primary storage location.

**Independent Test**: Run the embedding generation flow for representative jobs and verify that fresh active-target rows are written to `job_embedding`, duplicate reruns stay stable, and unchanged jobs do not need a second provider call.

### Tests for User Story 1

- [x] T004 [P] [US1] Expand `tests/unit/test_embedding_service.py` and add `tests/unit/test_job_embedding_repository.py` to cover active-target descriptor resolution, normalized model identity, and active-target upsert/refresh behavior keyed by `content_fingerprint`.
- [x] T005 [P] [US1] Add `tests/unit/test_backfill_job_embeddings_gemini.py` to cover writing fresh active-target rows to `job_embedding` without requiring `job.embedding` as the primary persistence path.

### Implementation for User Story 1

- [x] T006 [US1] Extend `app/repositories/job.py` and `app/repositories/job_embedding.py` with the write-side helpers needed to select embeddable jobs, detect already-fresh active-target rows, and upsert the new persisted records.
- [x] T007 [US1] Refactor `scripts/backfill_job_embeddings_gemini.py` so the normal embedding write path creates or refreshes `job_embedding` rows for the active target using `content_fingerprint`-aware skip/refresh logic.

**Checkpoint**: New embedding writes land in `job_embedding`, and reruns for unchanged content stay deterministic without relying on `job.embedding` as the main store.

---

## Phase 3: User Story 2 - Backfill And Migrate Historical Job Embeddings Safely (Priority: P2)

**Goal**: Migrate usable legacy in-row vectors and generate missing/stale active-target vectors so historical jobs become compatible with the new store.

**Independent Test**: Run the migration/backfill flow against mixed fixtures containing legacy in-row vectors, missing vectors, stale content fingerprints, and missing descriptions, then verify that compatible legacy rows migrate, missing rows regenerate, and reruns stay non-duplicative.

### Tests for User Story 2

- [x] T008 [P] [US2] Expand `tests/unit/test_backfill_job_embeddings_gemini.py` to cover migrating compatible legacy `job.embedding*` state, regenerating missing active-target rows, stale-content refresh behavior, dry-run reporting, and rerunnable execution.

### Implementation for User Story 2

- [x] T009 [US2] Extend `scripts/backfill_job_embeddings_gemini.py` to migrate usable legacy in-row vectors into `job_embedding` before calling the provider for missing or stale active-target rows.
- [x] T010 [US2] Extend `app/repositories/job.py` and `app/repositories/job_embedding.py` with batch/keyset helpers for legacy migration candidates, missing active-target rows, stale `content_fingerprint` rows, and bounded rollout reporting.

**Checkpoint**: Historical jobs can be migrated or regenerated into `job_embedding` safely, and reruns do not create duplicate active-target state.

---

## Phase 4: User Story 3 - Query Matching Through The New Embedding Store (Priority: P3)

**Goal**: Make vector recall consume `job_embedding` as the dedicated operational source of truth while preserving the rest of the matching pipeline.

**Independent Test**: Run matching query and API tests after cutover and verify that candidate recall joins through `job_embedding`, enforces one active target, and excludes jobs missing that target without breaking downstream ranking or serialization.

### Tests for User Story 3

- [x] T011 [P] [US3] Update `tests/unit/test_match_query.py` and `tests/unit/test_match_service.py` so vector recall expects explicit active-target filtering through `job_embedding` rather than direct dependence on `job.embedding`.
- [x] T012 [P] [US3] Update `tests/unit/test_match_experiment_script.py`, `tests/unit/test_match_schema.py`, and `tests/integration/test_matching_api.py` so matching-facing behavior remains compatible after the query cutover.

### Implementation for User Story 3

- [x] T013 [US3] Refactor `app/services/infra/match_query.py` to join against `job_embedding`, filter by the active target descriptor, and remove direct recall SQL dependence on `job.embedding`.
- [x] T014 [US3] Update `app/services/application/match_service.py` and `scripts/match_experiment.py` so request-time embedding generation stays aligned with the active stored target used by recall.
- [x] T015 [US3] Update `docs/architecture/README.md`, `docs/ROADMAP.md`, and `README.md` to document the dedicated `job_embedding` path, the recall cutover, and the bounded deprecation of legacy in-row embedding columns.

**Checkpoint**: Matching recall works through `job_embedding`, and the storage redesign is documented as independent from unfinished location work.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validate the redesign end to end and record the remaining cleanup boundary without broadening feature scope.

- [ ] T016 [P] Run targeted test suites with `./scripts/uv run pytest tests/unit/test_embedding_service.py tests/unit/test_job_embedding_repository.py tests/unit/test_backfill_job_embeddings_gemini.py tests/unit/test_match_query.py tests/unit/test_match_service.py tests/unit/test_match_experiment_script.py tests/unit/test_match_schema.py tests/integration/test_matching_api.py`.
- [ ] T017 Do a manual dry run of `scripts/backfill_job_embeddings_gemini.py` against a small dataset and record counts for migrated legacy vectors, regenerated active-target vectors, already-fresh skips, and missing-content failures.
- [ ] T018 Capture explicit follow-up cleanup for physically removing legacy `job.embedding*` columns in `docs/ROADMAP.md` or a follow-up spec if rollout safety requires a later drop migration.

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 blocks all user story work because write paths, historical migration, and matching recall all depend on the new persisted entity and one shared active-target rule.
- User Story 1 depends on Phase 1 and delivers the MVP storage cutover for new embedding writes.
- User Story 2 depends on Phase 1 and should reuse the same target-selection and persistence rules already exercised by User Story 1.
- User Story 3 depends on the persisted store from User Story 1 and is safest once User Story 2 has stabilized mixed historical data coverage.
- Polish depends on the phases you intend to ship in this increment.

### User Story Dependencies

- **US1 (P1)**: Required MVP slice. No dependency on other user stories once Phase 1 is complete.
- **US2 (P2)**: Depends on the shared schema and target-selection primitives from Phase 1 and should follow the same persistence rules established in US1.
- **US3 (P3)**: Depends on the persisted-store behavior stabilized by US1 and benefits from US2 so query coverage is more consistent across historical rows.

### Parallel Opportunities

- T004 and T005 can run in parallel as US1 coverage work.
- T008 can run in parallel with migration helper scaffolding once the Phase 1 primitives are in place.
- T011 and T012 can run in parallel for query cutover coverage.

## Implementation Strategy

### MVP First

1. Finish Phase 1.
2. Finish User Story 1.
3. Run the repository and script tests to prove new embedding writes persist to `job_embedding` without treating `job.embedding` as the primary store.

### Incremental Delivery

1. Ship the dedicated persisted embedding store plus shared target-selection primitives.
2. Ship the new write path for active-target embeddings.
3. Ship historical migration/backfill support for legacy in-row vectors and stale rows.
4. Ship matching query cutover and documentation updates.

## Notes

- The redesign should stay independent from country canonicalization and canonical location modeling.
- `job.embedding`, `job.embedding_model`, and `job.embedding_updated_at` may remain during rollout, but they should stop being the operational source of truth inside this feature.
- Active recall must not compare vectors across mismatched models or dimensions.
- Candidate/user embeddings remain request-scoped and should not be persisted by this feature.
- Retrieval-policy redesign beyond the storage cutover belongs to the separate roadmap items for hybrid retrieval and production-ready matching.
