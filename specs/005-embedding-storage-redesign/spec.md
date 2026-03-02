# Feature Specification: Embedding Storage Redesign

**Feature Branch**: `005-embedding-storage-redesign`  
**Created**: 2026-03-02  
**Status**: Draft  
**Input**: User description: "Create a spec for moving job embeddings out of the hot job row with model/version isolation, independently from unfinished location work"

## Summary

The current matching baseline works by generating one request-time candidate embedding and comparing it against one persisted job embedding stored directly on the `job` row.

That design was acceptable for the first JD-vector recall slice, but it is now a structural constraint:

- vector columns live on the hot `job` row even though most read and ingest paths do not need them
- changing embedding model or dimension overwrites the previous representation instead of isolating it
- the backfill script decides freshness using `job.embedding` and `job.embedding_model`, which couples rollout behavior to one in-row state
- the recall query reaches directly into `job.embedding`, making storage redesign and retrieval evolution harder than they need to be

This feature introduces a dedicated persisted job-embedding store and migrates the matching stack to query through that store. It is explicitly independent from location modeling. `location_*` rollout may continue on its own track, and this feature must not wait for canonical `locations` or `job_locations`.

This feature also does **not** redesign retrieval strategy end to end. Hard filters, cosine thresholding, deterministic rerank, and optional LLM rerank may remain as they are. The change here is where job vectors live, how they are versioned, and how recall selects them safely.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Persist Job Embeddings Outside `job` For New Writes (Priority: P1)

As a backend engineer working on matching and retrieval, I need persisted job embeddings to live outside the hot `job` row so vector data can evolve without bloating the core job table or forcing one model/version to overwrite another.

**Why this priority**: This is the structural change that unlocks the redesign. Without it, every later model change, dual-model experiment, or retrieval refactor remains tied to one mutable vector column on `job`.

**Independent Test**: Generate embeddings for representative jobs using the configured embedding pipeline, then verify that the system writes them to the new embedding store with the expected target metadata while normal job ingest/read behavior remains unchanged.

**Acceptance Scenarios**:

1. **Given** a job with embeddable content and no persisted record for the active embedding target, **When** the embedding pipeline runs, **Then** it creates a dedicated job-embedding record instead of writing the vector onto `job`.
2. **Given** the same job is later embedded with a different model, dimension, or explicit embedding target revision, **When** the pipeline runs, **Then** the new representation is isolated from the previous one rather than destructively overwriting it.
3. **Given** a job already has a persisted embedding record for the same content state and active embedding target, **When** the pipeline reruns, **Then** the system can deterministically skip or refresh that record without creating duplicate active state.

---

### User Story 2 - Backfill And Migrate Historical Job Embeddings Safely (Priority: P2)

As an operator rolling forward from the baseline implementation, I need historical job embeddings to be migrated or regenerated into the new store so matching coverage stays consistent without requiring a same-day full reingest.

**Why this priority**: If the new store only supports future writes, recall behavior will diverge across the corpus for too long and rollout risk will stay high.

**Independent Test**: Run the migration/backfill flow against a mixed dataset containing jobs with legacy in-row vectors, jobs with embeddable descriptions but no vectors, and jobs with stale or mismatched model metadata, then verify that the resulting embedding store is complete, rerunnable, and non-duplicative.

**Acceptance Scenarios**:

1. **Given** a historical job with a populated legacy in-row vector and matching legacy metadata, **When** the migration/backfill runs, **Then** the system copies or rehomes that vector into the new store without losing the job-to-vector relationship.
2. **Given** a historical job without a usable persisted vector but with embeddable content, **When** the backfill runs, **Then** the system may generate a new record for the active embedding target in the new store.
3. **Given** the backfill is rerun against unchanged inputs, **When** existing records for the same job and active embedding target already exist, **Then** the process must not create duplicate active records or oscillate between conflicting states.
4. **Given** a job cannot currently produce a valid embedding because content is missing or malformed, **When** the backfill runs, **Then** the job is skipped or reported without corrupting existing good records for other targets.

---

### User Story 3 - Query Matching Through The New Embedding Store (Priority: P3)

As an engineer maintaining the matching pipeline, I need vector recall to read job embeddings from the dedicated store so retrieval no longer depends on `job.embedding` being present on the main table.

**Why this priority**: Storage redesign is incomplete until the query path stops depending on the legacy columns. The system needs an explicit cutover point for matching recall.

**Independent Test**: Run matching tests and a representative recall query after the storage migration, then verify that candidate selection still works when the active embedding record exists in the new store and that jobs lacking the selected record are handled predictably.

**Acceptance Scenarios**:

1. **Given** a matching request and a configured active embedding target, **When** candidate recall runs, **Then** the query selects vectors from the dedicated job-embedding store rather than from `job.embedding`.
2. **Given** the dataset contains more than one stored embedding representation for the same job, **When** matching runs, **Then** the query uses only the configured active target and ignores non-selected representations.
3. **Given** a job lacks the active embedding record, **When** matching recall runs, **Then** that job is excluded from vector recall without breaking hard-filter logic, reranking, or response serialization for the remaining candidates.
4. **Given** rollout still requires temporary compatibility protection, **When** the query path is cut over, **Then** any dual-read or staged fallback behavior is explicit and bounded rather than an indefinite hidden dependency on legacy in-row columns.

---

### Edge Cases

- One job may need more than one persisted embedding over time because model name, provider normalization, dimension, or target revision changes.
- Existing rows may have partial legacy state such as `embedding_model` set while `embedding` is null, or vice versa.
- A job's description or normalized content may change after an embedding is generated; the redesign must define how staleness is detected without guessing.
- The active recall target may be changed in configuration while only part of the corpus has been backfilled for that target.
- Matching request embeddings remain request-scoped and may use the same provider/model as job embeddings, but this feature must not introduce persistence requirements for user-side vectors.
- The repo may later add more than one job-side embedding purpose, such as JD-only versus another structured retrieval target; the redesign should not make that future extension impossible.
- Backfill may be interrupted halfway through a large corpus and resumed later; reruns must stay deterministic.
- Stored vectors and request vectors must not be compared across mismatched dimensions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST introduce a dedicated persisted job-embedding store linked to `job`, rather than treating the `job` row as the long-term storage location for vectors.
- **FR-002**: The persisted job-embedding record MUST capture enough metadata to isolate one representation from another, including at least the owning job, model identity, vector dimension, embedding value, and update timestamp.
- **FR-003**: The persisted job-embedding record MUST track the content state or equivalent version basis that the vector was derived from, such as `content_fingerprint` or an equivalent deterministic content revision marker.
- **FR-004**: The redesign MUST support model/version isolation so one job can retain more than one persisted embedding representation without destructive overwrite.
- **FR-005**: The system MUST define one explicit active embedding-selection rule for vector recall, based on configured target metadata rather than "whatever vector is currently on the job row".
- **FR-006**: New embedding generation and refresh flows MUST write to the dedicated embedding store for the active target.
- **FR-007**: The rollout MUST provide a safe path for historical jobs, including migration of legacy in-row vectors when usable and generation of new vectors when migration alone is insufficient.
- **FR-008**: The migration/backfill flow MUST be safe to rerun and MUST NOT create duplicate active records for unchanged job-content and target state.
- **FR-009**: The system MUST define how stale embeddings are detected after job content changes, and MUST allow those stale records to be refreshed without corrupting other target representations.
- **FR-010**: Matching recall MUST query through the dedicated embedding store instead of directly depending on `job.embedding`.
- **FR-011**: Matching recall MUST use only the configured active embedding target and MUST NOT silently compare request vectors against mixed model or mixed-dimension job vectors.
- **FR-012**: Jobs lacking the configured active embedding record MAY be excluded from vector recall, but the behavior MUST be explicit and test-covered.
- **FR-013**: The rollout MAY use temporary dual-write or dual-read compatibility steps, but it MUST define a bounded cutover plan and MUST NOT leave the new design permanently dependent on legacy in-row embedding columns.
- **FR-014**: This feature MUST keep candidate/request embeddings request-scoped; it MUST NOT require persisting user embeddings.
- **FR-015**: This feature MUST NOT depend on completion of location v2 or v3 work. Country filtering and canonical location modeling remain separate tracks.
- **FR-016**: This feature MUST NOT redesign the broader retrieval policy beyond the storage cutover. Hard filters, cosine thresholding, deterministic rerank, and optional LLM rerank may remain unchanged unless storage cutover requires interface adjustments.
- **FR-017**: The system MUST add tests covering new-write persistence, historical migration/backfill, active-target selection, query cutover, and legacy-cutover safety.
- **FR-018**: The system SHOULD support a future extension to more than one job-side embedding purpose without forcing another storage redesign, whether through an explicit target field, embedding kind, or equivalent selection dimension.

### Key Entities *(include if feature involves data)*

- **Job**: The core job row that continues to own business identity, compatibility fields, descriptions, and structured metadata, but no longer serves as the long-term home for persisted vectors.
- **Job Embedding Record**: The persisted vector representation for one job under one embedding target. It includes the vector plus enough metadata to isolate model, dimension, and source-content state.
- **Active Embedding Target**: The configured retrieval-time selector that determines which stored job embedding representation matching should use.
- **Legacy In-Row Embedding State**: The current `job.embedding`, `job.embedding_model`, and `job.embedding_updated_at` fields that exist only as rollout compatibility until the redesign is complete.
- **Embedding Backfill/Migration Flow**: The operational path that either migrates legacy vectors or generates missing vectors into the new store for historical jobs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Automated tests show that embedding generation writes persisted job vectors to the dedicated store without requiring `job.embedding` as the primary storage location.
- **SC-002**: Automated tests show that the same job can retain isolated embedding representations for at least two distinct target configurations without destructive overwrite.
- **SC-003**: Historical migration/backfill can be rerun against unchanged inputs without duplicate active records or active-target drift.
- **SC-004**: Matching query tests confirm that vector recall no longer directly depends on `job.embedding` and instead selects the configured active representation from the dedicated store.
- **SC-005**: The feature can ship independently of location v2/v3 work, with no requirement to complete canonical location modeling before the embedding storage cutover.
