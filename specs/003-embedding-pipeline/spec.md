# Feature Specification: Embedding Pipeline

**Feature Branch**: `003-embedding-pipeline`  
**Created**: 2026-03-05  
**Status**: Planned  
**Input**: Data enrichment quality depends on stable embedding generation, consistent target identity, and snapshot-aligned lifecycle behavior.

## Summary

Provides a production-safe embedding capability: text is transformed into vectors with bounded retry behavior, stored under an explicit target identity, and refreshed in step with full snapshot sync outcomes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reliable Embedding Generation (Priority: P1)

As a system operator, I need embedding generation to tolerate transient provider instability so enrichment workflows remain available during normal API turbulence.

**Why this priority**: Without reliable embedding generation, downstream data quality and availability collapse immediately.

**Independent Test**: Simulate transient provider failures and verify requests retry within configured bounds, then succeed or fail deterministically.

**Acceptance Scenarios**:

1. **Given** temporary provider failures, **When** an embedding request is made, **Then** retries happen within a bounded limit.
2. **Given** non-retryable provider failures, **When** an embedding request is made, **Then** the system fails fast without unnecessary retries.
3. **Given** empty text input, **When** an embedding request is made, **Then** the system returns an empty result without calling external providers.

---

### User Story 2 - Stable Embedding Target Identity (Priority: P1)

As a data pipeline owner, I need vectors to be written and read under the same target identity so the system never mixes incompatible embeddings.

**Why this priority**: Target drift creates silent data quality failures that are hard to detect and expensive to recover.

**Independent Test**: Ingest embeddings and read them by configured active target; verify only target-consistent rows are selected.

**Acceptance Scenarios**:

1. **Given** an active embedding target definition, **When** vectors are persisted, **Then** rows are tagged with that exact target identity.
2. **Given** multiple historical targets in storage, **When** active-target reads run, **Then** only the active target rows are selected.
3. **Given** provider/model naming variants, **When** target identity is persisted, **Then** a stable normalized identity is used.

---

### User Story 3 - Snapshot-Aligned Embedding Refresh (Priority: P2)

As a data operator, I need embedding refresh behavior to align with successful full snapshot syncs so embedding data stays consistent with current job lifecycle.

**Why this priority**: Embedding freshness and job lifecycle must move together; otherwise embedding data drifts away from the latest snapshot state.

**Independent Test**: Run consecutive full snapshots and verify embeddings are refreshed for active jobs while closed jobs are not refreshed.

**Acceptance Scenarios**:

1. **Given** a successful full snapshot sync with active jobs, **When** embedding refresh runs, **Then** eligible jobs in the snapshot have active-target embeddings.
2. **Given** a subsequent successful snapshot where some jobs are missing, **When** reconciliation closes those jobs, **Then** closed jobs are excluded from embedding refresh scope.
3. **Given** repeated successful snapshots over the same active job set, **When** embedding refresh runs repeatedly, **Then** writes remain idempotent without duplicate active-target rows.

## Edge Cases

- Provider rejects requested vector dimensions for an otherwise valid request.
- Provider returns malformed payload shape or non-numeric vector values.
- Request partially succeeds after retries and must still produce deterministic failure behavior when limits are exceeded.
- Storage contains embeddings from multiple target versions and active-target reads must avoid cross-target contamination.
- Snapshot retries or reruns occur close together and embedding writes must remain idempotent.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support bounded retries for transient embedding-provider failures.
- **FR-002**: The system MUST fail fast on non-transient embedding-provider failures.
- **FR-003**: The system MUST support deterministic fallback behavior when requested dimensions are unsupported by a provider.
- **FR-004**: The system MUST validate embedding response shape and numeric content before accepting vectors.
- **FR-005**: The system MUST persist embeddings under an explicit target identity that includes kind, revision, model identity, and dimension.
- **FR-006**: The system MUST use a single active target identity for embedding read operations.
- **FR-007**: The system MUST drive embedding refresh from successful full snapshot sync outcomes.
- **FR-008**: The system MUST provide automated tests covering retry behavior, dimensions fallback, response validation, active-target isolation, and snapshot-aligned refresh semantics.

### Key Entities *(include if feature involves data)*

- **Embedding Target**: The active identity that defines compatibility boundaries for vectors.
- **Job Embedding Artifact**: A persisted vector representation associated with one job and one target.
- **Snapshot Sync Run**: A successful full-source reconciliation result that drives embedding refresh behavior.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Automated tests verify retry/fail-fast behavior under simulated transient and non-transient provider failures.
- **SC-002**: Automated tests verify target identity normalization and active-target isolation.
- **SC-003**: Automated tests verify snapshot-aligned refresh and idempotent active-target upsert behavior across repeated snapshots.
- **SC-004**: Core embedding unit and integration suites pass in CI without introducing flaky retry behavior.
