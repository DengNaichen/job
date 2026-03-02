# Implementation Plan: Embedding Storage Redesign

**Branch**: `005-embedding-storage-redesign` | **Date**: 2026-03-02 | **Spec**: [`/specs/005-embedding-storage-redesign/spec.md`](/Users/nd/Developer/job-005-embedding-storage-redesign/specs/005-embedding-storage-redesign/spec.md)
**Input**: Feature specification from `/specs/005-embedding-storage-redesign/spec.md`

## Summary

Move persisted job vectors out of the hot `job` row into a dedicated `job_embedding` store, keep model/version isolation explicit, and cut the matching recall query over to the new store without waiting for unfinished location work.

The current codebase already has a working embedding pipeline and matching baseline, but both are tightly coupled to `job.embedding`:

1. The `job` table still stores `embedding`, `embedding_model`, and `embedding_updated_at` directly on the main row.
2. The embedding backfill script decides pending work and freshness from those in-row columns.
3. The vector recall query orders directly by `job.embedding <=> $user_vec`.
4. The current design supports only one persisted job-side representation per row, making model changes and staged retrieval experiments unnecessarily destructive.

Implementation will therefore focus on storage isolation and staged cutover rather than retrieval-policy redesign:

1. Introduce a dedicated persisted `job_embedding` model and Alembic migration.
2. Define one stable active embedding target descriptor for current recall, based on the existing embedding configuration and a fixed job-side embedding kind.
3. Refactor the embedding backfill path to write and refresh records in `job_embedding`, using `content_fingerprint` or equivalent content state to detect staleness.
4. Support historical rollout by migrating usable legacy in-row vectors and generating missing/stale active-target vectors as needed.
5. Update matching recall to join against `job_embedding` and stop depending on `job.embedding` as the operational source of truth.

## Technical Context

**Language/Version**: Python 3.12  
**Primary Dependencies**: FastAPI, SQLModel, SQLAlchemy/Alembic, asyncpg, pgvector, LiteLLM  
**Storage**: PostgreSQL for relational data and vector storage, Supabase Storage for large job blobs  
**Testing**: pytest, pytest-asyncio, unit and integration suites under `tests/`  
**Target Platform**: Backend service and scheduled scripts running in local dev and Linux-style server environments  
**Project Type**: FastAPI web service with database-backed ingest and offline matching pipelines  
**Performance Goals**: Keep vector recall behavior stable while removing vector payloads from the hot `job` row, preserve current top-k recall/query semantics, and avoid full-corpus re-embedding for every rollout step  
**Constraints**: Must remain independent from location v2/v3, must not persist candidate/user embeddings, must not mix model or dimension targets in recall, must allow a bounded compatibility phase before legacy column cleanup  
**Scale/Scope**: Touches Alembic schema, SQLModel models, repository helpers, embedding config/target selection, the embedding backfill script, match query infrastructure, matching service wiring, targeted tests, and architecture/roadmap docs

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The repo's `.specify/memory/constitution.md` is still the default placeholder template, so there are no project-specific constitutional gates to enforce.

Operational gates for this feature:

- The redesign must introduce a dedicated persisted job-embedding store and stop treating `job.embedding` as the long-term operational source of truth.
- Active recall must select embeddings by explicit target metadata and must not silently compare request vectors against mixed model or mixed-dimension job vectors.
- Historical migration and backfill must be rerunnable and must not create duplicate active records for unchanged job-content and target state.
- Legacy in-row embedding columns may remain during a bounded rollout window, but the feature must define an explicit cutover and cleanup path.
- The redesign must remain independent from country canonicalization and canonical location modeling.

## Project Structure

### Documentation (this feature)

```text
specs/005-embedding-storage-redesign/
├── plan.md
├── spec.md
└── tasks.md
```

### Source Code (repository root)

```text
alembic/
└── versions/

app/
├── core/
├── models/
├── repositories/
├── services/
│   ├── application/
│   └── infra/
└── api/v1/

scripts/
├── backfill_job_embeddings_gemini.py
└── match_experiment.py

tests/
├── integration/
└── unit/
```

**Structure Decision**: Single backend service. The redesign should stay within the existing Postgres-backed matching stack by adding a new persisted embedding entity, refactoring the current script/query paths, and keeping rollout compatibility localized to the embedding pipeline rather than broadening into unrelated retrieval or location work.

## Implementation Strategy

### Phase A: Embedding Schema And Target Primitives

- Add a dedicated `JobEmbedding` model under `app/models/` and expose it through `app.models`.
- Create an Alembic migration that adds the new table, vector column, and indexes/constraints for active-target uniqueness while keeping legacy `job.embedding*` columns in place during rollout.
- Define a stable active embedding target descriptor in shared embedding infrastructure, using the existing configured model/dimension plus a fixed job-side embedding kind for the current JD-vector recall purpose.
- Reuse the existing normalized model resolution logic so stored target identity and query-time target selection come from the same code path.

### Phase B: New Write Path Cutover

- Create repository helpers for `job_embedding` persistence and freshness checks.
- Refactor `scripts/backfill_job_embeddings_gemini.py` to write vectors into `job_embedding` for the active target instead of treating `job.embedding` as the primary store.
- Use `content_fingerprint` or equivalent deterministic content state to decide whether an active-target embedding is fresh, missing, or stale.
- Keep any temporary dual-write or compatibility behavior explicit and bounded rather than implicit inside one-off SQL.

### Phase C: Historical Migration And Backfill

- Support migration of usable legacy in-row vectors into `job_embedding` when model/dimension state is compatible with the active target.
- Regenerate embeddings only when migration alone cannot satisfy the active target, such as missing records or stale content state.
- Add batch helpers for pending, stale, and legacy-migration candidate selection so the backfill logic does not repeatedly scan unrelated rows.
- Preserve dry-run and rerun safety so interrupted or incremental rollouts stay deterministic.

### Phase D: Matching Query Cutover

- Update `app/services/infra/match_query.py` to join against `job_embedding` and filter by the active target descriptor.
- Keep request-time candidate embedding generation ephemeral, but ensure request vector dimensions remain aligned with the selected stored target.
- Preserve current hard filters, cosine thresholding, deterministic rerank, and optional LLM rerank unless storage cutover forces interface adjustments.
- Make any fallback behavior explicit and temporary so the matching path does not remain secretly coupled to `job.embedding`.

### Phase E: Documentation And Cleanup Notes

- Document the dedicated embedding store and rollout order in `README.md`, `docs/architecture/README.md`, and `docs/ROADMAP.md`.
- Record the bounded cleanup plan for removing legacy `job.embedding*` columns once the new store is stable.
- Keep location v2/v3 and broader hybrid retrieval redesign explicitly out of scope for this feature.

## Open Design Assumptions

- The first version of this redesign will treat the active persisted target as one fixed job-side embedding kind, scoped to the current JD-vector recall use case.
- One `job_embedding` row per active target is sufficient; content changes should refresh that row in place rather than preserving historical vectors for every past `content_fingerprint`.
- The normalized model string returned by the existing embedding helper is stable enough to serve as persisted model identity for this feature.
- Legacy `job.embedding*` columns may remain physically present during rollout, but matching and backfill should stop depending on them as the operational source of truth inside this feature.
- No job read API needs to expose persisted embedding payloads; this redesign is storage/query infrastructure, not a public API expansion.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |
