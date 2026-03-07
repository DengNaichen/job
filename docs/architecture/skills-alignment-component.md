# Skills Alignment Component (Draft)

This document defines a lightweight, implementation-agnostic design for a
`skills alignment` component that maps extracted raw skill strings to a
canonical taxonomy.

This is a planning draft only. It does not force a specific provider
(`ESCO`, `O*NET`, internal taxonomy, etc.) and does not require immediate code changes.

## 1. Problem Statement

Current extraction output can contain stable structure (e.g. `required_skills`,
`preferred_skills`) while canonical alignment is still missing.

Without a dedicated alignment layer:

- same skill appears under many variants (`"js"`, `"javascript"`, `"node js"`)
- downstream filtering/ranking is inconsistent
- LLM output is hard to use as durable analytics keys

## 2. Goals

1. Convert raw skill text into canonical `skill_id` values.
2. Keep alignment deterministic and traceable.
3. Support both non-LLM and LLM-assisted modes.
4. Preserve unresolved skills for manual review and dictionary growth.

## 3. Non-Goals

- Building a full ontology management UI.
- Replacing existing JD extraction flow.
- Forcing a specific taxonomy vendor at this stage.

## 4. Component Boundary

Input:

- `raw_skill_text` (string)
- optional context (`job_title`, `job_domain`, `description_excerpt`)

Output:

- `canonical_skill_id` (nullable)
- `canonical_skill_name` (nullable)
- `alignment_status`: `mapped | review | unmapped`
- `alignment_method`: `exact | fuzzy | llm_disambiguation | none`
- `alignment_confidence` (0.0 - 1.0)
- `candidate_list` (top-k candidates with scores)

## 5. Pipeline Design

### Stage A: Normalize

- lowercase + trim
- whitespace collapse
- lightweight token normalization
  - examples: `c++ -> cpp`, `c# -> csharp`, `node.js -> nodejs`

### Stage B: Candidate Recall

Use one or more of:

1. alias dictionary exact match
2. fuzzy lexical match (token overlap / edit similarity)
3. optional embedding retrieval for semantic recall

Return top-k candidates with score.

### Stage C: Resolve

Resolution policy:

1. one high-confidence candidate -> `mapped`
2. multiple close candidates -> `review` (or optional LLM disambiguation)
3. no valid candidate -> `unmapped`

## 6. LLM Usage Policy (Optional)

If LLM is enabled, use it as a constrained selector, not a free generator.

Rules:

- LLM can only choose from provided candidate IDs.
- enforce strict schema output.
- invalid outputs are rejected and downgraded to `review`.

This keeps quality stable even when model output is cheap and fast.

## 7. Suggested Persistence Shape

Recommended fields for a normalized result table (or JSON payload):

- `job_id`
- `raw_skill`
- `normalized_skill`
- `canonical_skill_id` (nullable)
- `canonical_skill_name` (nullable)
- `alignment_status`
- `alignment_method`
- `alignment_confidence`
- `taxonomy_version`
- `model_version` (if LLM involved)
- `created_at`, `updated_at`

## 8. Operational Rules

### Triggering

Run alignment only when source content changed (e.g. content fingerprint changed),
not by `sync_run.updated_count`.

### Idempotency

Re-running with same input and same taxonomy/model versions should produce same
result payload.

### Auditability

Always keep:

- raw input text
- candidate list
- final selection reason / method

## 9. Quality Metrics

Track at least:

- `mapped_rate`
- `review_rate`
- `unmapped_rate`
- `auto_accept_precision` (from sampled review)
- top recurring unmapped terms

## 10. Incremental Rollout Plan

1. Start with alias + fuzzy only (no LLM).
2. Build review queue from `review` and `unmapped` buckets.
3. Grow alias dictionary from reviewed decisions.
4. Add optional LLM disambiguation only for ambiguous top-k cases.
5. Re-evaluate thresholds by weekly quality metrics.

## 11. Open Decisions

These are intentionally left open for later:

- canonical taxonomy source (`ESCO`/`O*NET`/internal)
- top-k size and score thresholds
- whether LLM is enabled in v1
- storage location (dedicated table vs nested JSONB)
