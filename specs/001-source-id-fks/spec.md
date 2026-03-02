# Feature Specification: Source ID Ownership Migration

**Feature Branch**: `001-source-id-fks`  
**Created**: 2026-03-01  
**Status**: Draft  
**Input**: User description: "Add source_id foreign keys to job and syncrun while keeping the legacy source key for compatibility during migration"

## Summary

The current system still treats the legacy `source` string as the runtime authority for same-source ingest behavior, even though the codebase already has some transitional `source_id` and `source_key` naming in result objects and tests.

This feature completes the migration so that:

- `job.source_id` and `syncrun.source_id` become the authoritative owner keys
- runtime same-source lookups, close-missing logic, and overlap detection stop depending on the mutable legacy `source` string
- the legacy physical column `source` remains available as compatibility state during rollout
- `source_id` is ultimately enforced as `NOT NULL`

This feature explicitly does **not** rename the physical `source` column to `source_key`. That cleanup remains deferred to a later follow-up.

## User Scenarios & Testing

### User Story 1 - Preserve Same-Source Ownership Correctly (Priority: P1)

As a backend engineer running ingest, I need every `job` row and every `syncrun` row to belong to a concrete `Source` by foreign key so that full-snapshot reconcile, overlap protection, and future cleanup logic do not depend on a mutable derived string.

**Why this priority**: This is the core safety property behind the migration. Without authoritative ownership on `source_id`, the system can still orphan data when `platform` or `identifier` changes.

**Independent Test**: Backfill `source_id` on existing rows, run a full snapshot sync, and verify that same-source upsert and close-missing behavior operate only on rows with the matching `source_id`.

**Acceptance Scenarios**:

1. **Given** existing `sources`, `job`, and `syncrun` rows linked only by the legacy source key, **When** the migration backfill runs, **Then** each dependent row receives the correct `source_id` matching its owning `Source`.
2. **Given** two sources with overlapping `external_job_id` values, **When** a full snapshot sync runs for one source, **Then** inserts, updates, and close-missing logic affect only rows with that source's `source_id`.
3. **Given** a running sync for a source, **When** a second sync attempt starts for the same source, **Then** overlap detection is enforced by `source_id` rather than by recomputing the legacy key.

### User Story 2 - Protect Source Lifecycle Operations (Priority: P2)

As an engineer managing source records, I need source delete and update behavior to remain safe during the compatibility window so that dependent jobs and sync runs cannot be orphaned or silently detached.

**Why this priority**: Once ownership is moved to `source_id`, the database can enforce referential integrity. During the rollout, the service layer must also prevent mutating source fields in ways that would invalidate the legacy key stored on historical rows.

**Independent Test**: Attempt to delete or mutate a source that already has dependent `job` or `syncrun` rows and confirm the system blocks the operation with a clear failure.

**Acceptance Scenarios**:

1. **Given** a source with existing jobs or sync runs, **When** a delete is requested, **Then** the delete is rejected because dependent rows still reference that source.
2. **Given** a source with existing jobs or sync runs during the migration period, **When** `platform` or `identifier` is changed, **Then** the update is rejected to prevent legacy `source` drift.

### User Story 3 - Preserve Compatibility During Rollout (Priority: P3)

As an API consumer or operator reading existing payloads and logs, I need the legacy source key to remain available during the rollout so that the migration does not force a same-day client or operational tooling change.

**Why this priority**: The migration is primarily about internal authority and database integrity. Compatibility should be preserved long enough to cut over safely without coupling the change to an unnecessary client break.

**Independent Test**: Verify that newly written jobs and sync runs include `source_id` internally while read payloads and operational logs still expose the legacy `source` string.

**Acceptance Scenarios**:

1. **Given** a migrated job or sync run, **When** it is returned through existing read paths, **Then** the legacy `source` field remains available for compatibility and debugging.
2. **Given** a new write path after the migration, **When** the system creates a job or sync run, **Then** it persists `source_id` as the authoritative owner and persists the legacy `source` field only as compatibility state.

## Edge Cases

- Existing `job.source` or `syncrun.source` values may not map to any current `Source` because the source's `platform` or `identifier` was edited before the migration.
- Backfill may discover duplicate `(source_id, external_job_id)` rows that were previously hidden behind inconsistent legacy source keys.
- Some internal write paths may still know only the legacy `source` string; they must fail fast if that string cannot be resolved to a `source_id`.
- A source may have sync-run history but no current jobs, or current jobs but no sync-run history; delete and mutation protection must handle both cases.
- The runtime may temporarily encounter rows where `source_id` is null during rollout. Legacy-string fallback is allowed only for those rows and only until enforcement is complete.
- The physical column rename from `source` to `source_key` must not happen in the same feature because it would mix semantic cutover with broad schema churn.

## Requirements

### Functional Requirements

- **FR-001**: The system MUST add nullable `source_id` columns to `job` and `syncrun`, each with foreign keys to `sources.id`.
- **FR-002**: The system MUST keep the existing legacy `source` string during the migration window so existing payloads, logs, and transitional code paths remain readable.
- **FR-003**: The system MUST backfill `source_id` for existing `job` and `syncrun` rows by matching the stored legacy key to `build_source_key(source.platform, source.identifier)`.
- **FR-004**: The rollout MUST stop before constraint enforcement if any existing `job` or `syncrun` row cannot be mapped to a valid `Source`.
- **FR-005**: The rollout MUST stop before constraint enforcement if backfill reveals duplicate `(source_id, external_job_id)` ownership that would violate same-source uniqueness.
- **FR-006**: The system MUST make `source_id` the authoritative key for same-source job uniqueness.
- **FR-007**: The system MUST make `source_id` the authoritative filter for full-snapshot lookup of existing jobs.
- **FR-008**: The system MUST make `source_id` the authoritative filter for close-missing behavior.
- **FR-009**: The system MUST make `source_id` the authoritative filter for sync overlap detection and sync-run history checks.
- **FR-010**: The system MUST dual-write both `source_id` and the legacy `source` string for all newly created jobs and sync runs during the compatibility period.
- **FR-011**: The system MUST allow temporary fallback to the legacy `source` string only for rows whose `source_id` is still null during the migration window.
- **FR-012**: The system MUST block deletion of a source that still has dependent jobs or sync runs.
- **FR-013**: The system MUST block `platform` or `identifier` updates for any source that already has dependent jobs or sync runs until the rollout no longer depends on the legacy key.
- **FR-014**: The system MUST add read-model support for exposing `source_id` without removing the legacy `source` field from existing API responses during the migration window.
- **FR-015**: The system MUST require direct write paths that receive only the legacy `source` string to resolve it to an authoritative `source_id` or fail fast.
- **FR-016**: The system MUST update repository, service, API, and integration tests so authoritative behavior is verified against `source_id`.
- **FR-017**: The system MUST enforce `job.source_id` and `syncrun.source_id` as `NOT NULL` only after backfill and dual-write validation are complete.
- **FR-018**: The system MUST defer any physical rename of the legacy `source` column to a separate cleanup task after `source_id` is fully authoritative.

### Key Entities

- **Source**: The configured upstream source identified by `id`, `platform`, and `identifier`. It becomes the authoritative owner of `job` and `syncrun` rows.
- **Job**: A job posting that currently stores a legacy `source` key and will gain `source_id` as its authoritative owner key. Same-source uniqueness is scoped by `source_id + external_job_id`.
- **SyncRun**: A source-level execution record that currently stores only the legacy `source` key and will gain `source_id` so overlap checks and history lookups no longer depend on a mutable derived string.
- **Legacy Source Key**: The derived string currently stored physically as `source` and built from `platform:identifier`. During migration it remains a compatibility and debugging field, not the authority for joins.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of existing `job` rows and 100% of existing `syncrun` rows can be backfilled to a valid `source_id` before `NOT NULL` enforcement.
- **SC-002**: All authoritative same-source ingest behaviors in tests pass using `source_id`-based filtering, including upsert, close-missing, and overlap detection.
- **SC-003**: Attempts to delete or structurally mutate a referenced `Source` are rejected in automated tests during the compatibility period.
- **SC-004**: Existing read paths continue to expose the legacy `source` string after the migration, so current operational tooling does not require a same-day rewrite.
- **SC-005**: `job.source_id` and `syncrun.source_id` are enforced as `NOT NULL` only after backfill validation and compatibility rollout complete successfully.
