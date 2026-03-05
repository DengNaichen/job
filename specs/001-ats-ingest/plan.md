# Implementation Plan: ATS Ingest (US1 Only)

**Branch**: `001-ats-ingest` | **Date**: 2026-03-05 | **Spec**: `specs/001-ats-ingest/spec.md`
**Input**: Feature specification from `specs/001-ats-ingest/spec.md`

## Summary

This plan only covers User Story 1 (P1): multi-platform fetching, transient error retries, graceful failure reporting, and bounded summary+detail concurrency.

Execution strategy is strict TDD: refactor test structure and write failing tests first (Red), implement minimal business changes (Green), then refactor.

Non-goals for this iteration: US2/US3/US4.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI, SQLModel, httpx, tenacity, pytest, pytest-asyncio, respx
**Storage**: PostgreSQL via SQLModel/AsyncSession
**Testing**: pytest + pytest-asyncio + respx
**Target Platform**: Backend service runtime (Linux/macOS)
**Project Type**: Backend ingest pipeline
**Performance Goals**: Enforce default detail-fetch concurrency of `6`
**Constraints**:
- All fetcher HTTP requests must go through BaseFetcher retry wrappers
- Retry exhaustion must produce trackable failure without process crash
- Scope must remain US1-only
- Changes must be covered by automated tests
**Scale/Scope**: 8 ATS platforms (Greenhouse, Lever, Ashby, Apple, Uber, TikTok, Eightfold, SmartRecruiters)

## Constitution Check

Current `.specify/memory/constitution.md` is still a template placeholder and does not define enforceable MUST clauses.

Quality gates applied for this plan:
- Test-first workflow (TDD)
- US1-only scope discipline
- Automated test coverage for all changed behavior
- No regressions in existing sync tests

## Project Structure

### Documentation (this feature)

```text
specs/001-ats-ingest/
├── spec.md
├── plan.md
└── tasks.md
```

### Source Code (repository root)

```text
app/
├── ingest/fetchers/
│   ├── base.py
│   ├── greenhouse.py
│   ├── lever.py
│   ├── ashby.py
│   ├── smartrecruiters.py
│   ├── apple.py
│   ├── uber.py
│   ├── tiktok.py
│   └── eightfold.py
├── services/application/sync/service.py
├── services/application/full_snapshot_sync/service.py
└── models/source.py

tests/
├── unit/ingest/fetchers/
├── unit/test_sync_service.py
└── unit/test_run_scheduled_ingests.py
```

**Structure Decision**: Keep current monorepo backend layout. Reorganize only US1-related tests under fetcher/sync test areas.

## US1 Scope and Acceptance Mapping

### US1-AC1: Multi-source fetching with transient retry
- Cover all 8 fetchers.
- Retryable status set: `429, 500, 502, 503, 504`.
- Verify requests are routed through BaseFetcher wrappers.

### US1-AC2: Graceful failure after retry exhaustion
Failure criteria for this plan:
1. Single-source sync marks `SyncRunStatus.failed` with error details.
2. Batch execution continues with later sources when one source fails.
3. Command can return non-zero summary exit code, but does not hard-crash mid-run.

### US1-AC3: Bounded summary+detail concurrency
- Default detail concurrency is unified to `6`.
- For summary+detail platforms, measured max in-flight requests must be `<= 6`.

## TDD-First Execution Strategy

### Phase 0 - Test Structure Refactor (no behavior change)
- Reorganize fetcher tests by US1 concerns.
- Extract shared fixtures/helpers to reduce duplication.
- File move/merge is allowed.

### Phase 1 - Write Failing Tests (Red)
- Retry contract tests for 8 platforms with retryable status matrix.
- Guard test to prevent bypassing BaseFetcher wrappers.
- Failure reporting and batch continuation tests.
- Detail concurrency cap tests with max in-flight assertion (`<= 6`).

### Phase 2 - Minimal Business Changes (Green)
- Replace direct HTTP calls with BaseFetcher wrapper methods where needed.
- Align retryable status behavior, including 429 handling.
- Align default detail concurrency to 6 across summary+detail fetchers.

### Phase 3 - Refactor and Stabilize
- Parameterize platform test matrix.
- Keep platform-specific edge-case tests (for example CSRF/detail fallback behavior).
- Remove duplicated legacy tests after equivalence is confirmed.

## Test Refactor Blueprint

```text
tests/unit/ingest/fetchers/
├── conftest.py
├── test_retry_contract.py
├── test_platform_retry_matrix.py
├── test_detail_concurrency_limit.py
└── test_no_raw_http_calls.py

tests/unit/sync/
└── test_failure_reporting_and_continuation.py
```

Migration note:
- Legacy files may temporarily coexist until new suite is stable.
- Old tests can be removed after assertion parity is verified.

## Validation Plan

Minimum validation commands:
- `pytest tests/unit/ingest/fetchers/test_no_raw_http_calls.py tests/unit/ingest/fetchers/test_retry_contract.py tests/unit/ingest/fetchers/test_platform_retry_matrix.py tests/unit/ingest/fetchers/test_detail_concurrency_limit.py -q`
- `pytest tests/unit/sync/test_failure_reporting_and_continuation.py -q`
- `pytest tests/unit/test_sync_service.py -q`
- `pytest tests/unit/test_run_scheduled_ingests.py -q`

Pass criteria:
- All new US1 tests pass.
- Sync regression tests pass.
- Each US1 acceptance criterion has explicit test evidence.

## Risks and Mitigations

- Risk: test refactor drops old assertion intent.
  - Mitigation: keep old and new tests in parallel until parity is confirmed.
- Risk: concurrency tests become flaky due to timing assumptions.
  - Mitigation: use deterministic in-flight counters/barriers, not sleep-only checks.
- Risk: unified retry behavior affects platform-specific quirks.
  - Mitigation: isolate exceptions via explicit per-fetcher retry config + tests.
