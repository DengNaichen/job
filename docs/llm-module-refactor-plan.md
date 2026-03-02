# LLM Infra Module Refactor Plan

## Scope
Refactor `app/services/infra/llm.py` into a small module set that is concurrency-safe, testable, and easier to evolve, while keeping the external call pattern stable (`complete_json(...)`, `get_llm_config(...)`).

## Goals
- Remove global mutable token tracking state.
- Eliminate duplicate token counting paths.
- Separate concerns: config normalization, response parsing, retry policy, usage accounting.
- Keep current feature behavior compatible for existing callers.

## Non-Goals
- Re-design prompt strategies.
- Introduce provider-specific SDKs.
- Change all call sites to new APIs in one shot.

## Proposed Structure
Create package: `app/services/infra/llm/`

- `types.py`
  - `LLMConfig`
  - `TokenUsage` (data model only)
- `config.py`
  - `get_llm_config()`
  - `_normalize_api_base()`
  - `_get_model_name()`
  - `_supports_temperature()`
  - `_supports_json_mode()`
- `parsing.py`
  - `_extract_text_parts()`
  - `_extract_choice_text()`
  - `_extract_choice_content()`
  - `_extract_json()`
- `usage.py`
  - request-local usage scope with `contextvars`
  - `start_usage_scope()`
  - `add_usage()`
  - `snapshot_usage()`
  - compatibility helper for `get_token_usage()` if needed
- `client.py`
  - litellm request assembly
  - retry/backoff logic
  - `complete_json()`

`app/services/infra/llm.py` becomes a compatibility facade re-exporting the stable API.

## Key Design Decisions
1. Token usage is request-scoped, not process-global.
- Use `contextvars.ContextVar[TokenUsage | None]`.
- No cross-request `reset()` race.

2. Single accounting path.
- Remove global `litellm.success_callback = [...]` usage accounting for this module.
- Account usage once after each `acompletion` response.

3. Backward compatibility first.
- Keep `complete_json(...)` signature unchanged.
- Keep `get_llm_config()` behavior unchanged.
- Keep existing error surface where practical (`ValueError` wrappers).

4. Progressive migration.
- Split files first with behavior parity.
- Then switch usage accounting implementation.
- Then clean up deprecated compatibility internals.

## Implementation Plan

### Phase 1: Mechanical Split (No Behavior Changes)
- Add package files and move pure helpers.
- Keep old `llm.py` as imports + thin forwarding layer.
- Ensure tests pass unchanged.

Acceptance criteria:
- No call-site edits required.
- Existing LLM-related tests stay green.

### Phase 2: Token Usage Refactor (Concurrency Safety)
- Implement request-local usage store in `usage.py`.
- Remove duplicated counting (callback + direct count).
- Update rerank flow to read scoped snapshot instead of global reset model.

Acceptance criteria:
- No duplicated token counts.
- Concurrent invocations do not pollute each other.

### Phase 3: Client Cleanup
- Extract `_build_completion_kwargs()`.
- Isolate retry policy and provider checks.
- Keep `complete_json()` short and readable.

Acceptance criteria:
- `complete_json()` complexity reduced.
- Behavior parity with prior response handling.

### Phase 4: Compatibility Cleanup
- Deprecate transitional helpers used only by old facade.
- Keep stable exports in one place (`__init__.py`).

Acceptance criteria:
- Internals are package-native.
- Public API remains stable.

## Testing Plan

### Unit Tests
- `parsing.py`
  - markdown fenced JSON extraction
  - nested braces and escaped quotes
  - invalid / partial JSON
  - max content size enforcement
- `config.py`
  - provider/model normalization cases
  - json-mode support matrix
- `usage.py`
  - scope isolation
  - nested scope behavior

### Async/Concurrency Tests
- Concurrent `complete_json()` calls with mocked litellm responses.
- Verify usage snapshots are isolated per request.
- Verify no shared reset side effects.

### Regression Tests
Run existing tests that touch LLM flows:
- JD parsing tests
- matching/rerank tests
- script-level tests that mock `complete_json`

## Risks and Mitigations
- Risk: hidden dependency on global `get_token_usage().reset()` semantics.
  - Mitigation: provide temporary compatibility adapter and migrate call sites explicitly.
- Risk: callback removal may break external shared instrumentation assumptions.
  - Mitigation: limit callback change to this module path and document behavior.
- Risk: subtle parsing behavior drift.
  - Mitigation: golden tests for representative raw outputs.

## Migration Notes
- Existing imports should continue to work:
  - `from app.services.infra.llm import complete_json, get_llm_config`
- If any code reads global usage counters directly, migrate to scoped usage snapshot API.

## Deliverables
- New `app/services/infra/llm/` package.
- Backward-compatible facade in `app/services/infra/llm.py`.
- Added/updated tests for parsing, usage scoping, and concurrency.
- Short developer note in `docs/` about usage tracking changes.

## Suggested PR Breakdown
1. PR-1: mechanical split + no behavior change.
2. PR-2: scoped usage accounting + rerank integration.
3. PR-3: cleanup/deprecations + final docs.
