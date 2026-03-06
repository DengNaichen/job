# Feature Specification: Location Parsing

**Feature Branch**: `004-location-parsing`  
**Created**: 2026-03-06  
**Status**: Planned  
**Input**: The system needs normalized location parsing so ingestion, matching, and API consumers can use consistent country and workplace semantics from heterogeneous source location data.

## Summary

Normalizes heterogeneous source location data into a conservative, stable location representation that supports country-aware behavior without fabricating geography from ambiguous inputs. Clear single-country signals remain usable, workplace semantics remain independent from geography, and ambiguous, regional, or multi-country inputs remain unresolved rather than forced into a single-country interpretation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Conservative Country Interpretation (Priority: P1)

As a data quality owner, I need ambiguous or broad location text to be handled conservatively so country eligibility does not drift or become fabricated.

**Why this priority**: False country assignment creates high-impact recommendation and filtering errors that are harder to detect than missing country data.

**Independent Test**: Run a baseline set of ambiguous, multi-country, single-country, and low-confidence location strings and verify the normalized outcomes remain stable.

**Acceptance Scenarios**:

1. **Given** an ambiguous abbreviation or broad regional label, **When** normalization runs, **Then** no single canonical country is assigned.
2. **Given** remote scope text that clearly includes multiple countries or a broad region, **When** normalization runs, **Then** no single canonical country is assigned.
3. **Given** location text that clearly indicates exactly one country, **When** normalization runs, **Then** that country can be assigned without losing workplace semantics.
4. **Given** an unparseable or low-confidence location string, **When** normalization runs, **Then** the result remains unknown-safe rather than fabricated.

---

### User Story 2 - Compatible Source Location Normalization (Priority: P1)

As an ingestion owner, I need supported sources to emit compatible normalized location hints so downstream persistence and matching can consume them consistently without over-interpreting partial source data.

**Why this priority**: Source-level semantic drift creates silent inconsistencies in country eligibility and workplace interpretation.

**Independent Test**: Validate representative jobs from each supported source and confirm normalized location outputs preserve known fields, preserve workplace semantics when available, and leave unknown fields unset when source data is partial.

**Acceptance Scenarios**:

1. **Given** location metadata from a supported source, **When** normalization runs, **Then** outputs follow a shared normalized location-hint contract with compatible field semantics.
2. **Given** source metadata that clearly identifies workplace mode, **When** normalization runs, **Then** workplace semantics are preserved independently from country assignment.
3. **Given** source metadata that only partially identifies geography, **When** normalization runs, **Then** known location fields are preserved and unknown fields remain unset.
4. **Given** empty, null, or whitespace-only location metadata, **When** normalization runs, **Then** no fabricated normalized location is produced.

---

### User Story 3 - Stable Normalized Location Contracts (Priority: P2)

As a consumer of job and matching responses, I need normalized location payloads and country-aware filtering behavior to remain stable so location-aware integrations can rely on one contract.

**Why this priority**: Contract churn causes integration failures even when parsing behavior itself is correct.

**Independent Test**: Execute contract and behavior checks for job responses, matching responses, and country-aware filtering guards, and verify normalized location semantics remain stable.

**Acceptance Scenarios**:

1. **Given** job list and detail responses, **When** location data is returned, **Then** normalized location payloads remain available without legacy location fields.
2. **Given** matching recommendation responses, **When** normalized location payloads are returned, **Then** field presence and semantics remain compatible with consumers.
3. **Given** country-aware filtering guards, **When** normalized locations are used, **Then** filtering decisions remain consistent with conservative country assignment rules.

## Edge Cases

- Ambiguous abbreviations that can represent a state, province, region, or country.
- Remote scope strings listing multiple countries with separators such as `or`, `and`, commas, or slashes.
- Remote scope strings that indicate supranational or broad regions, such as EMEA, APAC, Europe, or North America.
- Inputs that combine workplace semantics with noisy punctuation or mixed casing.
- City-only strings that may correspond to more than one country or region.
- Source records with workplace signals but incomplete geographic detail.
- Empty, null, or whitespace-only location strings.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST interpret known location parsing scenarios using conservative country assignment rules.
- **FR-002**: The system MUST NOT fabricate a single-country result for ambiguous, broad-region, multi-country, or low-confidence location input.
- **FR-003**: The system MUST allow a canonical country assignment when the input clearly indicates exactly one country.
- **FR-004**: The system MUST preserve workplace semantics independently from country assignment whenever workplace signals are available.
- **FR-005**: The system MUST normalize supported source inputs into a shared location-hint contract with compatible field semantics and unknown-safe defaults.
- **FR-006**: The system MUST preserve known structured location fields without requiring every source to provide every field.
- **FR-007**: The system MUST keep downstream job and matching location payload contracts stable without consumer-facing schema churn.
- **FR-008**: The system MUST keep country-aware filtering behavior aligned with normalized country assignments.
- **FR-009**: The system MUST provide automated regression coverage for parser behavior, source normalization behavior, and downstream contract and behavior guardrails.
- **FR-010**: The system MUST validate behavior against an agreed baseline scenario set before release.

### Key Entities *(include if feature involves data)*

- **Raw Location Input**: Original location text and workplace hints coming from source data.
- **Normalized Location Hint**: Standardized per-job location representation containing known geography, workplace semantics, and optional scope details.
- **Canonical Country Assignment**: Conservatively derived single-country eligibility used only when the signal is sufficiently clear.
- **Normalized Location Payload**: Downstream location representation consumed by job APIs, matching responses, and location-aware filtering.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of agreed baseline location parsing scenarios produce the expected normalized outcomes.
- **SC-002**: 0 known ambiguous, broad-region, or multi-country test scenarios produce a fabricated single-country assignment.
- **SC-003**: 100% of validated source-ingestion location samples emit compatible normalized location hints with unknown-safe handling for missing fields.
- **SC-004**: 100% of normalized location contract and behavior guardrail tests pass without consumer-facing schema changes.
