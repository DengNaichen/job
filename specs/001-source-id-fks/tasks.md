# Tasks: Source ID Ownership Migration

**Input**: Design documents from `/specs/001-source-id-fks/`  
**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Tests are required because this feature changes authoritative ownership, source lifecycle safety, and public read-model compatibility.

**Organization**: Tasks are grouped by implementation phase so rollout and enforcement can be executed in the intended order.

## Format: `[ID] [P?] Description`

- **[P]**: Can run in parallel once phase prerequisites are met
- Every task lists concrete file paths that should be changed or created

## Phase 1: Preflight & Docs

**Purpose**: Make the migration operationally executable before code and schema changes start.

- [x] T001 Finalize `specs/001-source-id-fks/quickstart.md` with preflight audit queries for legacy-key integrity across `sources`, `job`, and `syncrun`.
- [x] T002 Finalize post-backfill validation queries in `specs/001-source-id-fks/quickstart.md` covering null `source_id` checks and duplicate `(source_id, external_job_id)` ownership checks.
- [x] T003 Finalize rollout order, smoke test steps, and rollback guidance in `specs/001-source-id-fks/quickstart.md`, including explicit stop conditions for unmatched legacy keys or duplicate ownership rows.

**Checkpoint**: Operators have a concrete rollout document and the migration has clear blocker conditions.

---

## Phase 2: Schema Expansion & Backfill

**Purpose**: Introduce nullable foreign-key ownership and backfill existing rows without enforcing `NOT NULL` yet.

- [x] T004 Create a first Alembic revision under `alembic/versions/` that adds nullable `source_id` to `job` and `syncrun`, adds foreign keys to `sources.id`, and adds supporting `source_id` indexes.
- [x] T005 Implement backfill logic in that first Alembic revision so existing `job` and `syncrun` rows populate `source_id` by matching the stored legacy `source` string to `build_source_key(source.platform, source.identifier)`.
- [x] T006 Add blocker checks to the expansion/backfill workflow so unmatched rows and duplicate `(source_id, external_job_id)` ownership prevent the rollout from continuing to enforcement.
- [x] T007 [P] Update `app/models/job.py` and `app/models/sync_run.py` to add nullable `source_id` while preserving the legacy `source` column as compatibility state.
- [x] T008 [P] Update `app/schemas/job.py` and `app/schemas/sync_run.py` so read models can expose `source_id` without removing the legacy `source` field.

**Checkpoint**: The database can represent authoritative ownership, and existing data can be backfilled safely into a nullable `source_id` state.

---

## Phase 3: Repository & Application Cutover

**Purpose**: Make runtime authoritative behavior use `source_id` while dual-writing compatibility state.

- [x] T009 [P] Extend `app/repositories/job.py` with `source_id`-based same-source lookup, close-missing, and source-reference existence helpers, using legacy-string fallback only where migration safety requires it.
- [x] T010 [P] Extend `app/repositories/sync_run.py` with `source_id`-based running lookup, sync-run creation support, and source-reference existence helpers, using legacy-string fallback only where migration safety requires it.
- [x] T011 Update `app/services/application/full_snapshot_sync.py` so same-source reconcile uses `source_id` as the authoritative owner key while dual-writing both `source_id` and legacy `source`.
- [x] T012 Update `app/services/application/sync.py` so overlap detection, sync-run creation, and sync-run completion use `source_id` as the authoritative owner key.
- [x] T013 Update `app/services/application/job.py` and `app/repositories/source.py` so direct job creation can resolve a legacy `source` string to authoritative `source_id` and fail fast if resolution is impossible.
- [x] T014 [P] Update `tests/unit/test_full_snapshot_sync.py`, `tests/unit/test_sync_service.py`, `tests/unit/test_sync_run_repository.py`, and `tests/unit/test_job_repository_dedup.py` to validate authoritative `source_id` behavior and dual-write expectations.

**Checkpoint**: Same-source reconcile and overlap behavior are authoritative on `source_id`, with compatibility fallback limited to transitional rows.

---

## Phase 4: Source Lifecycle Guardrails

**Purpose**: Prevent source deletes or structural mutations from invalidating migrated ownership.

- [x] T015 [P] Update `tests/unit/test_source.py` to cover delete blocking and rejection of `platform` and `identifier` updates when a source is referenced by jobs or sync runs.
- [x] T016 [P] Update `tests/integration/test_source_api.py` to cover `409 Conflict` responses for deleting or mutating a referenced source.
- [x] T017 Update `app/services/application/source.py` so delete and mutation guards check both jobs and sync runs by `source_id`, not only by the legacy `source` string.
- [x] T018 Update `app/api/v1/sources.py` so referenced-source delete and mutation failures surface as explicit `409 Conflict` responses.

**Checkpoint**: Source lifecycle operations are safe throughout the compatibility window.

---

## Phase 5: API Compatibility & Tests

**Purpose**: Preserve client compatibility while making `source_id` visible and verifiable in read/write paths.

- [x] T019 [P] Update `tests/unit/test_job_service.py` for direct-create source resolution, compatibility reads, and failure behavior when a legacy `source` string cannot be resolved.
- [x] T020 [P] Update source-aware import tests in `tests/unit/test_import_company_api_jobs.py`, `tests/unit/test_import_greenhouse_jobs.py`, `tests/unit/test_import_lever_jobs.py`, `tests/unit/test_import_ashby_jobs.py`, `tests/unit/test_import_smartrecruiters_jobs.py`, `tests/unit/test_import_eightfold_jobs.py`, and `tests/unit/test_run_scheduled_ingests.py` so newly written rows are asserted to carry both `source_id` and legacy `source`.
- [x] T021 Create `tests/integration/test_job_api.py` covering job create/read compatibility, including `source_id` exposure without removing the legacy `source` field.
- [x] T022 Update `app/api/v1/jobs.py` and supporting job serialization paths so compatibility writes resolve to authoritative `source_id` and read responses expose `source_id`.

**Checkpoint**: API consumers can read `source_id` while continuing to rely on the legacy `source` field during rollout.

---

## Phase 6: Constraint Enforcement & Cleanup-in-Scope

**Purpose**: Finalize authoritative ownership and remove temporary migration-only behavior.

- [x] T023 Create a second Alembic revision under `alembic/versions/` that sets `job.source_id` and `syncrun.source_id` to `NOT NULL` and removes authoritative dependency on old string-only unique/index paths.
- [x] T024 Remove temporary runtime fallback logic that still consults the legacy `source` string for authoritative behavior once post-backfill validation proves every row has `source_id`.
- [x] T025 Update `README.md`, `app/models/README.md`, `docs/architecture/README.md`, and `docs/ROADMAP.md` to document `source_id` as the authoritative owner key and the legacy `source` field as compatibility state.
- [x] T026 Run targeted suites for this feature with `./scripts/uv run pytest tests/unit/test_full_snapshot_sync.py tests/unit/test_sync_service.py tests/unit/test_sync_run_repository.py tests/unit/test_job_repository_dedup.py tests/unit/test_job_service.py tests/unit/test_source.py tests/unit/test_import_company_api_jobs.py tests/unit/test_import_greenhouse_jobs.py tests/unit/test_import_lever_jobs.py tests/unit/test_import_ashby_jobs.py tests/unit/test_import_smartrecruiters_jobs.py tests/unit/test_import_eightfold_jobs.py tests/unit/test_run_scheduled_ingests.py tests/integration/test_source_api.py tests/integration/test_job_api.py`.
- [x] T027 Validate `specs/001-source-id-fks/quickstart.md` against a real database snapshot or staging dataset and record any rollout blockers before physical column rename follow-up work is planned.

**Checkpoint**: `source_id` is authoritative and enforced, while physical rename of the legacy `source` column remains explicitly deferred.

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 blocks all later work because rollout and blocker conditions must be documented up front.
- Phase 2 blocks all later code changes because schema support and backfill must exist before authoritative cutover.
- Phase 3 depends on Phase 2 because repositories and application services need `source_id` columns and backfilled data.
- Phase 4 depends on Phase 3 because guardrails should validate against the authoritative owner key.
- Phase 5 depends on Phases 3 and 4 because API compatibility and test expectations depend on the new runtime behavior.
- Phase 6 depends on successful post-backfill validation plus the compatibility rollout from Phases 3 through 5.

### Parallel Opportunities

- T007 and T008 can run in parallel after the first migration shape is agreed.
- T009 and T010 can run in parallel once schema support exists.
- T014 can be split among repository and sync-related unit tests in parallel.
- T015 and T016 can run in parallel for source lifecycle coverage.
- T019 and T020 can run in parallel for compatibility-oriented unit tests.

## Notes

- Keep the physical rename from `source` to `source_key` out of this feature.
- Do not mix schema expansion/backfill and `NOT NULL` enforcement into the same Alembic revision.
- Treat any unmatched legacy key or duplicate `(source_id, external_job_id)` ownership as a blocker, not a warning.
