# Feature Specification: ATS Ingest

**Feature Branch**: `001-ats-ingest`
**Created**: 2026-03-05
**Status**: Planned
**Input**: The system ingests job postings from external ATS (Applicant Tracking System) platforms into a normalized data model via full snapshot reconciliation.

## Summary

Multi-source job ingestion pipeline that fetches from ATS APIs, maps raw payloads to a canonical schema, deduplicates by external job ID, reconciles against existing state, and persists normalized jobs with structured locations and offloaded blob content.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Multi-Source Job Fetching with Retry Resilience (Priority: P1)

As a system operator, I can ingest jobs from any supported ATS platform, and transient API failures are automatically retried without crashing the sync run.

**Why this priority**: Reliability of data ingestion is the foundational requirement. Without resilient fetching, no downstream feature (matching, filtering) has data to work with.

**Independent Test**: Run a sync for each supported source against a mocked API that returns transient 500s, and verify the fetcher retries and eventually succeeds or fails gracefully.

**Acceptance Scenarios**:

1. **Given** a supported ATS platform (Greenhouse, Lever, Ashby, Apple, Uber, TikTok, Eightfold, SmartRecruiters), **When** a sync is triggered, **Then** all job listings are fetched with automatic retry on transient HTTP errors (429, 500, 502, 503, 504).
2. **Given** a transient error during fetch, **When** retries are exhausted, **Then** the sync run reports the failure without crashing the process.
3. **Given** a source with both summary and detail endpoints, **When** details are fetched, **Then** concurrent fetching is bounded by a configurable semaphore (default: 6).

---

### User Story 2 - Normalized Job Mapping with Structured Locations (Priority: P2)

As a downstream consumer (matching engine, API, UI), I receive jobs in a consistent schema regardless of which ATS they came from, including structured location data.

**Why this priority**: The canonical schema is what every downstream feature depends on. Inconsistent mapping means inconsistent matching, filtering, and display.

**Independent Test**: For each mapper, feed representative raw API payloads and verify the output `JobCreate` contains all required fields and structured `location_hints`.

**Acceptance Scenarios**:

1. **Given** raw job data from any supported ATS, **When** the mapper runs, **Then** a `JobCreate` is produced with `external_job_id`, `title`, `apply_url`, and `source_id`.
2. **Given** raw job data with location information, **When** the mapper runs, **Then** `location_hints` is populated with structured entries (city, region, country_code, workplace_type).
3. **Given** raw job data with HTML descriptions, **When** the mapper runs, **Then** `description_html` and `description_plain` are both available.
4. **Given** source employment labels with platform-specific variants, **When** the mapper runs, **Then** `employment_type` is normalized to canonical terms (`full-time`, `part-time`, `contract`, `intern`, `temporary`, `mixed`, `other`).

---

### User Story 3 - Full Snapshot Reconciliation (Priority: P3)

As a system operator, I can run a sync that reflects the current state of the source — new jobs are inserted, existing jobs are updated, and jobs no longer present are closed.

**Why this priority**: Correct job lifecycle management prevents stale listings from polluting search and matching results.

**Independent Test**: Sync a source with known existing state, then modify the source snapshot and re-sync. Verify inserts, updates, and closures match expectations.

**Acceptance Scenarios**:

1. **Given** a source with jobs not yet in the database, **When** sync runs, **Then** new jobs are inserted with status `open`.
2. **Given** a source with jobs already in the database, **When** sync runs with updated data, **Then** existing jobs are updated in place.
3. **Given** a job in the database that is absent from the latest fetch, **When** sync completes successfully, **Then** the missing job is closed (status updated).
4. **Given** duplicate `external_job_id` values in a single fetch, **When** deduplication runs, **Then** only one copy is retained.

---

### User Story 4 - Blob Storage Offloading (Priority: P4)

As a database operator, large content fields (raw payload, HTML descriptions) are stored in external blob storage rather than in PostgreSQL rows, keeping the database lean.

**Why this priority**: At scale (235K+ jobs), storing multi-KB HTML and raw JSON in PostgreSQL inflates TOAST storage. Offloading to blob storage keeps the database scannable and backup-friendly.

**Independent Test**: Sync a batch of jobs and verify `description_html` and `raw_payload` are persisted to blob storage with correct pointers on the Job row.

**Acceptance Scenarios**:

1. **Given** a job with `description_html`, **When** staging runs, **Then** the HTML is written to blob storage and the Job row contains a blob pointer instead of inline content.
2. **Given** a job with `raw_payload`, **When** staging runs, **Then** the raw payload is written to blob storage with a corresponding pointer.
3. **Given** concurrent blob uploads during staging, **When** concurrency is bounded, **Then** at most `blob_sync_concurrency` (default: 16) uploads run in parallel.

## Edge Cases

- Fetcher API returns a mix of retryable and non-retryable errors in a single sync run.
- Mapper receives a job with no location data — `location_hints` should be an empty list, not omitted.
- External job ID collision across different sources (isolated by `source_id`).
- Blob storage upload fails mid-batch — partial state must not corrupt the sync run.
- Detail endpoint returns 404 for a job that appeared in the listing — graceful degradation via `request_with_graceful_retry`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All fetcher HTTP calls MUST use `request_with_retry`, `request_json_with_retry`, or `request_with_graceful_retry` from `BaseFetcher`. No raw `client.get()` or `client.post()` is permitted.
- **FR-002**: All mappers MUST emit `location_hints` when location data is available in the raw payload.
- **FR-003**: Full snapshot reconciliation MUST close jobs not present in the latest successful fetch for the same source.
- **FR-004**: Blob storage offloading MUST be concurrent with bounded parallelism.
- **FR-005**: Deduplication MUST occur by `external_job_id` before staging.
- **FR-006**: All changes MUST be covered by automated tests.
- **FR-007**: Mappers MUST normalize source employment-type labels into canonical values (`full-time`, `part-time`, `contract`, `intern`, `temporary`, `mixed`, `other`) and must not use workplace labels (for example, remote/hybrid text) as `employment_type`.

### Key Entities *(include if feature involves data)*

- **Source**: ATS platform registration (platform + identifier), anchors all jobs from that source.
- **Job**: Canonical job record with normalized fields and blob pointers.
- **BaseFetcher**: Abstract base providing retry infrastructure and concurrent detail fetching.
- **BaseMapper**: Abstract base providing `raw → JobCreate` transformation.
- **FullSnapshotSyncService**: Orchestrator that wires fetch → map → dedupe → stage → persist → close.

### Supported ATS Platforms

| Platform | Fetcher | Mapper | API Style |
|----------|---------|--------|-----------|
| Greenhouse | GreenhouseFetcher | GreenhouseMapper | REST, paginated |
| Lever | LeverFetcher | LeverMapper | REST, paginated |
| Ashby | AshbyFetcher | AshbyMapper | JSON-RPC |
| Apple | AppleFetcher | AppleMapper | REST + CSRF |
| Uber | UberFetcher | UberMapper | REST, paginated |
| TikTok | TikTokFetcher | TikTokMapper | REST, paginated |
| Eightfold | EightfoldFetcher | EightfoldMapper | REST, paginated |
| SmartRecruiters | SmartRecruitersFetcher | SmartRecruitersMapper | REST, summary+detail |

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All fetcher HTTP calls use retry infrastructure — `grep -r "client\.get\|client\.post" app/ingest/fetchers/` returns zero matches outside of `base.py`.
- **SC-002**: All 8 mappers produce `location_hints` in their test outputs.
- **SC-003**: Full snapshot sync correctly inserts, updates, and closes jobs in automated tests.
- **SC-004**: Blob storage offloading is verified for both `description_html` and `raw_payload`.
- **SC-005**: Mapper test coverage verifies `employment_type` normalization to the canonical term set across supported ATS sources.
