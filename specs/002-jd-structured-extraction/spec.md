# Feature Specification: JD Structured Extraction

**Feature Branch**: `002-jd-structured-extraction`
**Created**: 2026-03-05
**Status**: Implemented
**Input**: Extract structured fields from job descriptions using a hybrid flow: deterministic rule extraction + compact LLM extraction.

## Summary

Implement a production-safe JD structured extraction flow that converts raw job descriptions into normalized structured data for downstream filtering, ranking, and matching. The extraction path combines deterministic rules (for stable fields) with LLM outputs (for non-deterministic fields), then persists results on the existing `job` model.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Deterministic Rule Extraction (Priority: P1)

As a platform owner, I need core screening fields to be extracted deterministically so behavior is stable and cheap for high-volume backfills.

**Why this priority**: Sponsorship, degree level, and years-of-experience are hard-filter fields. They must remain predictable and low-cost.

**Independent Test**: Run rule extraction on representative JDs and verify sponsorship/degree/year/seniority outputs are normalized and stable.

**Acceptance Scenarios**:

1. **Given** JD text with sponsorship signals, **When** rule extraction runs, **Then** `sponsorship_not_available` is normalized to `yes/no/unknown`.
2. **Given** JD text with degree requirements, **When** rule extraction runs, **Then** `min_degree_level` and `min_degree_rank` are derived consistently.
3. **Given** JD text with years-of-experience ranges, **When** rule extraction runs, **Then** `experience_years` and normalized requirements are extracted deterministically.
4. **Given** JD title and/or experience signals, **When** rule extraction runs, **Then** `seniority_level` is derived deterministically.

---

### User Story 2 - Compact LLM Extraction and Required Skills Normalization (Priority: P1)

As a matching pipeline owner, I need LLM extraction for role/domain and required skills, and I need required skills normalized into stable canonical outputs so downstream matching can use consistent semantics.

**Why this priority**: Rule-only extraction underperforms for nuanced domain classification and required skill signals, and raw skill strings are too noisy for stable matching quality.

**Independent Test**: Mock LLM responses for single and batch inputs and verify normalized structured outputs are produced, validated, and mapped into canonical-or-unknown skill results.

**Acceptance Scenarios**:

1. **Given** a JD input, **When** compact LLM extraction runs, **Then** normalized `job_domain_normalized` and `required_skills` fields are produced.
2. **Given** `required_skills` containing aliases/synonyms, **When** skills normalization runs, **Then** canonical skill labels are produced for mappable items.
3. **Given** `required_skills` items that cannot be mapped reliably, **When** skills normalization runs, **Then** those items are explicitly marked unknown and not force-mapped.
4. **Given** a batch of JDs, **When** batch extraction runs, **Then** all input `job_id`s are returned exactly once or the batch fails explicitly.
5. **Given** malformed or incomplete LLM output, **When** parsing/validation runs, **Then** extraction fails clearly (or preserves `unknown` where deterministic fallback is not defined).
6. **Given** LLM output with `job_domain_normalized = unknown`, **When** merge runs, **Then** domain remains `unknown` (no rule-based domain fallback is applied).

---

### User Story 3 - Persistence and Downstream Compatibility (Priority: P2)

As an application engineer, I need extracted results persisted in a shape compatible with existing query paths so matching/filtering can consume them safely.

**Why this priority**: Extraction is only useful if persisted consistently with current retrieval contracts.

**Independent Test**: Persist parsed results and verify `job.structured_jd` payload + typed projection fields are written and query contracts remain satisfied.

**Acceptance Scenarios**:

1. **Given** parsed structured JD output, **When** persistence runs, **Then** `job.structured_jd` stores compact payload fields and typed columns are projected correctly.
2. **Given** persisted extraction output, **When** downstream matching query executes, **Then** `structured_jd_version` compatibility checks continue to pass.
3. **Given** batch persistence input missing one target job mapping, **When** persistence runs, **Then** the write fails explicitly without partial silent corruption.

## Edge Cases

- JD description is empty or missing usable text.
- HTML-only description requires text conversion before extraction.
- LLM batch output has duplicate IDs, missing IDs, or unexpected IDs.
- LLM output contains invalid enum values or malformed list fields.
- LLM returns `job_domain_normalized = unknown`; the pipeline preserves `unknown` without deterministic domain fallback.
- Legacy industry/domain keys appear in payload and must normalize into `job_domain_*` conventions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support deterministic rule extraction for sponsorship, degree, experience, and seniority-related fields.
- **FR-002**: The system MUST support compact LLM extraction for non-deterministic JD fields (at minimum: domain and required skills).
- **FR-003**: The system MUST support both single-item and batch extraction workflows.
- **FR-004**: Batch extraction MUST enforce strict input/output `job_id` consistency (no missing, duplicate, or unexpected IDs).
- **FR-005**: The system MUST normalize structured outputs into canonical enums/typed values before persistence.
- **FR-006**: The system MUST persist structured extraction outputs into existing `job` storage fields (`structured_jd` + typed projection columns).
- **FR-007**: The system MUST preserve downstream compatibility via `structured_jd_version` semantics used by matching/query paths.
- **FR-008**: The system MUST provide automated tests covering rule extraction, LLM extraction normalization, batch consistency checks, and persistence mapping behavior.

### Non-Goals (for this feature)

- Introducing a new dedicated structured JD persistence table.
- Building a full parse-run audit subsystem.
- Redesigning matching/retrieval beyond current structured JD compatibility contracts.
- Implementing full ontology-level normalization for domain semantics and cross-taxonomy alignment beyond required-skills canonical mapping (for example: domain ontology expansion, cross-source taxonomy reconciliation, and advanced semantic harmonization).

### Planned Follow-Up (Post-002)

- Extend normalization coverage to `preferred_skills` and `job_domain_*` semantic aliases with explicit quality gates.
- Add richer evaluation fixtures/metrics for normalization quality (precision/recall on canonical labels) and drift monitoring after production rollout.

### Key Entities *(include if feature involves data)*

- **StructuredJD**: Canonical extracted value object used before persistence.
- **StructuredJDPayload**: Compact JSON payload stored in `job.structured_jd`.
- **StructuredJDProjection**: Typed projection fields persisted on `job` (sponsorship/domain/degree/version columns).
- **BatchStructuredJDItem**: Batch extraction item keyed by `job_id`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Unit tests verify deterministic rule extraction output normalization for sponsorship, degree, experience, and seniority fields.
- **SC-002**: Unit tests verify compact single/batch LLM extraction paths produce valid normalized structured outputs.
- **SC-003**: Unit tests verify batch extraction fails on ID-set inconsistencies (missing/duplicate/unexpected IDs).
- **SC-004**: Persistence tests verify `job.structured_jd` and typed projection fields are written consistently with schema version compatibility.
