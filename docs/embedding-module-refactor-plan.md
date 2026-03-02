# Embedding Infra Module Refactor Plan

## Scope
Refactor `app/services/infra/embedding.py` into a small module set that is easier to maintain and test, while keeping current external call patterns stable (`embed_text(...)`, `embed_texts(...)`, `get_embedding_config(...)`, `resolve_active_job_embedding_target(...)`).

## Goals
- Separate concerns: config normalization, target descriptor resolution, response parsing, retry policy, request assembly.
- Reduce broad exception handling in `embed_texts(...)` and make retry behavior explicit.
- Keep model identity and target descriptor behavior stable for storage compatibility.
- Preserve existing call-site behavior for application services and scripts.

## Non-Goals
- Introduce provider-specific SDKs.
- Redesign embedding storage schema or repository interfaces.
- Change all embedding call sites in one pass.

## Proposed Structure
Create package: `app/services/infra/embedding/`

- `types.py`
  - `EmbeddingConfig`
  - `EmbeddingTargetDescriptor`
- `config.py`
  - `get_embedding_config()`
  - `_normalize_api_base()`
  - `resolve_embedding_model_name()`
  - `normalize_embedding_model_identity()`
- `targets.py`
  - `JOB_EMBEDDING_KIND`
  - `JOB_EMBEDDING_TARGET_REVISION`
  - `resolve_active_job_embedding_target()`
- `parsing.py`
  - `_extract_vector()`
  - response shape validation helpers
- `client.py`
  - request kwargs assembly
  - retry/backoff policy
  - dimensions fallback policy
  - `embed_texts()` / `embed_text()`

`app/services/infra/embedding.py` becomes a compatibility facade re-exporting the stable API.

## Key Design Decisions
1. Backward compatibility first.
- Keep function signatures and return shapes stable.
- Keep persisted model identity format unchanged.

2. Retry policy should be explicit and bounded.
- Avoid nested generic `except Exception` fallback logic.
- Retry with clear branches: transient failures vs dimension-unsupported fallback.

3. Validation at module boundary.
- Validate response data is list-like and non-empty.
- Validate each embedding item and numeric coercion behavior.
- Optionally verify vector dimensions when caller requests `dimensions`.

4. Progressive migration.
- Mechanical split first.
- Then retry/fallback cleanup.
- Then validation + compatibility cleanup.

## Implementation Plan

### Phase 1: Mechanical Split (No Behavior Changes)
- Add package files and move helpers by concern.
- Keep `embedding.py` facade exports stable.
- Ensure existing tests pass unchanged.

Acceptance criteria:
- No call-site edits required.
- Existing embedding and match-service tests remain green.

### Phase 2: Retry/Fallback Refactor
- Extract `_build_embedding_kwargs()`.
- Replace nested fallback block with explicit policy:
  - first attempt with dimensions (if provided)
  - one fallback attempt without dimensions when provider rejects dimensions
  - bounded retries for transient errors
- Keep current default retry count semantics.

Acceptance criteria:
- Behavior is deterministic and testable.
- No duplicated silent retries beyond configured policy.

### Phase 3: Response Validation Hardening
- Centralize data extraction/validation in `parsing.py`.
- Add optional vector count / dimension checks for safer failures.
- Improve error messages for script and API diagnostics.

Acceptance criteria:
- Invalid provider responses fail with actionable errors.
- Existing happy-path behavior unchanged.

### Phase 4: Compatibility Cleanup
- Remove transitional internals used only during split.
- Keep stable exports in package `__init__.py`.
- Add short developer note documenting retry/fallback rules.

Acceptance criteria:
- Public API remains stable.
- Internals are package-native and easier to evolve.

## Testing Plan

### Unit Tests
- `config.py`
  - provider/model normalization
  - api_base normalization for anthropic/gemini suffix handling
- `parsing.py`
  - valid vector extraction from dict/object responses
  - invalid item/data shape handling
  - numeric coercion edge cases
- `client.py`
  - empty input fast-path
  - dimensions fallback path
  - transient retry path and retry limits

### Regression Tests
Run existing embedding-related tests:
- `tests/unit/test_embedding_service.py`
- `tests/unit/test_match_service.py` (embedding integration path)
- `tests/unit/test_backfill_job_embeddings_gemini.py`

## Risks and Mitigations
- Risk: behavior drift in retries can change script throughput.
  - Mitigation: pin retry semantics in unit tests before changing logic.
- Risk: stricter validation may surface previously hidden provider issues.
  - Mitigation: keep error messages explicit and include provider/model context.
- Risk: identity normalization drift could break embedding target matching.
  - Mitigation: add tests for `normalize_embedding_model_identity()` and target descriptor stability.

## Migration Notes
- Existing imports should continue to work:
  - `from app.services.infra.embedding import embed_text, embed_texts, get_embedding_config`
- No schema or repository migration is required for this refactor.

## Deliverables
- New `app/services/infra/embedding/` package.
- Backward-compatible facade in `app/services/infra/embedding.py`.
- Added/updated tests for config, parsing, and retry behavior.
- Developer note in `docs/` about retry + dimensions fallback behavior.

## Suggested PR Breakdown
1. PR-1: mechanical split + no behavior change.
2. PR-2: retry/fallback policy cleanup + tests.
3. PR-3: response validation hardening + docs cleanup.
