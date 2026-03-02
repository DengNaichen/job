# Quickstart: Source ID Ownership Migration

This document describes the operator workflow for rolling out the `source_id` ownership migration safely.

## Scope

This rollout covers:

- adding nullable `source_id` to `job` and `syncrun`
- backfilling existing rows
- dual-writing `source_id` plus legacy `source`
- cutting authoritative runtime behavior over to `source_id`
- enforcing `NOT NULL` once validation is clean

This rollout does **not** rename the physical `source` column to `source_key`.

## Preconditions

- Use the tracked repository Alembic setup:
  - `alembic.ini`
  - `alembic/`
- Ensure the database snapshot used for rollout matches the code being deployed.
- Do not apply the enforcement revision until all preflight and post-backfill checks are clean.

## Preflight Audit Queries

### 1. Confirm each source key maps to at most one source row

```sql
SELECT
  concat(platform, ':', btrim(identifier)) AS source_key,
  COUNT(*) AS source_count
FROM sources
GROUP BY 1
HAVING COUNT(*) > 1;
```

Expected result: zero rows.

### 2. Find `job` rows whose legacy key no longer maps to any current source

```sql
SELECT
  j.source,
  COUNT(*) AS job_count
FROM job AS j
LEFT JOIN sources AS s
  ON j.source = concat(s.platform, ':', btrim(s.identifier))
WHERE s.id IS NULL
GROUP BY j.source
ORDER BY job_count DESC, j.source;
```

Expected result: zero rows.

### 3. Find `syncrun` rows whose legacy key no longer maps to any current source

```sql
SELECT
  r.source,
  COUNT(*) AS run_count
FROM syncrun AS r
LEFT JOIN sources AS s
  ON r.source = concat(s.platform, ':', btrim(s.identifier))
WHERE s.id IS NULL
GROUP BY r.source
ORDER BY run_count DESC, r.source;
```

Expected result: zero rows.

### 4. Count legacy keys present in jobs or runs but missing from sources

```sql
WITH legacy_keys AS (
  SELECT source FROM job
  UNION
  SELECT source FROM syncrun
)
SELECT lk.source
FROM legacy_keys AS lk
LEFT JOIN sources AS s
  ON lk.source = concat(s.platform, ':', btrim(s.identifier))
WHERE s.id IS NULL
ORDER BY lk.source;
```

Expected result: zero rows.

## Rollout Order

1. Run all preflight audit queries.
2. Stop the rollout if any unmatched legacy keys are found.
3. Apply the schema-expansion and backfill revision.
4. Run all post-backfill validation queries.
5. Stop the rollout if any null `source_id` values remain or if duplicate ownership appears.
6. Deploy the dual-write and authoritative read-path application changes.
7. Run the smoke checks below.
8. Only after all checks are clean, apply the enforcement revision that sets `source_id` to `NOT NULL`.

## Post-Backfill Validation Queries

### 1. Verify `job.source_id` is fully populated

```sql
SELECT COUNT(*) AS null_job_source_ids
FROM job
WHERE source_id IS NULL;
```

Expected result: `0`.

### 2. Verify `syncrun.source_id` is fully populated

```sql
SELECT COUNT(*) AS null_syncrun_source_ids
FROM syncrun
WHERE source_id IS NULL;
```

Expected result: `0`.

### 3. Verify no duplicate authoritative same-source ownership exists

```sql
SELECT
  source_id,
  external_job_id,
  COUNT(*) AS duplicate_count
FROM job
GROUP BY source_id, external_job_id
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC, source_id, external_job_id;
```

Expected result: zero rows.

### 4. Verify every backfilled `source_id` still points at a valid source

```sql
SELECT COUNT(*) AS invalid_job_source_fk_count
FROM job AS j
LEFT JOIN sources AS s ON j.source_id = s.id
WHERE j.source_id IS NOT NULL
  AND s.id IS NULL;
```

```sql
SELECT COUNT(*) AS invalid_syncrun_source_fk_count
FROM syncrun AS r
LEFT JOIN sources AS s ON r.source_id = s.id
WHERE r.source_id IS NOT NULL
  AND s.id IS NULL;
```

Expected result: both queries return `0`.

## Smoke Checks

Run these after deploying the dual-write and authoritative read-path code, but before `NOT NULL` enforcement.

### 1. Full snapshot sync smoke test

- Choose one representative source with real jobs.
- Run a single sync.
- Verify:
  - a new `syncrun` row was created
  - touched jobs retain the legacy `source`
  - touched jobs also have the correct `source_id`
  - close-missing behavior affects only that source's rows

### 2. Overlap protection smoke test

- Start a sync for one source.
- Attempt a second sync for the same source while the first is still running.
- Verify the second attempt fails because of same-source overlap.

### 3. Source delete guard smoke test

- Attempt to delete a source that still has jobs or sync runs.
- Verify the operation is rejected.

### 4. Source mutation guard smoke test

- Attempt to update `platform` or `identifier` for a referenced source.
- Verify the operation is rejected with a conflict response.

## Stop Conditions

Stop the rollout immediately if any of the following are true:

- any preflight audit query returns unmatched legacy keys
- any backfilled `job` row still has `source_id IS NULL`
- any backfilled `syncrun` row still has `source_id IS NULL`
- any duplicate `(source_id, external_job_id)` rows appear
- sync smoke tests show same-source reconcile still operating by legacy key
- source delete or mutation guards do not block referenced sources

Do not apply the enforcement revision while any stop condition remains unresolved.

## Rollback Notes

- Before applying the enforcement revision, prefer rolling back by restoring application code and database state to the pre-rollout snapshot or by downgrading only the expansion revision if the data state is still understood and safe.
- After the enforcement revision is applied, do not assume a downgrade is operationally safe without an explicit rollback plan for data and constraints.
- If backfill exposes unmatched legacy keys or duplicate ownership, treat the rollout as blocked and fix the data first rather than forcing the migration forward.
