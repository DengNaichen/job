# Source ID Migration Spec

## Summary

The current MVP stores same-source ownership on `job.source` and `syncrun.source` as a derived string key such as `greenhouse:airbnb`.
That compromise made full-snapshot reconcile simple, but it leaves ownership unenforced at the database layer and makes `Source` mutations unsafe.

This spec moves authoritative ownership to `sources.id` by adding `source_id` foreign keys to `job` and `syncrun`.
The legacy string key is kept during rollout as a compatibility and cache field, but it must stop being the authoritative join key.

## Status (2026-03-02)

Most of this migration is now implemented in mainline code:

- `job.source_id` / `syncrun.source_id` are authoritative runtime keys
- same-source reconcile and close-missing use `source_id`
- overlap protection uses `source_id` and is guarded by a DB partial unique index for running `SyncRun`
- legacy `source` is still dual-written as compatibility state

This spec is kept as design history and cleanup guidance.

## Current State

Today the codebase uses `build_source_key(platform, identifier)` as the concrete same-source identity:

- `app/models/job.py`: `Job.source_id` is authoritative; legacy `Job.source` is retained as compatibility state
- `app/models/sync_run.py`: `SyncRun.source_id` is authoritative; legacy `SyncRun.source` is retained for compatibility/reads
- `app/services/application/full_snapshot_sync/`: same-source upsert and close-missing logic are keyed by `source_id`
- `app/services/application/sync.py`: overlap guard and sync-run creation are keyed by `source_id`
- `app/services/application/source.py`: delete/update protection checks `Job` and `SyncRun` references by `source_id`
- `app/schemas/job.py` and `app/schemas/sync_run.py`: public payloads expose `source`, not `source_id`

The architecture docs already describe the intended end state: `job` and `syncrun` should reference `sources.id`, with `source_key` retained only as a transitional field.

## Problems To Solve

### 1. No database-level ownership integrity

`job` and `syncrun` can exist without a valid `Source` row because their association is only a string.
The database cannot enforce `RESTRICT`, `CASCADE`, or join correctness.

### 2. Source updates can silently break historical associations

`SourceService.update_source()` currently allows `platform` and `identifier` updates.
Because jobs and sync runs store a derived string, changing either field can orphan the historical records from the current `Source` row.

### 3. Operational logic uses a mutable derived key

Full-snapshot reconcile, overlap protection, and source deletion checks depend on a key recomputed from mutable source fields.
That is fragile for long-lived data.

### 4. Cleanup and future schema work are harder than necessary

Follow-up tasks such as source-level cleanup, source-scoped reporting, or richer source metadata all become more awkward when ownership is not a foreign key.

## Goals

- Add `source_id` to `job` and `syncrun` and make it the authoritative ownership key
- Preserve current ingest behavior during rollout with no full rewrite of import scripts
- Keep same-source reconcile semantics intact
- Keep `source` as a compatibility field during migration, treating it conceptually as `source_key`
- Reach a state where all authoritative reads, writes, and constraints use `source_id`

## Non-Goals

- Redesign cross-source deduplication
- Change the external meaning of a `Source`
- Redesign job content/blob storage
- Complete location normalization or embedding storage changes
- Force an immediate public API break for clients currently reading `source`

## Target State

### Canonical ownership

- `sources.id` is the only authoritative owner key
- `job.source_id -> sources.id`
- `syncrun.source_id -> sources.id`

### Transitional legacy key

- Keep the current string field during rollout
- Treat that field as `source_key` in code and docs, even if the physical column is still named `source`
- Use it for logs, debugging, and backwards-compatible API payloads only

### Same-source invariants

- Same-source job uniqueness becomes `(source_id, external_job_id)`
- Close-missing logic scopes by `source_id`
- Overlap detection scopes by `source_id`
- Source deletion protection checks both `job` and `syncrun` references by `source_id`

### Source mutability during migration

Until all authoritative flows use `source_id`, a `Source` with dependent rows must not allow `platform` or `identifier` changes.
That avoids legacy `source_key` drift during the compatibility period.

## Recommended Rollout

### Phase 0: Preflight Audit

Before schema changes, audit current data:

- Every distinct `job.source` should map to exactly one `Source`
- Every distinct `syncrun.source` should map to exactly one `Source`
- There should be no orphaned rows whose stored key no longer matches any current `Source`

Recommended checks:

1. Count distinct `job.source` values and confirm each matches one `(platform, identifier)` pair in `sources`
2. Do the same for `syncrun.source`
3. Stop the migration if any unmatched rows exist

If the audit finds orphaned rows, fix those first.
Do not enforce `NOT NULL` or unique constraints until this audit is clean.

### Phase 1: Schema Expansion

Add the new columns and indexes without changing behavior yet.

`job`:

- add nullable `source_id`
- add foreign key to `sources.id` with `ON DELETE RESTRICT`
- add index on `source_id`
- add new unique constraint on `(source_id, external_job_id)`
- add new lookup index replacing `ix_job_source_status_last_seen_at` with a `source_id` variant

`syncrun`:

- add nullable `source_id`
- add foreign key to `sources.id` with `ON DELETE RESTRICT`
- add index on `source_id`
- add index to support running-run lookup by `source_id` and `status`

Important implementation note:

- Do not rename the physical `source` column in the same migration that introduces `source_id`
- In code, start referring to the legacy string as `source_key` to reduce ambiguity

### Phase 2: Backfill

Backfill `source_id` from the existing string key.

Matching rule:

- `job.source` or `syncrun.source` must equal `build_source_key(source.platform, source.identifier)`

Backfill approach:

1. Join each row to `sources` using the stored string key
2. Write the matching `sources.id` into `source_id`
3. Re-run the audit and confirm there are no remaining nulls except explicitly quarantined rows

If any rows fail to match, stop here.
Do not proceed to dual-read or `NOT NULL` enforcement with partial ownership.

### Phase 3: Dual-Write

Update write paths so new rows always carry both values:

- `source_id`: authoritative FK
- `source` / legacy string: compatibility field

Required code changes:

- `app/models/job.py`: add `source_id`, keep legacy `source`
- `app/models/sync_run.py`: add `source_id`, keep legacy `source`
- `app/services/application/full_snapshot_sync/`: write both fields when inserting or updating jobs
- `app/repositories/sync_run.py`: create runs with both `source_id` and legacy `source`
- `app/services/application/sync.py`: pass both values into sync-run creation
- `app/services/application/job.py`: if direct job creation stays supported, require source resolution before create

At this point, all newly written data should have `source_id`.

### Phase 4: Read Path Cutover

Move authoritative queries from legacy string filters to `source_id`.

Repository and service changes:

- `JobRepository.list_by_source_and_external_ids()` should become a `source_id`-based query
- `JobRepository.bulk_close_missing_for_source()` should become `source_id`-based
- `SyncRunRepository.get_running_by_source()` should become `source_id`-based
- `SyncRunRepository.has_any_for_source()` should become `source_id`-based
- `SourceService.delete_source()` must check both jobs and sync runs by `source_id`

Temporary fallback rule:

- Fallback to the legacy string only for rows with null `source_id`
- Treat that fallback as temporary migration support, not normal behavior

Once this phase is complete, same-source reconcile no longer depends on mutable source fields.

### Phase 5: Constraint Enforcement

After the backfill is complete and all write paths are dual-writing:

- set `job.source_id` to `NOT NULL`
- set `syncrun.source_id` to `NOT NULL`
- remove old unique/index dependencies from authoritative runtime queries
- keep legacy `source` only as compatibility state

At this phase, the database becomes the source of truth for ownership.

### Phase 6: Cleanup

Final cleanup should be separate from the FK rollout:

- decide whether the physical `source` column should be renamed to `source_key`
- remove temporary fallback code for null `source_id`
- remove old source-key-only repository methods
- update docs so `source_id` is clearly primary and `source_key` is explicitly legacy/cache-only

The recommended default is:

- finish the FK migration first
- rename the physical column later, in a smaller cleanup change

## API Compatibility

The repo currently exposes `source` in job and sync-run schemas.
To avoid an unnecessary API break during the migration:

- keep `source` in read payloads for now
- add `source_id` to read payloads once the model supports it
- keep accepting legacy `source` on write paths only if the service can resolve it to `source_id`

Preferred end state:

- read payloads expose both `source_id` and `source_key`
- internal logic does not rely on client-provided `source_key`

## Code Change Checklist

### Models and schemas

- `app/models/job.py`
- `app/models/sync_run.py`
- `app/schemas/job.py`
- `app/schemas/sync_run.py`

### Repositories

- `app/repositories/job.py`
- `app/repositories/sync_run.py`
- likely add a small existence helper in `JobRepository` for source delete protection

### Services

- `app/services/application/full_snapshot_sync/`
- `app/services/application/sync.py`
- `app/services/application/source.py`
- `app/services/application/job.py`

### Scripts

Import scripts mainly log `result.source_key` already and should need minimal or no direct changes.
The main behavior shift is inside the sync service and repositories.

### Tests

Update and extend tests covering:

- full-snapshot same-source upsert keyed by `source_id`
- close-missing behavior keyed by `source_id`
- overlap guard keyed by `source_id`
- source deletion blocked by existing jobs or sync runs
- source update blocked when dependent rows exist during migration
- successful backfill for old rows
- API payload compatibility for `source` plus `source_id`

## Acceptance Criteria

This task is done when all of the following are true:

1. Every `job` row has a valid `source_id`
2. Every `syncrun` row has a valid `source_id`
3. Full-snapshot reconcile uses `source_id` for lookups and close-missing behavior
4. Sync overlap protection uses `source_id`
5. Deleting a `Source` with dependent jobs or sync runs is blocked by FK-backed ownership
6. `platform` and `identifier` updates are blocked for referenced sources during the compatibility period
7. Existing API consumers can still read the legacy source key without a forced same-day migration

## Follow-Up Work

After this migration lands cleanly, the next logical cleanup is to rename the legacy string column from `source` to `source_key` so the schema matches its real role.
That should be tracked as a separate, smaller task once `source_id` is fully authoritative.
