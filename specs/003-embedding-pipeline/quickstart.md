# Quickstart: Embedding Pipeline (Snapshot-Aligned)

## Goal

Validate embedding generation behavior and snapshot-aligned refresh semantics for feature `003-embedding-pipeline`.

## Prerequisites

1. Python environment synced (`./scripts/uv sync`).
2. Database migrated to latest head.
3. At least one source configured and snapshot sync runnable.
4. Embedding provider credentials configured in `.env`.

## Scenario A: Baseline reliability checks (US1)

Run focused embedding tests:

```bash
./.venv/bin/pytest \
  tests/unit/services/infra/test_embedding_client.py \
  tests/unit/services/infra/test_embedding_config.py \
  tests/unit/services/infra/test_embedding_parsing.py -q
```

Expected:
- Retry/fail-fast/fallback behaviors pass.

## Scenario B: Active-target storage checks (US2)

Run repository contract tests:

```bash
./.venv/bin/pytest tests/unit/repositories/test_job_embedding_repository.py -q
```

Expected:
- Active-target upsert remains single-row/idempotent for repeated writes.

## Scenario C: Snapshot-aligned refresh checks (US3)

1. Execute one successful snapshot sync for a target source.
2. Run embedding refresh flow bound to that successful snapshot outcome.
3. Re-run the same snapshot outcome path.

Expected:
- Refresh runs only after successful snapshot.
- Closed jobs are excluded from refresh scope.
- Re-run does not create duplicate active-target rows.

## Suggested validation suite

```bash
./.venv/bin/pytest \
  tests/unit/services/infra/test_embedding_client.py \
  tests/unit/repositories/test_job_embedding_repository.py \
  tests/unit/sync -q
```

## Notes

- This feature scope is embedding generation/refresh only.
- Recommendation behavior is intentionally out of scope for 003.
