# Location Contract Test Layers

This folder contains feature-scoped tests for location API hard cutover.

## Layers

1. `contract/`
   - Fast schema-level contract checks.
   - Asserts removed legacy fields are absent from public models.

2. `integration/`
   - API payload shape checks for `/api/v1/jobs` and `/api/v1/matching/recommendations`.
   - Asserts legacy location fields are not returned.

3. `behavior/`
   - Non-contract behavior checks that must remain stable (country prefilter and conservative location semantics).

## Execution Order

Run in this order during migration:

1. `contract`
2. `integration`
3. `behavior`
