# LLM Match Reranker Refactor Plan

## Scope
Refactor `app/services/infra/llm_match_recommendation.py` into layered modules that better match current architecture (`domain` / `application` / `infra`) while keeping current external call patterns stable for matching flows and tests.

## Why This Next
- The current file sits in `infra` but contains mixed concerns:
  - domain policy (`LLMRecommendationEnum`, `LLM_ADJUSTMENT_MAP`)
  - application orchestration (`apply_llm_rerank(...)`, concurrency, reorder summary)
  - payload shaping/sanitization for prompt grounding
  - infra call to LLM (`complete_json(...)`)
- This makes boundaries unclear and raises maintenance/test cost.

## Goals
- Move non-infra concerns out of `infra` without breaking callers.
- Keep `MatchExperimentService` behavior stable.
- Keep response shape stable (`llm_*` fields, rerank summary fields, adjustment semantics).
- Make each concern independently testable (policy, payload, orchestration, transport).

## Non-Goals
- Change match ranking formula outside existing LLM adjustment policy.
- Redesign prompt strategy or recommendation labels.
- Introduce provider-specific SDKs.
- Migrate all call sites to new import paths in one pass.

## Proposed Structure

### Domain
Create: `app/services/domain/llm_rerank_policy.py`
- `LLMRecommendationEnum`
- `LLM_ADJUSTMENT_MAP`
- `get_llm_adjustment(...)`
- stable summary default helpers (if policy-owned)

### Application
Create package: `app/services/application/llm_rerank/`
- `payload.py`
  - `build_llm_match_payload(...)`
  - sanitize/coercion helpers
  - recent work history extraction and job profile shaping
- `orchestrator.py`
  - `attach_default_llm_fields(...)`
  - `apply_llm_rerank(...)`
  - `LLMMatchReranker`
  - rerank summary assembly
- `models.py` (optional if useful for clarity)
  - `LLMMatchRecommendation` schema and list normalization helpers

### Infra
Create: `app/services/infra/llm_match_client.py`
- `get_llm_match_recommendation(...)`
- provider config checks
- prompt + `complete_json(...)` transport call

### Compatibility Facade
Keep `app/services/infra/llm_match_recommendation.py` as a temporary facade re-exporting stable symbols used by existing call sites/tests.

## Key Design Decisions
1. Layer ownership by responsibility.
- `infra` owns transport/integration.
- `application` owns orchestration and request-level workflow behavior.
- `domain` owns scoring policy semantics and recommendation mapping.

2. Backward compatibility first.
- Keep existing return payload keys and types.
- Keep existing adjustment map semantics unchanged.
- Keep current exception behavior at service boundary where practical.

3. Progressive migration over big-bang move.
- Mechanical extraction first.
- Boundary cleanup second.
- Then remove transitional compatibility internals.

## Implementation Plan

### Phase 1: Mechanical Extraction (No Behavior Change)
- Create target modules.
- Move functions by concern with minimal code changes.
- Keep `infra/llm_match_recommendation.py` re-exporting current API.

Acceptance criteria:
- No call-site edits required.
- Existing LLM rerank and match service tests stay green.

### Phase 2: Boundary Cleanup
- Move policy constants/enums to `domain`.
- Keep orchestration in `application`.
- Keep LLM transport in `infra`.
- Remove cross-layer helper leakage where possible.

Acceptance criteria:
- Imports reflect intended layering.
- No behavior drift in rerank ordering and summary fields.

### Phase 3: Validation and Diagnostics Hardening
- Improve guardrails around payload shape and context row defaults.
- Keep per-item failure fallback behavior explicit.
- Add short docs note for rerank execution/failure semantics.

Acceptance criteria:
- Per-item LLM failures remain non-fatal to full rerank pipeline.
- Errors are easier to diagnose without changing response contract.

### Phase 4: Compatibility Cleanup
- Remove temporary wrappers only used during split.
- Keep one stable external surface for callers.

Acceptance criteria:
- Public API remains stable.
- Internals are layered and easier to evolve.

## Testing Plan

### Unit Tests
- Policy module:
  - recommendation-to-adjustment mapping stability
  - unknown/None recommendation handling
- Payload module:
  - injection redaction
  - truncation limits
  - list coercion and max-item limits
- Orchestrator module:
  - top-N window behavior
  - per-item failure fallback
  - reorder behavior and summary counters
  - concurrency path behavior
- Infra client:
  - config validation
  - `complete_json(...)` call shape and structured parse

### Regression Tests
Run current tests touching this flow:
- `tests/unit/test_llm_match_recommendation.py`
- `tests/unit/test_match_service.py`
- `tests/unit/services/infra/test_llm_usage.py` (usage snapshot interaction path)

## Risks and Mitigations
- Risk: subtle reorder drift after function moves.
  - Mitigation: keep golden ordering assertions in rerank tests.
- Risk: payload shaping drift changes LLM outputs.
  - Mitigation: pin key payload-shape tests before moves.
- Risk: import path churn in call sites/tests.
  - Mitigation: keep compatibility facade until migration is complete.

## Migration Notes
- Existing imports can remain during migration:
  - `from app.services.infra.llm_match_recommendation import LLMMatchReranker`
- New/updated code should prefer layered module paths after Phase 2.

## Deliverables
- New domain/application/infra modules with clear ownership.
- Temporary compatibility facade in `infra/llm_match_recommendation.py`.
- Updated tests for policy, payload, orchestration, and client boundary.
- Short developer note documenting rerank execution/failure semantics.

## Suggested PR Breakdown
1. PR-1: mechanical extraction + compatibility facade.
2. PR-2: policy/application/infra boundary cleanup + tests.
3. PR-3: validation/diagnostics hardening + docs cleanup.
