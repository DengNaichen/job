# Feature Specification: Location Filtering (Hard Cutover)

**Feature Branch**: `006-location-filtering`  
**Created**: 2026-03-05  
**Status**: Planned  
**Input**: Product direction requires a hard API cutover from legacy flattened location fields to normalized location payloads.

## Summary

The system supports location-aware recommendations by allowing callers to provide a preferred country. This behavior remains unchanged.

This feature introduces a **breaking API contract cutover**:

- Jobs API removes `location_text` from read responses and removes legacy location write fields.
- Matching API removes flattened location output fields and returns normalized `locations` payloads only.

No compatibility fallback is preserved at the API contract layer.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Country-Scoped Matching Recommendations (Priority: P1)

As a candidate or downstream recommender client, I want to provide a preferred country so recommendation results prioritize roles available in that country.

**Why this priority**: Country preference is the most direct location signal exposed to matching callers and has immediate relevance to recommendation quality.

**Independent Test**: Submit recommendation requests with and without `preferredCountryCode`, and verify country-scoped requests only return jobs linked to that country while using normalized location result payloads.

**Acceptance Scenarios**:

1. **Given** a recommendation request with `preferredCountryCode=US`, **When** matching runs, **Then** only jobs linked to US eligibility are considered in SQL prefiltering.
2. **Given** a recommendation request without a preferred country, **When** matching runs, **Then** no country prefilter is applied and global candidate recall behavior remains unchanged.
3. **Given** a valid preferred country code, **When** response metadata is returned, **Then** the prefilter summary includes that preferred country value.
4. **Given** any matching response item, **When** location data is returned, **Then** it includes normalized `locations` and excludes legacy flattened fields.

---

### User Story 2 - Stable Location Semantics for Ambiguous Inputs (Priority: P2)

As a user receiving recommendations, I need ambiguous or multi-country location strings to be handled conservatively so the system avoids false country matches.

**Why this priority**: Incorrect country inference causes highly visible recommendation quality errors and undermines trust more than returning fewer results.

**Independent Test**: Validate parsing behavior on ambiguous and multi-country strings (for example, state abbreviations and regional scopes) and confirm no fabricated single-country result is produced.

**Acceptance Scenarios**:

1. **Given** ambiguous location text, **When** location normalization runs, **Then** the system does not force a single-country interpretation.
2. **Given** remote scopes that clearly contain multiple countries, **When** location normalization runs, **Then** no single canonical country is assigned.
3. **Given** explicit single-country remote scopes, **When** location normalization runs, **Then** the country can be assigned while remote semantics remain preserved.

---

### User Story 3 - Hard Cutover for Jobs API Location Contract (Priority: P3)

As an API consumer, I need a stable normalized jobs location contract so downstream systems can rely on one canonical response/write shape.

**Why this priority**: Mixed compatibility contracts increase integration drift and maintenance cost.

**Independent Test**: Call job create/update/read endpoints and verify legacy location write/read fields are rejected or absent while normalized location structures remain available.

**Acceptance Scenarios**:

1. **Given** job read endpoints, **When** location data is returned, **Then** normalized `locations` are included and `location_text` is absent.
2. **Given** job create/update payloads, **When** legacy location write fields are provided, **Then** those fields are not part of the published contract and are not accepted as first-class API inputs.

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
- **FR-008**: The Jobs API MUST remove `location_text` from read responses and legacy location write fields from public create/update contracts.
- **FR-009**: The Matching API MUST remove flattened location fields (`location_text`, `city`, `region`, `country_code`, `workplace_type`) and return normalized `locations` only.
- **FR-010**: The system MUST include automated schema, integration, and behavior coverage for the hard-cut contracts and country/ambiguity behavior.

### Key Entities *(include if feature involves data)*

- **Recommendation Request**: Caller-provided candidate and preference payload used to generate ranked job results.
- **Preferred Country**: Optional country preference used to scope candidate retrieval.
- **Normalized Job Location Link**: Canonical job-to-location relationship used to evaluate country eligibility.
- **Normalized Match Location Item**: Matching response location structure derived from canonical location links.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Country-prefilter behavior is validated in automated matching tests for both with-country and without-country requests.
- **SC-002**: Ambiguous and multi-country parsing cases are covered by automated tests and do not produce fabricated single-country assignments.
- **SC-003**: Jobs API tests confirm `location_text` is absent and normalized `locations` are present in read responses.
- **SC-004**: Matching API tests confirm flattened location fields are absent and normalized `locations` are present.
- **SC-005**: SQL prefilter summary consistently reports whether a preferred country filter was applied.
