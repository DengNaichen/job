# Tasks: Canonical Locations V3

**Input**: Design documents from `/specs/004-canonical-locations-v3/`  
**Prerequisites**: `spec.md`, `plan.md`

**Tests**: Tests are required because this feature introduces new normalized entities, deterministic identity/primary-link rules, rerunnable historical backfill behavior, and query/read cutover risk.

**Organization**: Tasks are grouped by user story so each slice can be validated independently once the shared schema + canonicalization primitives exist.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel
- **[Story]**: Maps to the user story in `spec.md`
- Every task lists concrete file paths that should be changed or created

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Establish normalized schema + shared canonicalization rules before touching ingest/backfill/query surfaces.

- [x] T001 Add an Alembic revision under `alembic/versions/` to create `locations` and `job_locations` tables, uniqueness/index constraints (`locations.canonical_key`, `job_locations(job_id, location_id)`, and one-primary-per-job guard), and rollback-safe defaults.
- [x] T002 [P] Create normalized entities in `app/models/location.py` and `app/models/job_location.py`, export them from `app/models/__init__.py`, and document them in `app/models/README.md`.
- [x] T003 [P] Create `app/repositories/location.py` and `app/repositories/job_location.py`, export them from `app/repositories/__init__.py`, and add reusable upsert/link helpers needed by ingest/backfill paths.
- [x] T004 [P] Add normalized location schema models in `app/schemas/location.py`, update `app/schemas/job.py` and `app/schemas/__init__.py`, and document compatibility behavior in `app/schemas/README.md`.
- [x] T005 Create shared canonicalization + primary-link primitives in `app/services/domain/canonical_location.py` (or equivalent) and integrate deterministic helpers with `app/services/domain/job_location.py` where compatibility sync rules live.
- [x] T006 [P] Add local GeoNames reference-data plumbing (for example `scripts/sync_geonames_reference.py`, `app/core/config.py`, `.env.example`, and docs) so canonicalization can resolve place identity offline without using GeoNames web APIs.

**Checkpoint**: The repo can represent canonical locations and deterministic job-location links in schema/domain layers, with one shared normalization policy and local reference data inputs.

---

## Phase 2: User Story 1 - Persist Reusable Canonical Locations For New Jobs (Priority: P1) 🎯 MVP

**Goal**: New ingests create/reuse canonical `locations` rows and persist deterministic `job_locations` links (including one primary link) while keeping compatibility fields aligned.

**Independent Test**: Ingest representative single-location, multi-location, country-only, and remote-scope fixtures; verify canonical row reuse, deterministic primary-link assignment, and compatibility-field alignment.

### Tests for User Story 1

- [x] T007 [P] [US1] Add canonicalization/primary-rule unit coverage in `tests/unit/services/domain/test_canonical_location.py` and extend `tests/unit/test_job_location.py` for multi-location, remote-scope, and deterministic tie-break cases.
- [x] T008 [P] [US1] Extend mapper and sync coverage in `tests/unit/ingest/mappers/test_company_apis.py`, `tests/unit/ingest/mappers/test_smartrecruiters.py`, `tests/unit/ingest/mappers/test_eightfold.py`, `tests/unit/ingest/mappers/test_lever.py`, `tests/unit/ingest/mappers/test_greenhouse.py`, and `tests/unit/ingest/mappers/test_ashby.py` for candidate-location extraction inputs.
- [x] T009 [P] [US1] Extend ingest transaction coverage in `tests/unit/test_full_snapshot_sync.py`, `tests/unit/test_job_service.py`, and `tests/integration/test_job_api.py` to assert location reuse, one-primary behavior, and compatibility-field alignment.

### Implementation for User Story 1

- [x] T010 [US1] Integrate canonical location persistence into `app/services/application/full_snapshot_sync.py` so each mapped job writes deterministic `job_locations` links in the same transaction as the job upsert.
- [x] T011 [US1] Update `app/ingest/mappers/base.py`, `app/ingest/mappers/apple.py`, `app/ingest/mappers/smartrecruiters.py`, `app/ingest/mappers/uber.py`, `app/ingest/mappers/tiktok.py`, `app/ingest/mappers/eightfold.py`, `app/ingest/mappers/lever.py`, `app/ingest/mappers/greenhouse.py`, and `app/ingest/mappers/ashby.py` so the pipeline can supply multi-location candidate hints deterministically.
- [x] T012 [US1] Wire repository/domain orchestration in `app/repositories/job.py`, `app/repositories/location.py`, `app/repositories/job_location.py`, and `app/services/application/sync.py` so canonical row reuse and link upsert semantics stay idempotent.
- [x] T013 [US1] Implement compatibility sync from primary link in `app/services/domain/job_location.py` and apply it from ingest write paths so `job.location_*` fields remain rollout-safe.

**Checkpoint**: New/updated jobs consistently persist canonical links with deterministic primaries and no duplicate canonical entities.

---

## Phase 3: User Story 2 - Backfill Historical Jobs Into Canonical Location Entities Safely (Priority: P2)

**Goal**: Historical rows gain canonical links through a rerunnable backfill process without duplicate drift or primary-link instability.

**Independent Test**: Run backfill on mixed-confidence fixtures; verify canonical reuse, restored additional links when confidence allows, idempotent reruns, and stable primary behavior.

### Tests for User Story 2

- [x] T014 [P] [US2] Expand `tests/unit/test_backfill_job_locations.py` for v3 backfill behavior (structured fields first, raw payload second, multi-location restoration, rerun idempotency, and compatibility-field alignment).
- [x] T015 [P] [US2] Add repository idempotency/constraint tests in `tests/unit/repositories/test_location_repository.py` and `tests/unit/repositories/test_job_location_repository.py`.
- [x] T016 [P] [US2] Update import-flow regression tests in `tests/unit/test_import_company_api_jobs.py`, `tests/unit/test_import_greenhouse_jobs.py`, `tests/unit/test_import_lever_jobs.py`, `tests/unit/test_import_ashby_jobs.py`, `tests/unit/test_import_smartrecruiters_jobs.py`, and `tests/unit/test_import_eightfold_jobs.py` for normalized link expectations where applicable.

### Implementation for User Story 2

- [x] T017 [US2] Create `scripts/backfill_job_locations_v3.py` (or equivalent v3 mode) to generate/reuse canonical locations and job links from historical jobs with rerunnable semantics.
- [x] T018 [US2] Extend `app/repositories/job.py` with backfill-target selection helpers (keyset pagination + candidate filtering) for efficient incremental rollout.
- [x] T019 [US2] Reuse shared canonicalization/primary-link logic from `app/services/domain/canonical_location.py` and `app/services/domain/job_location.py` in the backfill path so ingest and historical repair follow one rule set.

**Checkpoint**: Historical jobs can be normalized safely, with no duplicate row drift on reruns.

---

## Phase 4: User Story 3 - Query Through Normalized Locations While Preserving Compatibility (Priority: P3)

**Goal**: Query/read paths consume normalized location links for country-aware and multi-location behavior while legacy compatibility fields remain available.

**Independent Test**: Validate that read/query endpoints expose primary + full location sets and that country-aware filtering can match through linked canonical locations.

### Tests for User Story 3

- [x] T020 [P] [US3] Update `tests/unit/test_match_query.py`, `tests/unit/test_match_service.py`, and `tests/unit/test_match_schema.py` so country/location filtering expectations target normalized joins rather than only `job.location_country_code`.
- [x] T021 [P] [US3] Update `tests/integration/test_matching_api.py` and `tests/integration/test_job_api.py` to validate normalized location serialization plus compatibility-field continuity.
- [x] T022 [P] [US3] Update `tests/unit/test_llm_match_recommendation.py` and `tests/unit/test_match_experiment_script.py` if downstream payload builders now consume normalized primary/full location summaries.

### Implementation for User Story 3

- [x] T023 [US3] Refactor `app/services/infra/match_query.py`, `app/services/application/match_service.py`, and `app/api/v1/matching.py` so country-aware filters can join via `job_locations -> locations`.
- [x] T024 [US3] Update read serialization in `app/services/application/job.py`, `app/api/v1/jobs.py`, `app/schemas/job.py`, and `app/schemas/location.py` to expose primary + linked locations while preserving existing compatibility fields.
- [x] T025 [US3] Update docs in `docs/architecture/README.md`, `docs/ROADMAP.md`, and `README.md` to mark v3 normalized location tables as authoritative long-term location identity.

**Checkpoint**: Query/read paths can consume normalized links, and compatibility behavior remains stable during migration.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Validate v3 end-to-end and capture deferred cleanup explicitly.

- [x] T026 [P] Run targeted suites with `./scripts/uv run pytest tests/unit/services/domain/test_canonical_location.py tests/unit/test_job_location.py tests/unit/ingest/mappers/test_company_apis.py tests/unit/ingest/mappers/test_smartrecruiters.py tests/unit/ingest/mappers/test_eightfold.py tests/unit/ingest/mappers/test_lever.py tests/unit/ingest/mappers/test_greenhouse.py tests/unit/ingest/mappers/test_ashby.py tests/unit/test_full_snapshot_sync.py tests/unit/test_job_service.py tests/unit/test_backfill_job_locations.py tests/unit/repositories/test_location_repository.py tests/unit/repositories/test_job_location_repository.py tests/unit/test_import_company_api_jobs.py tests/unit/test_import_greenhouse_jobs.py tests/unit/test_import_lever_jobs.py tests/unit/test_import_ashby_jobs.py tests/unit/test_import_smartrecruiters_jobs.py tests/unit/test_import_eightfold_jobs.py tests/unit/test_match_query.py tests/unit/test_match_service.py tests/unit/test_match_schema.py tests/unit/test_llm_match_recommendation.py tests/unit/test_match_experiment_script.py tests/integration/test_job_api.py tests/integration/test_matching_api.py`.
- [x] T027 Do a manual dry run of `scripts/backfill_job_locations_v3.py` on a bounded dataset and record canonical reuse rate, multi-location restoration counts, primary-link stability, and unchanged-row skip counts.
- [x] T028 Capture post-v3 follow-up cleanup in `docs/ROADMAP.md` (timing for dropping/repurposing denormalized compatibility fields, GeoNames refresh cadence automation, and additional retrieval rollout steps).

---

## Dependencies & Execution Order

### Phase Dependencies

- Phase 1 blocks all user stories because schema/entities/canonicalization primitives define v3 behavior.
- US1 depends on Phase 1 and delivers MVP normalized ingest behavior.
- US2 depends on Phase 1 and should reuse the same canonicalization/primary-link rules proven in US1.
- US3 depends on normalized writes from US1 and is safest once US2 stabilizes historical coverage.
- Polish depends on the phases you intend to ship now.

### User Story Dependencies

- **US1 (P1)**: Required MVP slice once foundational schema/rules exist.
- **US2 (P2)**: Depends on foundational schema/rules and should follow US1 rule semantics exactly.
- **US3 (P3)**: Depends on normalized-link persistence from US1 and benefits from US2 historical consistency.

### Parallel Opportunities

- T002, T003, T004, and T006 can run in parallel after table shape is finalized.
- T007, T008, and T009 can run in parallel for US1 coverage.
- T014, T015, and T016 can run in parallel for US2 coverage.
- T020, T021, and T022 can run in parallel for US3 coverage.

## Implementation Strategy

### MVP First

1. Finish Phase 1.
2. Finish US1 ingest write-path rollout.
3. Prove canonical reuse + deterministic primary-link behavior via unit and sync tests.

### Incremental Delivery

1. Ship normalized schema + shared canonicalization.
2. Ship ingest writes to `locations + job_locations` with compatibility sync.
3. Ship historical backfill for mixed old/new corpus consistency.
4. Ship query/read cutover to normalized links with compatibility fields still present.

## Notes

- V3 is about canonical identity and many-to-many relationship modeling, not geometric/spatial ranking.
- GeoNames is a local reference metadata source, not an external request-time dependency.
- Preserve explicit separation between workplace semantics and employment semantics.
- Treat denormalized `job.location_*` fields as rollout compatibility state, not long-term identity authority.
