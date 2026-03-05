# Research: Embedding Pipeline (003)

## Scope

Audit implemented state and define planning decisions for a snapshot-aligned embedding generation feature.

## Inputs Reviewed

- Spec: [/Users/nd/Developer/job/specs/003-embedding-pipeline/spec.md](/Users/nd/Developer/job/specs/003-embedding-pipeline/spec.md)
- Embedding infra package (`app/services/infra/embedding/*`)
- Embedding storage model/repository (`app/models/job_embedding.py`, `app/repositories/job_embedding.py`)
- Snapshot sync flow (`app/services/application/full_snapshot_sync/*`)
- Candidate selection helpers in job repository (`app/repositories/job.py`)
- Focused tests:
  - `tests/unit/services/infra/test_embedding_client.py`
  - `tests/unit/services/infra/test_embedding_config.py`
  - `tests/unit/services/infra/test_embedding_parsing.py`
  - `tests/unit/repositories/test_job_embedding_repository.py`
  - `tests/unit/services/infra/matching/test_query.py`
  - `tests/unit/services/application/test_match_service.py`

## Decision 1: Treat US1 (reliable generation) as done

Rationale:
- Retry/fail-fast behavior, dimensions fallback, and response validation are already implemented and passing in focused tests.
- Additional refactor in this area would increase risk without moving current feature scope.

Alternatives considered:
- Re-open retry policy tuning now: rejected as out of scope for current gap closure.

## Decision 2: Treat US2 (stable active target identity) as done

Rationale:
- Target identity resolution and storage/read isolation by `kind/revision/model/dim` already exist.
- Repository/model and retrieval paths already encode active-target semantics.

Alternatives considered:
- Introduce new target dimensions or versioning semantics now: rejected; no requirement pressure.

## Decision 3: Make US3 the only active implementation gap

Rationale:
- Current codebase contains snapshot sync and embedding primitives but no explicit, feature-scoped snapshot-triggered embedding refresh orchestration artifact.
- US3 acceptance criteria focus on orchestration + idempotent reruns aligned to successful snapshots.

Alternatives considered:
- Broaden 003 to include recommendation behavior: rejected by current feature boundary.

## Decision 4: Use snapshot outcomes as refresh driver for this feature

Rationale:
- Feature spec explicitly defines snapshot-aligned behavior.
- Operationally simpler to reason about and validate for this iteration.

Alternatives considered:
- Fingerprint-driven incremental refresh: deferred for future feature scope.
- Hybrid snapshot+fingerprint now: deferred to keep semantics explicit and reduce scope churn.

## Decision 5: Preserve active-target idempotent upsert as write contract

Rationale:
- Existing uniqueness and upsert semantics prevent duplicate active-target rows.
- Fits repeated snapshot rerun scenarios with predictable outcomes.

Alternatives considered:
- Replace with append-only embedding history writes: rejected for current scope and storage cost.

## Completion Audit (Current State)

- US1: Completed.
- US2: Completed.
- US3: Partially completed (orchestration and dedicated scenario tests remain for closure).

## Evidence Commands (executed)

1. `SPECIFY_FEATURE=003-embedding-pipeline .specify/scripts/bash/setup-plan.sh --json`
2. `SPECIFY_FEATURE=003-embedding-pipeline .specify/scripts/bash/check-prerequisites.sh --json --paths-only`
3. `./.venv/bin/pytest tests/unit/services/infra/test_embedding_client.py tests/unit/services/infra/test_embedding_config.py tests/unit/services/infra/test_embedding_parsing.py tests/unit/repositories/test_job_embedding_repository.py tests/unit/services/infra/matching/test_query.py tests/unit/services/application/test_match_service.py -q`
4. `rg -n "list_embeddable_jobs_for_active_target|count_jobs_missing_or_stale_active_target|count_fresh_active_target_jobs|content_fingerprint" app`

## Result

All technical-context unknowns for planning are resolved. No remaining `NEEDS CLARIFICATION` items for the current scope.
