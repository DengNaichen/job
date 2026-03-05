# Tasks: Embedding Pipeline

**Input**: Design documents from `/Users/nd/Developer/job/specs/003-embedding-pipeline/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Testing policy**: Tests are required for this feature because `spec.md` mandates automated coverage in FR-008 and success criteria SC-001..SC-004.

## Phase 1: Setup (Project Initialization)

- [X] T001 Add embedding refresh runtime flags (`embedding_refresh_enabled`, `embedding_refresh_batch_size`) in /Users/nd/Developer/job/app/core/config.py
- [X] T002 [P] Create embedding refresh application package exports in /Users/nd/Developer/job/app/services/application/embedding_refresh/__init__.py
- [X] T003 [P] Create embedding refresh service module scaffold in /Users/nd/Developer/job/app/services/application/embedding_refresh/service.py
- [X] T004 [P] Add shared sync-test fixtures for embedding refresh injection in /Users/nd/Developer/job/tests/unit/sync/conftest.py

## Phase 2: Foundational (Blocking Prerequisites)

- [X] T005 Add snapshot-refresh candidate projection type for repository reads in /Users/nd/Developer/job/app/repositories/job.py
- [X] T006 Add source-scoped refresh candidate query method for open jobs in /Users/nd/Developer/job/app/repositories/job.py
- [X] T007 Add embedding refresh execution result dataclass and interfaces in /Users/nd/Developer/job/app/services/application/embedding_refresh/service.py
- [X] T008 Wire `EmbeddingRefreshService` dependency into sync orchestration constructor in /Users/nd/Developer/job/app/services/application/sync/service.py
- [X] T009 Add foundational sync-service hook tests for dependency wiring in /Users/nd/Developer/job/tests/unit/sync/test_sync_service.py

## Phase 3: User Story 1 - Reliable Embedding Generation (Priority: P1)

**Goal**: Keep embedding generation resilient under transient provider failures and deterministic under non-transient failures.

**Independent Test**: Run embedding client/parsing unit suites and verify retry/fail-fast/fallback behavior remains deterministic.

- [X] T010 [P] [US1] Extend transient vs non-transient retry matrix tests in /Users/nd/Developer/job/tests/unit/services/infra/test_embedding_client.py
- [X] T011 [P] [US1] Add dimensions-fallback edge-case tests (retry exhaustion and one-shot fallback) in /Users/nd/Developer/job/tests/unit/services/infra/test_embedding_client.py
- [X] T012 [P] [US1] Add malformed payload coercion and numeric validation tests in /Users/nd/Developer/job/tests/unit/services/infra/test_embedding_parsing.py
- [X] T013 [US1] Refactor client-level monkeypatch points to target client module symbols in /Users/nd/Developer/job/tests/unit/services/infra/test_embedding_client.py
- [X] T014 [US1] Harden retry/fallback branching for edge cases in /Users/nd/Developer/job/app/services/infra/embedding/client.py
- [X] T015 [US1] Harden parsing diagnostics for invalid provider payloads in /Users/nd/Developer/job/app/services/infra/embedding/parsing.py
- [X] T016 [US1] Align US1 verification steps in /Users/nd/Developer/job/specs/003-embedding-pipeline/quickstart.md

**Checkpoint**: US1 can be validated independently via embedding service/parsing tests.

## Phase 4: User Story 2 - Stable Embedding Target Identity (Priority: P1)

**Goal**: Ensure active-target identity isolation across writes and reads so incompatible embeddings are never mixed.

**Independent Test**: Persist mixed-target rows and verify only active-target-consistent rows are selected by repository/gateway reads.

- [X] T017 [P] [US2] Add mixed-target isolation tests for repository read helpers in /Users/nd/Developer/job/tests/unit/repositories/test_job_embedding_repository.py
- [X] T018 [P] [US2] Add provider/model normalization edge-case tests in /Users/nd/Developer/job/tests/unit/services/infra/test_embedding_config.py
- [X] T019 [P] [US2] Add active-target SQL filter assertions for embedding reads in /Users/nd/Developer/job/tests/unit/services/infra/matching/test_query.py
- [X] T020 [US2] Enforce target-consistent row selection helpers in /Users/nd/Developer/job/app/repositories/job_embedding.py
- [X] T021 [US2] Harden model identity normalization paths in /Users/nd/Developer/job/app/services/infra/embedding/config.py
- [X] T022 [US2] Refactor MatchExperimentService tests to use constructor injection over global monkeypatching in /Users/nd/Developer/job/tests/unit/services/application/test_match_service.py

**Checkpoint**: US2 can be validated independently via repository/config/query target-isolation tests.

## Phase 5: User Story 3 - Snapshot-Aligned Embedding Refresh (Priority: P2)

**Goal**: Run embedding refresh only after successful snapshot sync outcomes with idempotent upserts and closed-job exclusion.

**Independent Test**: Run consecutive successful snapshots and verify refresh trigger behavior, closed-job exclusion, and no duplicate active-target rows.

- [X] T023 [P] [US3] Add unit tests for snapshot-triggered refresh behavior in /Users/nd/Developer/job/tests/unit/services/application/test_embedding_refresh_service.py
- [X] T024 [P] [US3] Add success-only refresh trigger tests in /Users/nd/Developer/job/tests/unit/sync/test_sync_service.py
- [X] T025 [P] [US3] Add idempotent rerun and closed-job refresh exclusion tests in /Users/nd/Developer/job/tests/unit/sync/test_full_snapshot_sync.py
- [X] T026 [US3] Implement snapshot-aligned refresh orchestration flow in /Users/nd/Developer/job/app/services/application/embedding_refresh/service.py
- [X] T027 [US3] Implement source-scoped refresh selection with closed-job exclusion in /Users/nd/Developer/job/app/repositories/job.py
- [X] T028 [US3] Implement active-target batch upsert execution for refresh jobs in /Users/nd/Developer/job/app/repositories/job_embedding.py
- [X] T029 [US3] Invoke embedding refresh only on successful snapshot runs in /Users/nd/Developer/job/app/services/application/sync/service.py
- [X] T030 [US3] Add contract-level snapshot refresh behavior tests in /Users/nd/Developer/job/tests/unit/sync/test_snapshot_embedding_refresh_contract.py

**Checkpoint**: US3 can be validated independently via snapshot-success refresh flow tests and idempotency checks.

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T031 [P] Update snapshot-only embedding semantics in /Users/nd/Developer/job/README.md
- [X] T032 [P] Update embedding behavior note for snapshot-aligned flow in /Users/nd/Developer/job/docs/embedding-retry-fallback-rules.md
- [X] T033 [P] Record validation plan and executed test matrix in /Users/nd/Developer/job/reports/003-embedding-refresh-validation.md
- [X] T034 Run focused regression commands and append outcome summary in /Users/nd/Developer/job/reports/003-embedding-refresh-validation.md

---

## Dependencies & Execution Order

### Phase Dependencies

- Setup (Phase 1): no dependencies
- Foundational (Phase 2): depends on Setup completion
- User Stories (Phases 3-5): depend on Foundational completion
- Polish (Phase 6): depends on target user stories being complete

### User Story Dependencies

- US1 (P1): can start after Phase 2; independent delivery unit
- US2 (P1): can start after Phase 2; independent delivery unit
- US3 (P2): starts after Phase 2 and should run after US2 target-isolation hardening

### Completion Order Recommendation

1. Finish Phase 1 + Phase 2
2. Deliver US1 as MVP
3. Deliver US2
4. Deliver US3
5. Run Phase 6 polish and final validation

---

## Parallel Execution Examples

### US1 Parallel Example

```bash
# Parallelizable US1 tests
T010 + T012

# Then implement core behavior changes
T013 + T014
```

### US2 Parallel Example

```bash
# Parallelizable US2 tests
T017 + T018 + T019

# Then implement target isolation hardening
T020 + T021
```

### US3 Parallel Example

```bash
# Parallelizable US3 test-first tasks
T023 + T024 + T025

# Parallelizable implementation tasks on different files
T026 + T028
```

---

## Implementation Strategy

### MVP First (US1 only)

1. Complete Phase 1 and Phase 2
2. Complete Phase 3 (US1)
3. Validate US1 independently
4. Pause for review before expanding scope

### Incremental Delivery

1. US1 (reliability)
2. US2 (target identity isolation)
3. US3 (snapshot-aligned refresh orchestration)
4. Polish and regression reporting

### Parallel Team Strategy

1. One engineer handles US1 reliability refinements
2. One engineer handles US2 target isolation hardening
3. One engineer handles US3 orchestration after foundational tasks merge
