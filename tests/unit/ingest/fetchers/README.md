# US1 Fetcher Coverage Notes

This directory contains the User Story 1 contract tests for ATS ingest resilience.

## Coverage Map

- `test_no_raw_http_calls.py`
  - Enforces that concrete fetchers do not call `client.get()`/`client.post()` directly.
  - Guards usage of `BaseFetcher` retry wrappers.
- `test_retry_contract.py`
  - Validates retry status contract (`429/500/502/503/504`).
  - Validates SmartRecruiters detail retry config includes the same statuses.
- `test_platform_retry_matrix.py`
  - Validates all eight supported fetchers satisfy retry matrix expectations.
  - Re-checks no-raw-call guard for grouped platform subsets.
- `test_detail_concurrency_limit.py`
  - Validates default detail concurrency of summary+detail fetchers is `6`.
  - Validates runtime semaphore enforcement via measured max in-flight requests.

## Scope

- Focused on US1 acceptance criteria only:
  - Retry-wrapper compliance
  - Transient retry behavior across all supported platforms
  - Bounded detail concurrency
