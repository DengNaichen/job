# Feature Specification: Canonical Locations V3

**Feature Branch**: `004-canonical-locations-v3`  
**Created**: 2026-03-01  
**Status**: Draft  
**Input**: User description: "Create a v3 spec that introduces canonical location entities and split tables after v1 structured location fields and v2 canonical country normalization"

## Summary

V1 keeps structured location fields directly on `job` so filtering can improve quickly without broad schema churn. V2 makes country-level filtering more reliable by canonicalizing `job.location_country_code` for high-confidence cases.

This v3 feature is the step that actually normalizes location storage: introduce canonical location entities plus a many-to-many job link so the system can represent reusable locations, multi-location jobs, and richer location-aware retrieval without depending on one denormalized location profile per job.

V3 still preserves the existing job-level location fields during rollout. Those fields become compatibility and staging state, and may also remain as denormalized query helpers while the normalized model proves itself.

This feature explicitly does **not** require PostGIS, radius search, distance ranking, or other spatial query infrastructure. It is about normalized entities and relationship modeling, not geometry.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Persist Reusable Canonical Locations For New Jobs (Priority: P1)

As a backend engineer working on richer location-aware retrieval, I need locations to be stored as reusable canonical entities linked to jobs so that the system can represent more than one location per job and avoid duplicating the same place description across many rows.

**Why this priority**: This is the first phase where multi-location jobs and canonical reuse become first-class data model features instead of being squeezed into one `job` row.

**Independent Test**: Ingest representative fixtures containing single-location jobs, multi-location jobs, country-only jobs, and remote-scope jobs, then verify that the pipeline creates canonical `locations`, links them through `job_locations`, and still maintains compatibility fields on `job`.

**Acceptance Scenarios**:

1. **Given** two jobs that refer to the same canonical place, **When** they are ingested, **Then** they reuse one `locations` row rather than storing duplicate location entities for the same normalized identity.
2. **Given** a source payload that exposes multiple supported job locations, **When** the mapper persists the job, **Then** the system creates multiple `job_locations` links and marks exactly one link as primary using a deterministic rule.
3. **Given** a source payload that exposes only one clear location, **When** the job is ingested, **Then** the system creates one canonical location link and keeps the job-level compatibility fields aligned with that primary location.
4. **Given** a remote job with explicit country-level eligibility such as `US or Canada`, **When** the system can derive multiple country-level canonical targets with high confidence, **Then** it may attach more than one linked location instead of forcing one lossy country choice on the job row.

---

### User Story 2 - Backfill Historical Jobs Into Canonical Location Entities Safely (Priority: P2)

As an operator rolling forward from v1 and v2, I need historical jobs to be linked to canonical locations so the dataset becomes consistent without requiring a same-day full reimport.

**Why this priority**: Without a historical backfill, normalized location tables would only be useful for newly ingested rows and retrieval behavior would remain inconsistent for too long.

**Independent Test**: Run the canonical-location backfill against historical rows with mixed confidence and verify that it creates reusable location rows, preserves deterministic primary links, and is safe to rerun without duplicate entity drift.

**Acceptance Scenarios**:

1. **Given** an existing job with a high-confidence structured location profile on `job`, **When** the backfill runs, **Then** it creates or reuses the expected canonical `locations` row and links the job without changing the job's identity.
2. **Given** an existing job whose `raw_payload` reveals more than one location but v1 stored only one primary location on the job row, **When** the backfill runs, **Then** the normalized model may restore the additional supported locations when confidence is sufficient.
3. **Given** a rerun of the backfill on the same dataset, **When** canonicalization rules and source inputs have not changed, **Then** the process must not create duplicate location rows or duplicate job-location links.

---

### User Story 3 - Query Through Normalized Locations While Preserving Compatibility (Priority: P3)

As an engineer evolving retrieval and APIs, I need read and query paths to consume canonical locations so that future matching and filtering can reason about multi-location jobs without reparsing `location_text` or depending forever on denormalized columns.

**Why this priority**: The point of split tables is not just storage purity. It is to unlock query behavior that the single-row model cannot represent cleanly.

**Independent Test**: Verify that read/query paths can retrieve canonical location sets and primary locations from normalized tables while existing compatibility fields on `job` remain available during the migration period.

**Acceptance Scenarios**:

1. **Given** a normalized multi-location job, **When** a read path fetches it, **Then** the system can expose both the primary location summary and the full linked location set without reparsing `location_text`.
2. **Given** country-aware retrieval filters, **When** they run against normalized tables, **Then** they can match jobs through linked canonical locations rather than depending only on the one primary country stored on `job`.
3. **Given** existing API consumers that still expect the job-level compatibility fields, **When** v3 ships, **Then** those fields remain available during rollout even though normalized tables become the authoritative long-term model.

---

### Edge Cases

- A source may expose multiple cities within one country, multiple countries, or a mixture of country-level and city-level locations for one job.
- Two sources may express the same place differently, such as `Toronto, ON, Canada` versus `Toronto, Ontario, CA`, and v3 must define a canonical reuse strategy.
- Some jobs expose only a country or region and no city; canonical location entities must support partial geography rather than assuming every record resolves to city-level precision.
- Some jobs are remote with one eligible country, while others are remote across multiple countries or broad regions such as `EMEA`; the normalized model must support both without collapsing them into one fabricated place.
- Some jobs may have both a physical office location and a remote-eligibility scope; v3 must define whether those are represented as separate linked location entities, or through an equivalent explicit split in the normalized model.
- Source payloads may not identify a clear primary location even when they expose multiple options; the rollout still requires one deterministic primary link for compatibility behavior.
- Historical jobs may already contain denormalized `location_*` fields from v1/v2 that disagree with newly derived canonical entities; backfill rules must define which source of truth wins.
- Canonicalization quality may improve over time. The system must avoid duplicate location entities caused by normalization rule changes or formatting-only differences.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST introduce a canonical `locations` entity store and a `job_locations` association so one job can be linked to many locations and one location can be reused by many jobs.
- **FR-002**: The normalized model MUST support at least country, region, city, and remote-scope style location information without requiring full address precision.
- **FR-003**: The normalized model MUST explicitly distinguish physical locations from remote-eligibility scopes, either through a typed field such as `location_kind` or an equivalent explicit representation.
- **FR-004**: The system MUST define deterministic canonicalization rules so equivalent source representations reuse the same canonical location entity.
- **FR-005**: The system MUST define deterministic primary-location selection so every job with linked locations has at most one primary link used for compatibility and summary behavior.
- **FR-006**: The ingest pipeline MUST create or reuse canonical location entities for newly ingested jobs and persist the required `job_locations` links.
- **FR-007**: The ingest pipeline MUST support jobs with more than one linked canonical location when source confidence is sufficient.
- **FR-008**: The system MUST preserve the existing job-level location fields during rollout and MUST keep them aligned with the authoritative primary linked location or equivalent compatibility rule.
- **FR-009**: The system MUST provide a rerunnable backfill path that creates canonical locations and job-location links for historical jobs using v1/v2 structured fields first and `raw_payload` second.
- **FR-010**: The backfill path MUST NOT create duplicate canonical locations or duplicate job-location links when rerun against unchanged inputs.
- **FR-011**: The system MUST allow country-aware filters and future location-aware retrieval paths to query against normalized location links instead of reparsing `location_text`.
- **FR-012**: The system MAY continue to use denormalized job-level location fields as query helpers during rollout, but the normalized location entities MUST become the long-term authoritative model for reusable location identity.
- **FR-013**: The system MUST add tests covering canonical reuse, primary-link selection, multi-location jobs, historical backfill, and compatibility serialization.
- **FR-014**: The system MUST preserve separation between workplace semantics and employment semantics; no location normalization rule may collapse `remote`, `hybrid`, or `onsite` back into `employment_type`.
- **FR-015**: This feature MUST NOT require PostGIS, geocoding, or radius/distance query support.
- **FR-016**: This feature MUST NOT require the immediate removal of `job.location_text` or the v1/v2 job-level structured fields from existing APIs during rollout.

### Key Entities *(include if feature involves data)*

- **Location**: A canonical normalized location entity that can represent physical geography or remote-eligibility scope at the supported precision levels for the system.
- **JobLocation**: The association between a `Job` and a `Location`, including the primary-link flag and any other metadata required to preserve ordering or relationship semantics.
- **Primary Job Location**: The one deterministic linked location used to keep compatibility and summary behavior stable on the `job` row during rollout.
- **Canonical Location Rule**: Shared normalization logic that decides when two source location representations should resolve to the same `Location` entity.
- **Job-Level Compatibility Fields**: The existing `job.location_text` and v1/v2 structured location fields retained during migration so current API clients and staged query paths continue to function.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Automated ingest tests show that equivalent source locations reuse canonical `locations` rows rather than producing duplicate entities.
- **SC-002**: Automated multi-location tests show that jobs can persist more than one linked location with a deterministic primary link.
- **SC-003**: The canonical-location backfill can be rerun without duplicate `locations` rows, duplicate `job_locations` rows, or primary-link drift.
- **SC-004**: Read/query paths can access normalized locations for country-aware and multi-location behavior without reparsing `location_text`.
- **SC-005**: Existing compatibility fields remain available during rollout even after normalized tables become the long-term authoritative model.

## Implementation Notes *(non-mandatory)*

- V3 should use a `GeoNames` downloadable dataset as the reference place source for canonical location identity and hierarchy rather than relying only on repo-local string normalization rules.
- V3 should use downloaded `GeoNames` data locally, not the hosted GeoNames web API, so canonicalization is not coupled to external request quotas or network availability.
- The external dataset should be treated as reference metadata for canonical identity and hierarchy, not as a mandate to import every place into the local database up front.
- The normalized schema should remain application-owned even if an external place dataset is used. `locations` and `job_locations` must still reflect this repo's semantics for primary links, remote scopes, and confidence handling.
- PostGIS remains out of scope for v3 unless later product requirements actually demand geometry-aware queries such as radius search, distance ranking, or polygon matching.
