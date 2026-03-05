# Feature Specification: Location Filtering

**Feature Branch**: `006-location-filtering`  
**Created**: 2026-03-05  
**Status**: Planned  
**Input**: Matching recommendations need country-scoped prefiltering using normalized location data, and location parsing must handle ambiguous inputs conservatively.

## Summary

Adds optional country-scoped prefiltering to the matching recommendation pipeline and hardens location parsing to avoid false country assignments on ambiguous or multi-country inputs.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Country-Scoped Matching Recommendations (Priority: P1)

As a candidate or downstream recommender client, I want to provide a preferred country so recommendation results prioritize roles available in that country.

**Why this priority**: Country preference is the most direct location signal exposed to matching callers and has immediate relevance to recommendation quality.

**Independent Test**: Submit recommendation requests with and without `preferredCountryCode`, and verify country-scoped requests only return jobs linked to that country while using normalized location result payloads.

**Acceptance Scenarios**:

1. **Given** a recommendation request with `preferredCountryCode=US`, **When** matching runs, **Then** only jobs linked to US eligibility are considered in SQL prefiltering.
2. **Given** a recommendation request without a preferred country, **When** matching runs, **Then** no country prefilter is applied and global candidate recall behavior remains unchanged.
3. **Given** a valid preferred country code, **When** response metadata is returned, **Then** the prefilter summary includes that preferred country value.

---

### User Story 2 - Stable Location Semantics for Ambiguous Inputs (Priority: P2)

As a user receiving recommendations, I need ambiguous or multi-country location strings to be handled conservatively so the system avoids false country matches.

**Why this priority**: Incorrect country inference causes highly visible recommendation quality errors and undermines trust more than returning fewer results.

**Independent Test**: Validate parsing behavior on ambiguous and multi-country strings (for example, state abbreviations and regional scopes) and confirm no fabricated single-country result is produced.

**Acceptance Scenarios**:

1. **Given** ambiguous location text, **When** location normalization runs, **Then** the system does not force a single-country interpretation.
2. **Given** remote scopes that clearly contain multiple countries, **When** location normalization runs, **Then** no single canonical country is assigned.
3. **Given** explicit single-country remote scopes, **When** location normalization runs, **Then** the country can be assigned while remote semantics remain preserved.

## Edge Cases

- Location input contains ambiguous abbreviations that can represent either a region or a country.
- Remote scope contains multiple countries (for example, "US or Canada").
- Remote scope references a supranational region (for example, "EMEA", "APAC").
- Jobs have multiple linked locations and matching output must preserve ordering/primary semantics in normalized location payloads.
- Preferred country is omitted and behavior must remain functionally unchanged.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept an optional preferred country in recommendation requests.
- **FR-002**: The system MUST apply country prefiltering only when a preferred country is provided.
- **FR-003**: The system MUST use normalized job-location links for country prefiltering decisions.
- **FR-004**: The system MUST preserve existing recommendation behavior when no preferred country is provided.
- **FR-005**: The system MUST expose prefilter metadata so consumers can verify whether country filtering was applied.
- **FR-006**: The system MUST handle ambiguous and multi-country location strings conservatively and avoid fabricated single-country assignments.
- **FR-007**: The system MUST preserve remote/onsite/hybrid semantics independently from country selection.
- **FR-008**: The system MUST include automated behavior coverage for country prefiltering and ambiguity handling.

### Key Entities *(include if feature involves data)*

- **Recommendation Request**: Caller-provided candidate and preference payload used to generate ranked job results.
- **Preferred Country**: Optional country preference used to scope candidate retrieval.
- **Normalized Job Location Link**: Canonical job-to-location relationship used to evaluate country eligibility.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Country-prefilter behavior is validated in automated matching tests for both with-country and without-country requests.
- **SC-002**: Ambiguous and multi-country parsing cases are covered by automated tests and do not produce fabricated single-country assignments.
- **SC-003**: SQL prefilter summary consistently reports whether a preferred country filter was applied.
