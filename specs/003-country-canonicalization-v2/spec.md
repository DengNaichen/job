# Feature Specification: Job Country Canonicalization V2

**Feature Branch**: `003-country-canonicalization-v2`  
**Created**: 2026-03-01  
**Status**: Draft  
**Input**: User description: "Create a follow-up v2 spec that makes country filtering reliable through canonical country normalization, while keeping full location normalization and split tables out of scope"

## Summary

V1 introduces best-effort structured location fields directly on `job`, including `location_country_code`, but it intentionally stops short of broader canonical location modeling.

This v2 feature narrows the next step to one specific outcome: make country-level filtering reliable by normalizing high-confidence country inputs into a canonical country code on the existing `job.location_country_code` field.

`job.location_country_code` remains a single-value field in v2. For onsite and hybrid jobs, it represents the canonical country of the primary physical location. For remote jobs, it may represent explicit single-country work eligibility rather than a physical office location. If a job clearly spans multiple countries, v2 keeps the field null instead of forcing a lossy primary-country choice.

This feature explicitly does **not** introduce `locations` or `job_locations`, does **not** require PostGIS, and does **not** attempt full city/region canonicalization. Those remain future work after country filtering proves valuable enough to justify more schema complexity.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Normalize Country Codes For New And Updated Jobs (Priority: P1)

As a backend engineer building country-aware filters, I need `job.location_country_code` to hold a canonical country value for high-confidence cases so retrieval and filtering can rely on one stable field instead of reparsing inconsistent source strings.

**Why this priority**: Country filtering is materially simpler than full location normalization and can unlock useful retrieval constraints without taking on split tables or spatial modeling.

**Independent Test**: Ingest representative fixtures containing structured country fields, full country names inside location text, single-country remote scopes, and ambiguous abbreviations, then verify that canonical country codes are populated only when confidence is high.

**Acceptance Scenarios**:

1. **Given** a source payload with an explicit country field such as `Canada` or `United States`, **When** the mapper or shared helper normalizes the job, **Then** `location_country_code` is stored as a canonical ISO-style country code and the existing compatibility fields remain intact.
2. **Given** a source payload with text such as `Toronto, ON, Canada`, **When** the system applies conservative normalization, **Then** it stores the canonical country code for Canada without requiring a separate canonical location table.
3. **Given** a source payload with ambiguous text such as `San Francisco, CA`, **When** the system evaluates country normalization, **Then** it must not infer `CA` as Canada from the region abbreviation alone.
4. **Given** a remote job whose scope is explicitly one country such as `Remote - Canada`, **When** normalization runs, **Then** it may store the canonical country code for Canada while preserving remote semantics separately from geography.
5. **Given** a remote job whose scope names multiple countries such as `Remote - US or Canada`, **When** normalization runs, **Then** `location_country_code` remains null and the multi-country scope is preserved in the existing remote-scope or compatibility fields.

---

### User Story 2 - Repair Historical Country Codes Safely (Priority: P2)

As an operator rolling forward from v1, I need historical jobs to gain canonical country codes where confidence is high so country filtering behaves consistently across old and new rows without destructive rewrites.

**Why this priority**: If normalization applies only to newly ingested jobs, country filters will remain inconsistent across the corpus for too long to be operationally useful.

**Independent Test**: Run the country normalization backfill against a mixed-confidence dataset and verify that it upgrades null or weak country values safely, leaves ambiguous rows untouched, and can be rerun without oscillation.

**Acceptance Scenarios**:

1. **Given** an existing job with `location_country_code` unset but a source-native country value in `raw_payload`, **When** the backfill runs, **Then** the job is upgraded to the canonical country code without changing identity or compatibility fields.
2. **Given** an existing job with ambiguous multi-country or supranational scope such as `Remote - US or Canada` or `EMEA`, **When** the backfill runs, **Then** the system leaves `location_country_code` null rather than collapsing the job to one fabricated country.
3. **Given** an existing job with a populated high-confidence country code, **When** normalization is rerun, **Then** a lower-confidence parse must not overwrite the existing value.

---

### User Story 3 - Defer Full Canonical Location Modeling (Priority: P3)

As an engineer managing rollout scope, I need country canonicalization to stay on the existing `job` row so the team can ship country-aware filtering before committing to canonical location entities, many-to-many modeling, or spatial infrastructure.

**Why this priority**: Country filtering is the immediate product need. Full location reuse, multi-location jobs, and spatial querying remain optional until later evidence justifies the added complexity.

**Independent Test**: Verify that country-aware query paths can rely on `location_country_code` after normalization without requiring `locations + job_locations`, geocoding, or PostGIS.

**Acceptance Scenarios**:

1. **Given** v2 country normalization is complete, **When** a query filters by one country code, **Then** it can use `job.location_country_code` directly without reparsing `location_text`.
2. **Given** a future need for canonical location entities, **When** that work is taken on later, **Then** the v2 canonical country code remains a useful staging field rather than a dead-end schema choice.
3. **Given** the repo has not yet justified distance or radius queries, **When** v2 ships, **Then** it must not require PostGIS or other spatial infrastructure to be considered complete.

---

### Edge Cases

- Country expressions may arrive as names, codes, mixed-case strings, or source-specific labels such as `United States`, `USA`, `US`, `United Kingdom`, `UK`, or `UAE`.
- Some short codes are ambiguous outside a known country field. For example, `CA` may mean Canada or California depending on context.
- Some remote scopes express more than one country, such as `US or Canada`, and must not be collapsed into one canonical country code.
- Some remote scopes express a region rather than a country, such as `EMEA`, `APAC`, `Europe`, or `North America`.
- Some postings expose multiple locations across different countries; v2 still stores at most one canonical country on `job` and must leave the field null if no single primary country is safely derivable.
- Existing v1 rows may already contain low-confidence or inconsistent country codes that need conservative repair rules.
- Country normalization must respect workplace semantics: `remote`, `hybrid`, and `onsite` remain separate from country identity.
- The canonical code format may differ from common business shorthand. For example, ISO-style normalization may require `GB` instead of `UK`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST treat `job.location_country_code` as the single canonical country filter field introduced in v1.
- **FR-002**: The system MUST normalize high-confidence country values into a canonical uppercase country code format, such as ISO 3166-1 alpha-2.
- **FR-003**: The system MUST prioritize explicit source-native country fields over inferred parsing from free text.
- **FR-004**: The system MUST centralize country normalization rules in shared logic so ingest, repair scripts, and read-oriented workflows apply the same mappings.
- **FR-005**: The system MAY infer country from text only when the text identifies exactly one unambiguous country with high confidence.
- **FR-006**: The system MUST NOT infer a canonical country code from ambiguous region or state abbreviations alone.
- **FR-007**: For onsite and hybrid jobs, `location_country_code` MUST represent the canonical country of the primary physical job location when that country is known with high confidence.
- **FR-008**: When a remote scope explicitly names exactly one country, the system MAY populate `location_country_code` while preserving `location_workplace_type` and `location_remote_scope`.
- **FR-009**: When a location or remote scope names multiple countries or only a supranational region, the system MUST leave `location_country_code` null unless a deterministic primary country is already explicit in source-native structure.
- **FR-010**: The system MUST NOT reinterpret a multi-country remote scope as a single-country canonical value merely to satisfy filtering convenience.
- **FR-011**: The system MUST provide a rerunnable normalization/backfill path for existing jobs whose country code is null, invalid, or lower-confidence than the newly available normalization result.
- **FR-012**: The normalization/backfill path MUST NOT overwrite an existing high-confidence country code with a lower-confidence inferred value.
- **FR-013**: The system MUST preserve `location_text`, `location_city`, `location_region`, `location_workplace_type`, and `location_remote_scope` during normalization.
- **FR-014**: The system MUST add tests covering positive mappings, ambiguous abbreviations, remote single-country scope, remote multi-country scope, and rerunnable repair behavior.
- **FR-015**: Read/query paths needed for country-aware filtering MUST be able to rely on `location_country_code` without reparsing `location_text`.
- **FR-016**: This feature MUST NOT introduce canonical `locations` or `job_locations` tables.
- **FR-017**: This feature MUST NOT require PostGIS, geocoding, third-party enrichment, or polygon/point spatial queries.
- **FR-018**: This feature MUST NOT promise full city or region canonicalization; city and region remain best-effort supporting fields in this phase.

### Key Entities *(include if feature involves data)*

- **Job**: The persisted job row created by v1. In v2 it continues to store compatibility text and structured location fields directly on the main row.
- **Canonical Country Code**: The normalized single-country identifier stored in `job.location_country_code` and intended for stable country-aware filtering. For remote jobs it may reflect explicit single-country eligibility rather than a physical office location.
- **Country Normalization Rule**: Shared logic that maps explicit source-native country values and approved high-confidence text patterns to canonical country codes.
- **Remote Scope**: Free-text scope restrictions such as `Canada`, `US or Canada`, or `EMEA` that may inform but do not automatically determine the canonical country code.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Automated ingest tests show that explicit or high-confidence country inputs normalize to the expected canonical country codes.
- **SC-002**: Automated ambiguity tests show that region/state abbreviations and multi-country scopes do not produce fabricated canonical country codes.
- **SC-003**: The country normalization backfill can be rerun against the same dataset without value oscillation or confidence downgrades.
- **SC-004**: Country-aware query paths can filter on `location_country_code` without reparsing `location_text`.
- **SC-005**: The repo has a documented path from v1 structured location fields to v2 canonical country normalization without introducing split tables or spatial infrastructure.

## Implementation Notes *(non-mandatory)*

- A pragmatic OSS baseline for v2 is `pycountry` as the source of ISO country metadata plus a repo-local alias/guard layer for business-specific normalization rules.
- The repo-local alias/guard layer should remain authoritative for ambiguous or product-specific behavior, such as accepting `UK` as input while storing `GB`, or refusing to interpret `CA` as Canada when the surrounding context indicates a US state abbreviation.
- The normalization pipeline should treat OSS metadata as a reference source, not as a complete policy engine. Remote-scope semantics, multi-country handling, and confidence guards remain application logic owned by this repo.
- Heavy address-parsing or geocoding-oriented tools such as `libpostal` are intentionally a poor fit for this v2 scope because the main problem is country filtering semantics on job postings, not free-form street address understanding.
