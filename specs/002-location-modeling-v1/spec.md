# Feature Specification: Job Location Modeling V1

**Feature Branch**: `002-location-modeling-v1`  
**Created**: 2026-03-01  
**Status**: Draft  
**Input**: User description: "Create a v1 spec for structured job location modeling while keeping location_text for compatibility"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Persist Filterable Location Structure on `job` (Priority: P1)

As a backend engineer working on hybrid retrieval, I need each job row to carry a best-effort structured location profile in addition to `location_text` so future location filtering and ranking do not depend on reparsing arbitrary display strings at query time.

**Why this priority**: The roadmap already calls for location-aware structured filters in retrieval. That work remains fragile until location data is represented as first-class columns rather than only a free-text string.

**Independent Test**: Ingest a representative set of source payloads and verify that the job row preserves `location_text` while also persisting structured location fields when the upstream payload contains explicit location structure.

**Acceptance Scenarios**:

1. **Given** a source payload with explicit `city`, `region`, or `country` fields, **When** the mapper ingests the job, **Then** the job row stores those values in structured location columns and still keeps `location_text` as the display-compatible text.
2. **Given** a source payload with an explicit remote or hybrid signal, **When** the mapper ingests the job, **Then** the job row stores `location_workplace_type` separately from `employment_type`.
3. **Given** a source payload that contains only ambiguous free-text location data, **When** the mapper ingests the job, **Then** the system keeps `location_text` and leaves uncertain structured fields null or `unknown` instead of fabricating geography.

---

### User Story 2 - Backfill Existing Jobs Safely (Priority: P2)

As an operator rolling out the schema change, I need existing jobs to be backfilled from stored payloads and current location text so the feature improves historical data coverage without risking destructive guesses or data loss.

**Why this priority**: If only newly ingested jobs receive structured location fields, retrieval behavior and analytics will be inconsistent across the corpus for an extended period.

**Independent Test**: Run the backfill against a test dataset containing both structured-source jobs and ambiguous free-text jobs, then verify that the script populates safe fields, preserves `location_text`, and can be rerun without creating drift.

**Acceptance Scenarios**:

1. **Given** an existing job whose `raw_payload` still contains structured location data, **When** the backfill runs, **Then** it populates the structured location columns without changing the job's identity or compatibility fields.
2. **Given** an existing job with ambiguous text such as `Remote - North to South America`, **When** the backfill runs, **Then** it may classify the workplace as remote and preserve remote-scope text, but it must not invent a precise city, region, or country code.
3. **Given** a job that already has populated structured location fields, **When** the backfill is rerun, **Then** a lower-confidence parse must not overwrite higher-confidence existing values.

---

### User Story 3 - Defer Full Multi-Location Normalization (Priority: P3)

As an engineer managing schema complexity, I need v1 to stop at job-level structured columns so location-aware retrieval can ship before introducing canonical `locations` and `job_locations` tables.

**Why this priority**: Some sources expose multiple locations and some only expose text, but that does not justify taking on canonical location reuse, many-to-many modeling, and cross-source normalization in the same feature.

**Independent Test**: Verify that the schema change and ingest pipeline can support retrieval-facing structured location fields without requiring a location dimension table or a breaking API change.

**Acceptance Scenarios**:

1. **Given** a source that exposes multiple possible locations for one job, **When** v1 persists the record, **Then** it stores one deterministic primary representation on `job` and relies on `raw_payload` for any richer future normalization.
2. **Given** existing API consumers reading job payloads, **When** v1 ships, **Then** `location_text` remains available and no same-day migration is required.
3. **Given** a future need for `locations + job_locations`, **When** that work is taken on later, **Then** the v1 columns can be treated as a staging layer rather than a dead-end redesign.

---

### Edge Cases

- Some sources provide fully structured geography (`city`, `region`, `country`) while others provide only free text such as `Remote`, `Canada`, or `Remote - North to South America`.
- Some sources expose multiple locations for one posting; v1 must choose one representative location deterministically instead of modeling all locations immediately.
- `remote`, `hybrid`, and `onsite` are workplace-mode concepts, not synonyms for geography; they must not be overloaded into `employment_type`.
- A job may be remote but still carry a hiring-scope restriction such as a country or region; v1 should preserve scope text without pretending it is canonical geography.
- Existing rows may have missing or truncated `raw_payload`, making exact backfill impossible for some sources.
- Region values may arrive as abbreviations (`CA`, `ON`) or full names (`California`, `Ontario`); v1 should not promise aggressive canonicalization.
- Country names may not always map cleanly to ISO codes; when mapping is uncertain, the system should preserve display text and leave `location_country_code` null.
- Some source payloads put location hints in fields that are currently misclassified, such as Eightfold `workLocationOption`; v1 must explicitly separate those semantics.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST add nullable structured location columns to `job` while keeping the existing `location_text` column for compatibility and display.
- **FR-002**: V1 structured columns on `job` MUST include at least `location_city`, `location_region`, `location_country_code`, `location_workplace_type`, and `location_remote_scope`.
- **FR-003**: `location_workplace_type` MUST use explicit enum semantics and support at least `unknown`, `onsite`, `hybrid`, and `remote`.
- **FR-004**: System MUST treat `location_text` as compatibility/display text, not as the authoritative field for location filtering once structured columns are populated.
- **FR-005**: Ingest mappers MUST populate structured location columns directly from source-native structured payload fields when those fields are explicit and unambiguous.
- **FR-006**: Ingest mappers MAY use conservative parsing of text-based location fields for well-known patterns, but MUST leave ambiguous structured fields null or `unknown` rather than guessing.
- **FR-007**: System MUST separate workplace-mode extraction from `employment_type`; fields such as Eightfold `workLocationOption` must no longer be modeled as employment type.
- **FR-008**: System MUST define a deterministic primary-location rule for v1 so every job stores at most one structured location profile on the main row.
- **FR-009**: System MUST provide a backfill path for existing jobs using `raw_payload` first and `location_text` second, with preference for higher-confidence source-native structure over inferred parsing.
- **FR-010**: The backfill process MUST be idempotent and safe to rerun.
- **FR-011**: The backfill process MUST NOT overwrite existing populated structured fields with lower-confidence inferred values.
- **FR-012**: Read schemas MAY add the new structured fields, but MUST continue exposing `location_text` during the v1 rollout.
- **FR-013**: Internal query/read paths needed for future hybrid retrieval MUST be able to consume structured location columns without reparsing `location_text`.
- **FR-014**: System MUST add tests covering mapper behavior, schema serialization, and backfill behavior for both structured-source and ambiguous free-text cases.
- **FR-015**: This feature MUST NOT introduce canonical `locations` or `job_locations` tables.
- **FR-016**: This feature MUST NOT require geocoding, third-party location enrichment, or LLM-based location parsing in the hot ingest path.

### Key Entities *(include if feature involves data)*

- **Job**: The primary persisted job row. In v1 it remains the storage location for both compatibility text (`location_text`) and the new structured location fields.
- **Structured Job Location**: The best-effort, single-location profile stored directly on `job`, composed of city, region, country code, workplace type, and remote-scope text.
- **Legacy Location Text**: The existing `location_text` field. It remains the API-safe display field and fallback text when structured parsing is incomplete.
- **Workplace Type**: The normalized classification of how work is performed, independent of geography. V1 supports `unknown`, `onsite`, `hybrid`, and `remote`.
- **Remote Scope**: A free-text description of where remote eligibility applies, such as `Canada`, `North America`, or `North to South America`, when the source expresses that constraint but not canonical geography.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Source fixtures that already expose structured location subfields populate the new `job` location columns correctly in automated mapper tests.
- **SC-002**: Ambiguous free-text fixtures preserve `location_text` and do not produce fabricated city, region, or country-code values in automated tests.
- **SC-003**: The backfill job can be rerun against the same dataset without introducing value drift or downgrading previously populated high-confidence structured fields.
- **SC-004**: The repo has a documented, test-backed path for future location-aware retrieval work to use structured location columns instead of reparsing `location_text`.
- **SC-005**: Existing read paths continue to expose `location_text`, so v1 does not force a same-day client migration.
